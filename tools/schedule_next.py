#!/usr/bin/env python3
"""Extend the puzzle schedule from images that are approved but unscheduled.

Two things are balanced at once.

**Difficulty** — every day runs easy to hard, so round 1 is a win and round 5
is a fight.

**Variety** — a day should not be five space photographs, and two consecutive
days should not both open in the United States. The library is lopsided (63%
US, space the largest topic by far), so left alone a naive scheduler produces
days that feel repetitive even though each photograph is individually fine.

Scoring picks each slot: candidates are penalised for repeating a topic already
used in the day, and for repeating topics or countries used in recent days. It
is a preference, not a hard rule — a thin pool still schedules rather than
refusing, it just does the best it can.

Usage:
    python3 tools/schedule_next.py
    python3 tools/schedule_next.py --days 7
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

# How far back variety looks, and how hard each clash is punished.
LOOKBACK_DAYS = 3
PENALTY_TOPIC_IN_DAY = 100     # two of the same topic in one day is the worst
PENALTY_COUNTRY_IN_DAY = 40
PENALTY_TOPIC_RECENT = 12
PENALTY_COUNTRY_RECENT = 8


def recent_context(schedule: dict, images: dict, upto: str, n: int) -> tuple:
    """Topics and countries used in the n scheduled days before `upto`."""
    past = sorted(d for d in schedule if d < upto)[-n:]
    topics, countries = [], []
    for d in past:
        for i in schedule[d]:
            img = images.get(i)
            if img:
                topics.append(img.get("topic"))
                countries.append(img.get("country"))
    return topics, countries


def pick_day(pool: list, want_difficulty: int, day_topics: list,
             day_countries: list, recent_topics: list, recent_countries: list):
    """Choose the best next image for a slot, or None when the pool is empty."""
    best, best_score = None, None
    for img in pool:
        # Difficulty is the primary driver; variety breaks ties and nudges.
        score = abs(img["difficulty"] - want_difficulty) * 200
        if img.get("topic") in day_topics:
            score += PENALTY_TOPIC_IN_DAY
        if img.get("country") in day_countries:
            score += PENALTY_COUNTRY_IN_DAY
        score += recent_topics.count(img.get("topic")) * PENALTY_TOPIC_RECENT
        score += recent_countries.count(img.get("country")) * PENALTY_COUNTRY_RECENT
        if best_score is None or score < best_score:
            best, best_score = img, score
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="max days to add (0 = all possible)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lib = json.loads(LIBRARY.read_text())
    schedule = lib.setdefault("schedule", {})
    images = {i["id"]: i for i in lib["images"]}

    scheduled_ids = {i for ids in schedule.values() for i in ids}
    pool = [i for i in lib["images"] if i["id"] not in scheduled_ids]

    n_days = len(pool) // ROUNDS
    if args.days:
        n_days = min(n_days, args.days)
    if n_days == 0:
        print(f"Not enough unscheduled images ({len(pool)}) for a full day of {ROUNDS}.")
        print("Curate more first: open tools/curate.html")
        return 1

    start = date.fromisoformat(max(schedule)) + timedelta(days=1) if schedule else date.today()
    added = {}
    remaining = list(pool)

    for offset in range(n_days):
        day = (start + timedelta(days=offset)).isoformat()
        # Look back across days already scheduled, including ones added in this run.
        merged = dict(schedule, **added)
        recent_topics, recent_countries = recent_context(merged, images, day, LOOKBACK_DAYS)

        chosen, day_topics, day_countries = [], [], []
        for slot in range(ROUNDS):
            # Aim for difficulty 1..5 across the five rounds.
            want = 1 + round(slot * 4 / (ROUNDS - 1))
            pick = pick_day(remaining, want, day_topics, day_countries,
                            recent_topics, recent_countries)
            if pick is None:
                break
            remaining.remove(pick)
            chosen.append(pick)
            day_topics.append(pick.get("topic"))
            day_countries.append(pick.get("country"))

        chosen.sort(key=lambda i: i["difficulty"])
        added[day] = [i["id"] for i in chosen]

    for day, ids in added.items():
        diffs = "".join(str(images[i]["difficulty"]) for i in ids)
        topics = ", ".join(sorted({images[i]["topic"] for i in ids}))
        countries = ", ".join(sorted({images[i]["country"] for i in ids}))
        print(f"  {day}  [{diffs}]")
        print(f"       topics:    {topics}")
        print(f"       countries: {countries}")

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
