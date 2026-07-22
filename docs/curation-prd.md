# Yearshot — Curation PRD

**Status:** Agreed and built — `tools/curate.html` implements this
**Last updated:** July 22, 2026

---

## 1. Why we are redoing this

The first curation tool optimised for the wrong thing. It swept Wikimedia
categories looking for images that were *legally clean and technically large*,
and produced a review queue of parking lots, real-estate listings, lab gels and
a cheetah. Legality and resolution are necessary, not sufficient. Nothing in
that pipeline could tell a good photograph from a merely valid one.

The first playtest confirms the cost. From puzzle #002:

| Signal | Result | Target |
|---|---|---|
| Average game score | **9,425** / 25,000 | 12,000–18,000 |
| Average error, round 4 | **33.9 years** | — |
| Hints taken on round 1 | **11 of 12 players** | round 1 is meant to be a free win |
| Completion rate | 48% of visitors | — |
| **Share rate** | **10 shares / 11 plays (91%)** | — |

Two conclusions. The game is materially too hard — a full 2,500 points below
the bottom of the intended band, with even the "easy" opening round requiring a
hint from almost everyone. And the share loop is *already working*: at a 91%
share rate, content quality is the bottleneck, not distribution.

**The bet:** photographs that are recognisable and carry a real story will
raise scores into the target band and make every reveal worth reading.

---

## 2. What a Yearshot photograph is

Every image must clear all five bars. These are not preferences.

1. **A documented event or moment.** Something happened: a first flight, a
   disaster, a protest, an opening night, a landing. If nothing happened, there
   is nothing to say in the reveal.
2. **A verifiable exact year.** Never "circa", never a range. An approximate
   answer makes the scoring dishonest and is unrecoverable once shipped.
3. **Visually strong.** Well composed, in focus, properly exposed, and legible
   filling a phone screen. Photographs are the product.
4. **Free licence with attribution captured.** Public domain, CC0, CC BY, or
   CC BY-SA. "No known copyright restrictions" is *not* a licence grant and
   does not qualify.
5. **A story worth two sentences.** Something a player did not know and will
   repeat. "The pilot had never flown at night before." Not "this is a bridge."

### War is in. Gore is out.
The bad side of history belongs here — war, invasions, disasters, protest and
repression. That is the history worth learning, and the playtesters said the
learning was the best part. The line is drawn at the **image**, not the
subject: battles, occupations and aftermath pass; bodies, executions, torture
and atrocity imagery do not. A scoring screen should never sit beneath a
photograph of victims.

---

## 3. The difficulty model

The single most useful distinction we found: **recognisability and datability
are different axes.** The data proves it. Challenger is about as iconic as a
photograph gets, and it was round 1 of puzzle #002 — yet players missed by an
average of 11.5 years and 11 of 12 needed a hint. They knew exactly what they
were looking at and still could not place the year.

So "use icons" is not by itself a fix. What actually makes a round easy is that
**the event's year is common knowledge**, not that the event is famous.

| Tier | Definition | Example |
|---|---|---|
| 1 — gift | The year itself is common knowledge | Moon landing, Titanic, fall of the Berlin Wall |
| 2 — recall | Famous event, year recalled with effort | Challenger, Chernobyl, Live Aid |
| 3 — reason | Famous *subject*, ambiguous year — read the details | A Shuttle launch, a Concorde, a Beatles photo |
| 4 — read the era | Documented moment, unfamiliar; date it from the scene | A named but obscure protest or opening |
| 5 — devious | Feels like the wrong decade entirely | A 1985 photo that reads as 2005 |

A day runs 1 → 5. **Every day must open on a genuine tier 1**, because the
current opener is not one and it is costing us players before they reach the
good part.

**Target:** lift the average game score from 9,425 into 12,000–18,000. Curation
is the primary lever — dropping average error from ~17 years to ~8 lands us at
roughly 12,800 without touching the scoring curve. Loosening the decay constant
is the backup lever, not the first move, because it inflates scores without
making the game better.

---

## 4. Where photographs come from

The old pipeline swept raw categories. The new premise: **great photographs
have already been curated by humans — start from their work.**

| Source | Why it qualifies |
|---|---|
| **Commons Featured Pictures** | Human-vetted for technical and visual quality. The quality bar is already enforced. |
| **Commons Quality Images** | Larger pool, same principle, lower ceiling. |
| **Wikipedia event articles** | The lead image is usually *the* iconic photograph, and the article itself is the story and the date. |
| **Wikidata events** | Structured `point in time` + image, so the year arrives as data rather than a guess parsed from a caption. |
| **Named press/state archives** | Anefo, the German Federal Archive, NASA, LOC — documentary by construction, well described, and not US-only. |

Starting from an *event* rather than an image gives us the photograph, the
year, and the story in one fetch, which is exactly what the old tool could
never assemble.

**Geography:** deliberately not US-only. The starting library over-indexes on
American subjects; non-US sources are a first-class requirement, not a garnish.

---

## 5. How the tool should work

Search-led, not sweep-led. You should be able to say *"the 1960s space
programme"* or *"European protests"* and get a short list of strong candidates,
rather than being handed 200 files to sift.

Per candidate the tool must show, without extra clicks:

- The photograph **large** — quality cannot be judged from a thumbnail
- The proposed **year and where it came from** (Wikidata, article, caption)
- The **source article summary** — the raw material for the story
- **Licence and attribution**, already formatted for the reveal
- A **drafted two-sentence story** in the house voice, editable inline
- A **difficulty tier** suggestion, which you set

Accept, edit, or reject. Rejections are remembered so the same photograph never
comes back.

**Authoring:** stories are drafted from the source article and always edited by
a human before they ship. Never auto-published — flat or wrong writing reaching
players costs more than it saves.

---

## 6. Variety is scheduled, not hoped for

Every image carries a `topic` (a controlled list of twelve) and a `country`.
Orbital images use "Space", because what a player sees is space, not the
country that launched it.

The starting library is badly lopsided and it was invisible until measured:
**63% United States**, with space the largest topic by a distance. Curating one
photograph at a time cannot reveal that, so the tool shows live coverage of
what already exists, flags anything taking more than its fair share, and
suggests searches aimed at the thinnest areas.

`schedule_next.py` then scores every slot rather than dealing blindly: it
penalises repeating a topic within a day, and repeating topics or countries
used in the previous three days, while still running each day easy to hard.
It is a preference, not a hard rule — a thin pool still schedules, it just
does the best it can with what exists.

## 7. Non-goals

- Fully automatic curation. The filters exist to save reading time, never to
  make the final call.
- Maximum volume. A smaller library of excellent photographs beats a large one
  of adequate ones.
- Representative history. A balanced survey of the 20th century makes a boring
  game; we are selecting for *interest*, not coverage.

---

## 7. Open questions

1. **Volume.** Five a day is 1,825 a year. Featured Pictures alone will not
   sustain that indefinitely. Do we accept a slower daily cadence, a smaller
   rotation, or a wider net once the good material thins?
2. **Existing library.** 41 images are curated and 8 days are banked. Do the
   weaker ones get retired against this bar, or grandfathered?
3. **Old tooling.** `harvest.py`, the review queue and `candidates.json` are to
   be removed. Keep `generate_puzzles.py`, `fetch_images.py`, `check_bank.py`
   and `schedule_next.py` — those handle scheduling and delivery, not taste,
   and they work.
