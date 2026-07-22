#!/usr/bin/env python3
"""Extend the puzzle schedule using images that are approved but unscheduled.

Deals images across days so every day gets its own easy -> hard curve rather
than one day of gimmes and another of impossibilities: the pool is sorted by
difficulty and dealt round-robin, then each day is sorted internally.

Run after merging newly curated images into content/library.json, then
regenerate blobs with tools/generate_puzzles.py.

Usage:
    python3 tools/schedule_next.py              # schedule every full day available
    python3 tools/schedule_next.py --days 7     # cap how many days to add
    python3 tools/schedule_next.py --dry-run
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "content" / "library.json"
ROUNDS = 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="max days to add (0 = all possible)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lib = json.loads(LIBRARY.read_text())
    schedule = lib.setdefault("schedule", {})

    scheduled_ids = {i for ids in schedule.values() for i in ids}
    pool = [i for i in lib["images"] if i["id"] not in scheduled_ids]
    pool.sort(key=lambda i: i["difficulty"])

    n_days = len(pool) // ROUNDS
    if args.days:
        n_days = min(n_days, args.days)
    if n_days == 0:
        print(f"Not enough unscheduled images ({len(pool)}) for a full day of {ROUNDS}.")
        print("Harvest and curate more first: tools/harvest.py then tools/curate.html")
        return 1

    usable = pool[: n_days * ROUNDS]
    # Deal round-robin so each day draws across the whole difficulty range.
    days = [[] for _ in range(n_days)]
    for idx, img in enumerate(usable):
        days[idx % n_days].append(img)
    for d in days:
        d.sort(key=lambda i: i["difficulty"])

    start = date.fromisoformat(max(schedule)) + timedelta(days=1) if schedule else date.today()

    added = {}
    for offset, day_imgs in enumerate(days):
        day = (start + timedelta(days=offset)).isoformat()
        added[day] = [i["id"] for i in day_imgs]

    for day, ids in added.items():
        diffs = "".join(str(next(i["difficulty"] for i in lib["images"] if i["id"] == x)) for x in ids)
        print(f"  {day}  [{diffs}]  {', '.join(ids)}")

    if args.dry_run:
        print(f"\nDry run — would add {len(added)} day(s).")
        return 0

    schedule.update(added)
    LIBRARY.write_text(json.dumps(lib, indent=2, ensure_ascii=False) + "\n")
    print(f"\nAdded {len(added)} day(s); schedule now runs to {max(schedule)}.")
    print("Next: python3 tools/generate_puzzles.py && python3 tools/fetch_images.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
