#!/usr/bin/env python3
"""Harvest candidate photographs from Wikimedia Commons.

This automates the boring 80% of curation — finding freely licensed, well-dated,
high-resolution photographs — and deliberately automates none of the judgement.
It never writes to the library; it produces a review queue that a human accepts
or rejects in tools/curate.html. Taste is the moat; scripts are bad at it.

What gets filtered out automatically (the PRD's inclusion criteria):
  - anything not clearly free (public domain / CC0 / CC BY / CC BY-SA)
  - anything under --min-width pixels
  - anything whose date field doesn't evidence the exact year ("circa" is out)
  - anything already in content/library.json, or already reviewed and rejected
  - non-photographs (maps, documents, logos, diagrams) by filename heuristics

Usage:
    python3 tools/harvest.py --years 1975-2015 --per-year 8
    python3 tools/harvest.py --years 1985,1992,2003 --per-year 20
    python3 tools/harvest.py --category "Photographs by Documerica" --limit 60

Output: tools/candidates.json (merged with any existing queue, deduped).

Be a good citizen: Wikimedia returns HTTP 429 under its robot policy if you
hammer it, so requests are paced and backed off.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "content" / "library.json"
CANDIDATES = ROOT / "tools" / "candidates.json"
REJECTED = ROOT / "tools" / "rejected.json"

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "YearglassHarvester/1.0 (daily photo puzzle; curation candidate search; "
    "contact via repository issues)"
)

FREE_LICENSE = re.compile(r"public domain|^cc0|^cc by(-sa)?[ -]?\d", re.I)
# Filenames that are almost never a usable photograph for this game.
JUNK_NAME = re.compile(
    r"\.(svg|pdf|djvu|ogv|webm|tif|tiff|gif)$|logo|map of|diagram|chart|"
    r"coat of arms|flag of|signature|stamp|banknote|poster|cover|screenshot",
    re.I,
)
PAUSE = 1.5  # seconds between API calls


def api_get(params: dict, attempts: int = 4) -> dict:
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(3)
    return {}


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", s or "")).strip()


def category_files(category: str, limit: int) -> list:
    """File titles in a category (non-recursive)."""
    out, cont = [], None
    while len(out) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": "file",
            "cmlimit": min(500, limit - len(out)),
        }
        if cont:
            params["cmcontinue"] = cont
        data = api_get(params)
        members = data.get("query", {}).get("categorymembers", [])
        if not members:
            break
        out.extend(m["title"] for m in members)
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(PAUSE)
    return out[:limit]


def file_metadata(titles: list) -> list:
    """Batch imageinfo lookup (the API accepts 50 titles per request)."""
    results = []
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        data = api_get(
            {
                "action": "query",
                "prop": "imageinfo",
                "iiprop": "extmetadata|size|mime",
                "iiextmetadatafilter": "LicenseShortName|Artist|DateTimeOriginal|ImageDescription",
                "titles": "|".join(batch),
            }
        )
        for page in data.get("query", {}).get("pages", []):
            if "imageinfo" not in page:
                continue
            ii = page["imageinfo"][0]
            md = ii.get("extmetadata", {})
            results.append(
                {
                    "commonsFile": page["title"].replace("File:", ""),
                    "license": (md.get("LicenseShortName") or {}).get("value", ""),
                    "artist": strip_html((md.get("Artist") or {}).get("value", "")),
                    "dateOriginal": strip_html(
                        (md.get("DateTimeOriginal") or {}).get("value", "")
                    ),
                    "description": strip_html(
                        (md.get("ImageDescription") or {}).get("value", "")
                    )[:300],
                    "width": ii.get("width", 0),
                    "height": ii.get("height", 0),
                    "mime": ii.get("mime", ""),
                }
            )
        time.sleep(PAUSE)
    return results


def exact_year(date_field: str, want: int) -> bool:
    """Reject anything that doesn't evidence the exact year.

    'circa', 'or', ranges and decade forms are all disqualifying — an ambiguous
    answer makes the scoring dishonest, which is the one thing we can't ship.
    """
    if not date_field:
        return False
    low = date_field.lower()
    if any(w in low for w in ("circa", " ca.", "c.19", "c.20", "between", "or ", "unknown", "s]]", "190s", "0s")):
        return False
    years = set(re.findall(r"\b(1[89]\d{2}|20\d{2})\b", date_field))
    return years == {str(want)}


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", help="e.g. 1975-2015 or 1985,1992,2003")
    ap.add_argument("--category", help="a specific Commons category to sweep")
    ap.add_argument("--per-year", type=int, default=6, help="candidates to keep per year")
    ap.add_argument("--limit", type=int, default=120, help="files to inspect per category")
    ap.add_argument("--min-width", type=int, default=1200)
    args = ap.parse_args()

    if not args.years and not args.category:
        ap.error("give --years or --category")

    lib = load_json(LIBRARY, {"images": []})
    known = {i["commonsFile"] for i in lib.get("images", [])}
    queue = load_json(CANDIDATES, [])
    known |= {c["commonsFile"] for c in queue}
    known |= set(load_json(REJECTED, []))

    targets = []
    if args.category:
        targets.append((None, args.category))
    if args.years:
        years = []
        for part in args.years.split(","):
            if "-" in part:
                a, b = part.split("-")
                years.extend(range(int(a), int(b) + 1))
            else:
                years.append(int(part))
        targets.extend((y, f"{y} photographs") for y in years)

    found_total = 0
    for year, category in targets:
        try:
            titles = category_files(category, args.limit)
        except Exception as e:  # noqa: BLE001 — report and continue to next year
            print(f"  {category}: lookup failed ({e})")
            continue
        if not titles:
            print(f"  {category}: no files")
            continue

        titles = [t for t in titles if not JUNK_NAME.search(t)]
        meta = file_metadata(titles)

        kept = []
        for m in meta:
            if m["commonsFile"] in known:
                continue
            if not m["mime"].startswith("image/"):
                continue
            if not FREE_LICENSE.search(m["license"]):
                continue
            if m["width"] < args.min_width:
                continue
            if year is not None and not exact_year(m["dateOriginal"], year):
                continue
            m["year"] = year
            m["thumb"] = (
                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                + urllib.parse.quote(m["commonsFile"])
                + "?width=400"
            )
            kept.append(m)
            known.add(m["commonsFile"])
            if len(kept) >= args.per_year:
                break

        found_total += len(kept)
        queue.extend(kept)
        print(f"  {category}: inspected {len(meta)}, kept {len(kept)}")

    CANDIDATES.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{found_total} new candidate(s); queue now {len(queue)}")
    print(f"Review them in tools/curate.html → {CANDIDATES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
