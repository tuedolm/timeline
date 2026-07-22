#!/usr/bin/env python3
"""Report how many days of puzzles remain, and fail when the bank runs low.

Run by CI daily so the content bank can never quietly run dry — the one
failure that takes the game down for everyone at once.

Usage:
    python3 tools/check_bank.py               # human-readable report
    python3 tools/check_bank.py --min-days 14 # exit 1 when below the threshold
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "content" / "library.json"
PUZZLES = ROOT / "puzzles"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-days", type=int, default=14)
    args = ap.parse_args()

    lib = json.loads(LIBRARY.read_text())
    schedule = lib.get("schedule", {})
    today = date.today()

    future = sorted(d for d in schedule if date.fromisoformat(d) >= today)
    last = date.fromisoformat(max(schedule)) if schedule else today - timedelta(days=1)
    days_left = (last - today).days + 1 if future else 0

    scheduled_ids = {i for ids in schedule.values() for i in ids}
    unscheduled = [i for i in lib["images"] if i["id"] not in scheduled_ids]
    blobs = len(list(PUZZLES.glob("*.json"))) if PUZZLES.exists() else 0

    print(f"Today (UTC-ish local):  {today}")
    print(f"Last scheduled puzzle:  {last}")
    print(f"Days of puzzles left:   {days_left}")
    print(f"Generated blobs:        {blobs}")
    print(f"Library images:         {len(lib['images'])}")
    print(f"Unscheduled images:     {len(unscheduled)} "
          f"({len(unscheduled) // 5} more full day(s) available)")

    if days_left < args.min_days:
        print(
            f"\nLOW BANK: {days_left} day(s) left, want at least {args.min_days}.\n"
            f"  1. open tools/curate.html and search for events to curate\n"
            f"  2. export and merge into content/library.json\n"
            f"  3. python3 tools/schedule_next.py\n"
            f"  4. python3 tools/generate_puzzles.py && python3 tools/fetch_images.py\n"
            f"  5. commit and push"
        )
        return 1

    print("\nBank OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
