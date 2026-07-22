#!/usr/bin/env python3
"""Prepare curation candidates automatically, everything except the words.

Given an event, this resolves the defining photograph, verifies it, works out
the year, infers topic and country, and estimates difficulty. What it does not
do is write: story, blurb and hint keywords are left empty, because those carry
the game's voice and are written by hand from the `sourceSummary` each
candidate carries.

Candidate selection is gap-aware. The library is 63% United States with space
as its largest topic, so events are scored to favour the countries, topics and
decades that are currently thin.

Usage:
    python3 tools/auto_curate.py --count 20
    python3 tools/auto_curate.py --events "Suez Crisis,Chernobyl disaster"
    python3 tools/auto_curate.py --gaps

Output: tools/candidates.json — review in tools/review.html.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "content" / "library.json"
CANDIDATES = ROOT / "tools" / "candidates.json"
SEED = ROOT / "tools" / "events_seed.json"

WIKI = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
             "en.wikipedia/all-access/user/{title}/monthly/2024010100/2025123100")
UA = "YearshotCurator/1.0 (daily photo puzzle; candidate preparation)"
PAUSE = 0.9

MIN_WIDTH = 800
TOPICS = ["space", "conflict", "disaster", "politics", "protest", "sport",
          "culture", "technology", "transport", "daily-life", "society", "science"]

FREE = re.compile(r"public domain|^cc0|^cc by(-sa)?[ -]?\d", re.I)

# Same line the curation tool draws: dark history is welcome, graphic imagery
# is not. Blocking topics rather than images would exclude the war photography
# that playtesters said they learned the most from.
GRAPHIC = re.compile(r"\b(" + "|".join([
    "corpse", "corpses", "dead body", "dead bodies", "cadaver", "mass grave",
    "execution", "executed", "beheading", "decapitat", "lynching", "lynched",
    "firing squad", "mutilat", "dismember", "torture", "tortured",
    "gore", "gory", "bloodied", "blood-soaked", "severed",
    "concentration camp", "extermination camp", "gas chamber", "auschwitz",
    "dachau", "buchenwald", "treblinka", "holocaust victim", "genocide", "emaciated",
]) + r")\b", re.I)

NOT_PHOTO = re.compile(r"\b(" + "|".join([
    "flag of", "coat of arms", "emblem", "crest", "seal of", "logo",
    "map of", "maps of", "atlas", "cartograph", "diagram", "chart of",
    "painting", "engraving", "lithograph", "etching", "woodcut", "drawing",
    "illustration", "manuscript", "poster", "stamp", "banknote", "medal",
    "gemälde", "zeichnung", "stich", "karte", "flagge", "bandeira", "bandera",
    "drapeau", "vlag", "flagga", "mapa", "mappa", "escudo", "brasão", "wappen",
    "pintura", "peinture", "collage", "montage",
]) + r")\b", re.I)

TOPIC_HINTS = {
    "conflict":  r"\bwar\b|battle|invasion|siege|troops|military|offensive|ceasefire|army|occupation|uprising against",
    "disaster":  r"earthquake|flood|hurricane|cyclone|erupt|tsunami|famine|crash|explosion|disaster|wildfire|meltdown|capsiz",
    "space":     r"spacecraft|orbit|lunar|astronaut|cosmonaut|satellite|space station|rocket launch",
    "politics":  r"election|president|parliament|treaty|summit|government|minister|coup|referendum|accord|constitution",
    "protest":   r"protest|demonstration|\bmarch\b|strike|uprising|revolution|riot|movement",
    "sport":     r"olympic|world cup|championship|tournament|stadium|athlete|football|cricket|cycling|tennis",
    "culture":   r"film|music|concert|festival|album|band|artist|exhibition|opera|carnival",
    "technology": r"invention|computer|aircraft|engine|prototype|first flight|nuclear|telephone|broadcast",
    "transport": r"railway|railroad|airline|\bship\b|bridge|tunnel|metro|canal|underground|motorway",
    "society":   r"immigration|housing|education|civil rights|labour|labor|population|welfare|generation",
    "science":   r"discovery|experiment|vaccine|research|genome|physics|expedition",
}

COUNTRIES = ["United States", "United Kingdom", "England", "Scotland", "Wales", "Ireland",
    "France", "Germany", "Italy", "Spain", "Portugal", "Netherlands", "Belgium", "Poland",
    "Czechoslovakia", "Czech Republic", "Hungary", "Austria", "Switzerland", "Sweden",
    "Norway", "Denmark", "Finland", "Iceland", "Russia", "Soviet Union", "Ukraine",
    "Romania", "Bulgaria", "Greece", "Turkey", "Yugoslavia", "Serbia", "Bosnia", "Croatia",
    "China", "Japan", "South Korea", "North Korea", "Vietnam", "Cambodia", "India",
    "Pakistan", "Bangladesh", "Indonesia", "Thailand", "Malaysia", "Singapore",
    "Philippines", "Australia", "New Zealand", "Canada", "Mexico", "Brazil", "Argentina",
    "Chile", "Peru", "Colombia", "Cuba", "Egypt", "Israel", "Lebanon", "Syria", "Iraq",
    "Iran", "Kuwait", "Saudi Arabia", "South Africa", "Nigeria", "Kenya", "Ethiopia",
    "Rwanda", "Algeria", "Morocco", "Hong Kong", "Taiwan", "Panama"]


def get(url: str, attempts: int = 3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(6 * (i + 1)); continue
            if e.code == 404:
                return None
            if i == attempts - 1:
                return None
        except Exception:
            if i == attempts - 1:
                return None
            time.sleep(2)
    return None


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", s or "")).strip()


def years_in(t):
    return sorted({int(y) for y in re.findall(r"\b(1[89]\d{2}|20\d{2})\b", t or "")})


def approximate(t):
    return bool(re.search(r"\bcirca\b|\bca\.\s*\d{4}|\bapprox|\bbetween\b|\d{4}s\b", t or "", re.I))


def has_clock(t):
    return bool(re.search(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", t or ""))


def article(title):
    url = (WIKI + "?action=query&format=json&formatversion=2&prop=extracts|images|pageimages"
           "&exintro=1&explaintext=1&imlimit=40&piprop=original&titles="
           + urllib.parse.quote(title))
    d = get(url)
    if not d:
        return None
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    return pages[0]


def pageviews(title):
    """Monthly views over two years. A fame proxy, which is a difficulty proxy."""
    d = get(PAGEVIEWS.format(title=urllib.parse.quote(title.replace(" ", "_"), safe="")))
    if not d or "items" not in d:
        return 0
    return sum(i.get("views", 0) for i in d["items"])


def commons_meta(files):
    """Batch metadata for candidate files."""
    out = []
    for i in range(0, len(files), 25):
        batch = files[i:i + 25]
        url = (COMMONS + "?action=query&format=json&formatversion=2"
               "&prop=imageinfo|categories&cllimit=60&iiprop=extmetadata|size|mime"
               "&iiextmetadatafilter=LicenseShortName|Artist|DateTimeOriginal|ImageDescription"
               "&titles=" + urllib.parse.quote("|".join("File:" + f for f in batch)))
        d = get(url)
        if not d:
            continue
        for p in d.get("query", {}).get("pages", []):
            if "imageinfo" not in p:
                continue
            ii = p["imageinfo"][0]
            md = ii.get("extmetadata", {})
            out.append({
                "commonsFile": p["title"].replace("File:", ""),
                "license": (md.get("LicenseShortName") or {}).get("value", ""),
                "artist": strip_html((md.get("Artist") or {}).get("value", "")),
                "dateOriginal": strip_html((md.get("DateTimeOriginal") or {}).get("value", "")),
                "description": strip_html((md.get("ImageDescription") or {}).get("value", ""))[:400],
                "categories": [c["title"].replace("Category:", "") for c in p.get("categories", [])],
                "width": ii.get("width", 0), "height": ii.get("height", 0),
                "mime": ii.get("mime", ""),
            })
        time.sleep(PAUSE)
    return out


def pick_photo(page, summary):
    """Best usable photograph on the article: passes every check, then largest."""
    files = [i["title"].replace("File:", "") for i in page.get("images", [])]
    files = [f for f in files if re.search(r"\.(jpe?g|png)$", f, re.I)
             and not NOT_PHOTO.search(f) and not re.search(r"icon|symbol|arrow|blank|commons-logo", f, re.I)]
    lead = ""
    if page.get("original", {}).get("source"):
        lead = urllib.parse.unquote(page["original"]["source"].split("/")[-1])
    ordered = ([lead] if lead else []) + [f for f in files if f != lead]
    if not ordered:
        return None, "no candidate images"

    metas = commons_meta(ordered[:14])
    rejects = Counter()
    usable = []
    for m in metas:
        blob = " ".join([m["commonsFile"], m["description"], " ".join(m["categories"])])
        if not m["mime"].startswith("image/") or "svg" in m["mime"]:
            rejects["not an image"] += 1; continue
        if NOT_PHOTO.search(blob):
            rejects["not a photograph"] += 1; continue
        if not FREE.search(m["license"]):
            rejects["licence"] += 1; continue
        if m["width"] < MIN_WIDTH:
            rejects["too small"] += 1; continue
        if GRAPHIC.search(blob) or GRAPHIC.search(summary):
            rejects["graphic"] += 1; continue
        usable.append(m)
    if not usable:
        return None, ", ".join(f"{v}× {k}" for k, v in rejects.most_common()) or "nothing usable"
    usable.sort(key=lambda m: m["width"] * m["height"], reverse=True)
    return usable[0], None


def confirm_year(meta, title, summary):
    """Accept a year only when the article itself vouches for it.

    The article is the authority on when the event happened, so the photograph's
    year must appear there too. Without this, two bad things pass: a file whose
    date is really an upload or assembly timestamp (an "Invasion of
    Czechoslovakia collage" dated 2025), and a photograph that is simply the
    wrong one for the event (a 1938 portrait on an article about 1947).
    """
    if approximate(meta["dateOriginal"]) or approximate(summary[:200]):
        return None
    date_years = [] if has_clock(meta["dateOriginal"]) else years_in(meta["dateOriginal"])
    name_years = years_in(meta["commonsFile"])
    photo_years = set(date_years) | set(name_years)
    article_years = set(years_in(title + " " + summary[:400]))

    agreed = sorted(photo_years & article_years)
    if len(agreed) == 1:
        return agreed[0]
    return None


def infer_topic(text):
    scores = {t: len(re.findall(p, text, re.I)) for t, p in TOPIC_HINTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "society"


def infer_country(text, title=""):
    """Most-mentioned country, with the title winning ties.

    Scanning in list order picked whichever country happened to sit earliest in
    the list, which made Prague Spring German and the Iran-Iraq War American.
    """
    # The opening sentence is where an article says where something happened;
    # later paragraphs drag in every neighbour and ally. Counting the whole
    # summary made the Prague Spring German.
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0] if text.strip() else ""
    counts = {}
    for c in COUNTRIES:
        pat = r"\b" + re.escape(c) + r"\b"
        total = len(re.findall(pat, text, re.I))
        if not total:
            continue
        counts[c] = (total
                     + 5 * len(re.findall(pat, first, re.I))
                     + (10 if re.search(pat, title, re.I) else 0))
    if not counts:
        return ""
    return max(counts, key=counts.get)


def difficulty_from_fame(views):
    """More famous means more people know the year, so an easier round."""
    if views > 4_000_000: return 1
    if views > 1_200_000: return 2
    if views > 400_000:   return 3
    if views > 120_000:   return 4
    return 5


STOPWORDS = {"the", "of", "and", "in", "a", "an", "on", "to", "for", "at", "war",
             "disaster", "crisis", "revolution", "uprising", "protests", "protest"}


def likely_duplicate(title, lib):
    """Flag an event the library probably already covers.

    Dedupe by filename alone missed Occupy Wall Street, which is already in the
    library under a different photograph — and the existing images predate the
    sourceArticle field, so there is nothing to match on but the words.
    """
    words = {w for w in re.findall(r"[a-z]+", title.lower()) if w not in STOPWORDS and len(w) > 3}
    if not words:
        return ""
    # Every distinctive word must appear. A partial match is meaningless at this
    # length: one shared word paired "Prague Spring" with a photograph whose
    # blurb happened to mention spring, and "Occupy Wall Street" with a
    # nineteenth-century photograph of Sacramento Street.
    for img in lib["images"]:
        hay = (img["id"] + " " + img.get("blurb", "")).lower()
        if all(w in hay for w in words):
            return img["id"]
    return ""


def kebab(s):
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))[:42]


def coverage(lib):
    return Counter(i["topic"] for i in lib["images"]), Counter(i["country"] for i in lib["images"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=15, help="how many candidates to prepare")
    ap.add_argument("--events", help="comma-separated article titles instead of the seed list")
    ap.add_argument("--gaps", action="store_true", help="report coverage gaps and exit")
    args = ap.parse_args()

    lib = json.loads(LIBRARY.read_text())
    topics, countries = coverage(lib)
    total = len(lib["images"])

    if args.gaps:
        print(f"{total} images\n\ntopics:")
        for t in TOPICS:
            print(f"  {t:<12} {topics.get(t, 0)}")
        print("\ncountries:")
        for c, n in countries.most_common():
            print(f"  {c:<18} {n}  ({n/total:.0%})")
        return 0

    have_articles = {i.get("sourceArticle", "") for i in lib["images"]}
    have_files = {i["commonsFile"] for i in lib["images"]}
    queue = json.loads(CANDIDATES.read_text()) if CANDIDATES.exists() else []
    have_files |= {c["commonsFile"] for c in queue}

    if args.events:
        events = [e.strip() for e in args.events.split(",") if e.strip()]
    else:
        events = json.loads(SEED.read_text())["events"]
        # Favour events whose likely country/topic is thin in the library.
        def gap_score(name):
            c = infer_country(name, name)
            return (countries.get(c, 0) if c else 3)
        events = [e for e in events if e not in have_articles]
        events.sort(key=gap_score)

    prepared, skipped = [], []
    for n, title in enumerate(events, 1):
        if len(prepared) >= args.count:
            break
        print(f"  .. [{n}/{len(events)}] {title}", flush=True)
        page = article(title)
        time.sleep(PAUSE)
        if not page:
            skipped.append((title, "no article")); continue
        summary = strip_html(page.get("extract", ""))
        if GRAPHIC.search(summary):
            skipped.append((title, "graphic subject")); continue

        meta, why = pick_photo(page, summary)
        if not meta:
            skipped.append((title, why)); continue
        if meta["commonsFile"] in have_files:
            skipped.append((title, "already have this photo")); continue

        year = confirm_year(meta, title, summary)
        if year is None:
            skipped.append((title, "year not corroborated")); continue

        views = pageviews(title)
        time.sleep(PAUSE)
        text = title + " " + summary
        prepared.append({
            "id": kebab(title),
            "commonsFile": meta["commonsFile"],
            "year": year,
            "difficulty": difficulty_from_fame(views),
            "topic": infer_topic(text),
            "country": infer_country(text, title) or "",
            # Left empty on purpose: these carry the game's voice and are
            # written by hand from sourceSummary.
            "blurb": "",
            "story": "",
            "keywords": [],
            "credit": (meta["artist"][:80] + (" — public domain" if re.search(r"public domain", meta["license"], re.I)
                       else f" ({meta['license']})")) if meta["artist"] else meta["license"],
            "sourceArticle": title,
            "sourceSummary": summary[:900],
            "pageviews": views,
            "possibleDuplicate": likely_duplicate(title, lib),
            "verified": {"license": meta["license"], "artist": meta["artist"],
                         "dateOriginal": meta["dateOriginal"]},
            "_width": meta["width"], "_height": meta["height"],
        })
        have_files.add(meta["commonsFile"])
        print(f"  ok    {year}  d{prepared[-1]['difficulty']}  "
              f"{prepared[-1]['topic']:<11} {prepared[-1]['country']:<16} {title}", flush=True)

    for t, why in skipped:
        print(f"  skip  {t}  ({why})", flush=True)

    queue.extend(prepared)
    CANDIDATES.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n")
    print(f"\nprepared {len(prepared)}, skipped {len(skipped)}; queue now {len(queue)}")
    print("Review and approve in tools/review.html, then hand the export over for story writing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
