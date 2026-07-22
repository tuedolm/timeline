#!/usr/bin/env python3
"""Generate daily puzzle blobs from content/library.json.

Each scheduled day becomes puzzles/YYYY-MM-DD.json with five rounds ordered
easy -> hard by the curator's difficulty rating. The client fetches only the
blob for the current UTC date, so future answers never ship to players who
haven't reached that day.

Usage:
    python3 tools/generate_puzzles.py            # generate all scheduled days
    python3 tools/generate_puzzles.py --check    # validate the library only

Validation enforced (PRD inclusion criteria):
    - every image has an exact integer year, blurb, credit, verified license
    - every scheduled day has exactly 5 rounds, all ids exist
    - no image is scheduled twice
"""

import argparse
import json
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "content" / "library.json"
OUT_DIR = ROOT / "puzzles"
LAUNCH = date(2026, 7, 21)  # puzzle #001

# Images are self-hosted: tools/fetch_images.py localizes each library image
# to assets/<id>.jpg. Set HOTLINK_COMMONS = True to fall back to hotlinking
# (dev only — do not ship that way).
HOTLINK_COMMONS = False
IMAGE_WIDTH = 1600

# Controlled vocabulary. Kept small on purpose: too many topics and nothing
# ever collides, which defeats the point of scheduling for variety.
TOPICS = {
    "space", "conflict", "disaster", "politics", "protest", "sport",
    "culture", "technology", "transport", "daily-life", "society", "science",
}


def image_url(img: dict) -> str:
    if HOTLINK_COMMONS:
        return (
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            + urllib.parse.quote(img["commonsFile"])
            + f"?width={IMAGE_WIDTH}"
        )
    return f"assets/{img['id']}.jpg"


def validate(lib: dict) -> list:
    errors = []
    images = {img["id"]: img for img in lib["images"]}
    for img in lib["images"]:
        where = f"image '{img.get('id', '?')}'"
        if not isinstance(img.get("year"), int):
            errors.append(f"{where}: year must be an exact integer")
        for field in ("blurb", "credit", "commonsFile", "story"):
            if not img.get(field):
                errors.append(f"{where}: missing {field}")
        kw = img.get("keywords")
        if not isinstance(kw, list) or len(kw) != 3 or not all(kw):
            errors.append(f"{where}: needs exactly 3 hint keywords")
        # topic and country drive variety scheduling; without them a day can
        # silently become five space photographs from the same country.
        if img.get("topic") not in TOPICS:
            errors.append(f"{where}: topic must be one of {sorted(TOPICS)}")
        if not img.get("country"):
            errors.append(f"{where}: missing country")
        if not img.get("verified", {}).get("license"):
            errors.append(f"{where}: license not verified")
        if img.get("difficulty") not in (1, 2, 3, 4, 5):
            errors.append(f"{where}: difficulty must be 1-5")

    seen = {}
    for day, ids in lib["schedule"].items():
        if len(ids) != 5:
            errors.append(f"{day}: needs exactly 5 rounds, has {len(ids)}")
        for i in ids:
            if i not in images:
                errors.append(f"{day}: unknown image id '{i}'")
            elif i in seen:
                errors.append(f"{day}: '{i}' already used on {seen[i]}")
            else:
                seen[i] = day
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate only")
    args = parser.parse_args()

    lib = json.loads(LIBRARY.read_text())
    errors = validate(lib)
    if errors:
        print(f"FAILED: {len(errors)} problem(s)")
        for e in errors:
            print("  -", e)
        return 1

    unused = len(lib["images"]) - sum(len(v) for v in lib["schedule"].values())
    print(f"Library OK: {len(lib['images'])} images, "
          f"{len(lib['schedule'])} scheduled days, {unused} images unscheduled")
    if args.check:
        return 0

    images = {img["id"]: img for img in lib["images"]}
    OUT_DIR.mkdir(exist_ok=True)
    for day_str in sorted(lib["schedule"]):
        day = date.fromisoformat(day_str)
        number = (day - LAUNCH).days + 1
        rounds = sorted(
            (images[i] for i in lib["schedule"][day_str]),
            key=lambda img: img["difficulty"],
        )
        blob = {
            "date": day_str,
            "number": number,
            "rounds": [
                {
                    "image": image_url(img),
                    "year": img["year"],
                    "blurb": img["blurb"],
                    "credit": img["credit"],
                    "story": img["story"],
                    "keywords": img["keywords"],
                }
                for img in rounds
            ],
        }
        out = OUT_DIR / f"{day_str}.json"
        out.write_text(json.dumps(blob, indent=2) + "\n")
        print(f"  wrote {out.relative_to(ROOT)}  (#" + f"{number:03d})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
