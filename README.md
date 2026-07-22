# Yearshot

A once-a-day web game: five photographs, drag a slider to guess the year each
was taken, score by how close you were, share a spoiler-free result grid.

Static site, no build step, no backend required. State (streaks, stats,
resume) lives in localStorage.

## Run locally

```sh
python3 -m http.server 8471
# open http://localhost:8471
```

## Architecture

| Path | What it is |
|---|---|
| `index.html` / `styles.css` / `app.js` | The game client |
| `content/library.json` | Canonical curated library: exact year, blurb, credit, difficulty, **audited license** per image |
| `puzzles/YYYY-MM-DD.json` | Pre-generated daily blobs; the client fetches only today's, so future answers never ship |
| `tools/generate_puzzles.py` | library.json → daily blobs, with PRD-criteria validation (`--check` to lint only) |
| `tools/curate.html` | Curation UI: paste a Commons file → fetches license/artist/size via API, gates on free license + resolution, exports JSON |
| `tools/fetch_images.py` | Localizes images into `assets/` for CDN upload (run before launch; hotlinking Commons is prototype-only) |
| `infra/worker.js` | Cloudflare Worker scaffold for anonymous score-distribution analytics (client stub is `track()` in app.js, off by default) |

## Keeping the bank full

The one failure that takes the game down for everyone at once is running out of
puzzles, and it happens silently. `.github/workflows/bank-check.yml` runs daily
and opens a GitHub issue when fewer than 14 days remain.

The refill loop:

```sh
# 1. open tools/curate.html, search an event, review, add
#    (serve locally: python3 -m http.server 8471)
python3 tools/schedule_next.py            # 2. deal into days, easy -> hard
python3 tools/generate_puzzles.py && python3 tools/fetch_images.py
git add -A && git commit && git push      # 3. ship
python3 tools/check_bank.py               # anytime: days left
```

### Curation starts from an event, not an image

The rules live in [docs/curation-prd.md](docs/curation-prd.md); the tool
enforces them. Searching Wikipedia for an event returns the photograph, the
year and the story in one fetch — which is the whole point, because an earlier
sweep-based harvester could find legally-clean pixels but never assemble those
three things together.

The tool refuses to add anything that fails the bar: non-free licence, under
1200px, an approximate date, or not a photograph (articles lead with flags,
maps and crests as often as photographs). It proposes a year only when two
independent sources agree, and otherwise makes you set it — a wrong year is
scored against real players and is the one error the game cannot survive.

**War and difficult history belong here** — that is the history worth learning,
and playtesters said so. The line is drawn at *graphic imagery*, not dark
subject matter: battles, protests, disasters and their aftermath all pass;
bodies, executions and atrocity do not.

## Daily cycle

The client keys everything off the UTC date. `generate_puzzles.py` turns the
hand-authored `schedule` in library.json into per-day blobs; puzzle #001 is
2026-07-21. Six days are currently banked (30 images, each used once).
`tools/curate.html` is how the bank grows: target ~90 banked days before a
public launch.

## Tuning knobs (all in `app.js`)

- **`DECAY = 12`** — `points = round(5000 · e^(−|error|/DECAY))`. The single
  most important parameter; retune from real playtest data (median total
  should land in 12,000–18,000).
- **`ANCHORS`** — non-linear slider mapping; 1970–present gets ~58% of travel.
- **`band()`** — share-grid thresholds: 🟩 ≤5 yrs, 🟨 ≤10, 🟧 ≤20, 🟥 ≤40, ⬛ wild.
- **`HINT_TIERS`** — progressive hints: era ×0.8, keywords ×0.7, decade ×0.6.
  Tiers must stay ordered weakest→strongest *and* cheapest→dearest, or a tier
  becomes a dominated choice nobody takes. Keywords live in `library.json` and
  must be context clues only — a keyword naming the event would make tier 2
  stronger than tier 3 and break the ladder.
- **`CONFIG.name`** — single point of rename (also update index.html meta,
  manifest.webmanifest, and the OG image).

## Playtest deployment

Live at **https://yearshot.com/**. `git push` triggers
`.github/workflows/deploy.yml`, which assembles a `_site` directory and
publishes **only what a player needs**:

    index.html about.html dashboard.html app.js styles.css
    favicon.svg og.png manifest.webmanifest CNAME puzzles/ assets/

`content/`, `tools/`, `infra/` and `docs/` are deliberately excluded. Serving
the whole repository put the entire library — every future answer — at a public
URL, which defeats the point of shipping one day at a time. The curation and
schedule tools are local-only for the same reason: run
`python3 -m http.server 8471` and open `tools/curate.html` or
`tools/schedule.html`.

Tomorrow's puzzle blob is still guessable by URL. Fixing that properly needs a
server that refuses to serve future dates; it is not worth it at playtest size.

## Launch checklist

- [x] Self-hosted images (`assets/`, in-repo; move to a CDN if traffic grows)
- [x] Privacy + photo credits page (`about.html`, linked from results)
- [x] Absolute `og:image` URL
- [x] CC attribution rendered on every reveal + credits page
- [x] Hint mechanic (decade reveal, −40% of round score)
- [x] **Name: Yearshot** (renamed from Timeline, which collides with
  Asmodee/Zygomatic's Timeline card game)
- [ ] Bank ≥90 days of puzzles via `tools/curate.html` (8 days banked now;
  puzzle #009+ shows "no puzzle" until scheduled)
- [x] Analytics live: `infra/worker.js` on Cloudflare (D1). Aggregates at
  https://yearshot-analytics.tuedolm.workers.dev/stats
- [ ] Custom domain once named
- [ ] Optional: service worker for offline/instant-load PWA

## Content rules (from the PRD, enforced by the generator)

Exact verified year — never "circa". Clear license with attribution captured.
One-line reveal blurb. ≥1200px wide. Difficulty 1–5, five images per day
ordered easy → hard. Weight the library toward 1970–2015 and hunt for
photos that *feel* like the wrong decade — a representative sample of history
makes a boring game.
