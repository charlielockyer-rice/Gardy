# Gardy — Gardevoir Tie Tracker

## Goal

Track what **percentage of Gardevoir players have tied at least one round** at a major Pokemon TCG tournament (EUIC 2026), showing how that percentage **builds cumulatively round by round** (after R1, R2, R3, ... R14).

Gardevoir is notorious for going to time. We want to quantify it — both standard Gardevoir and Gardevoir/Jellicent variants.

## Target Data: EUIC 2026 London

- **4,010 Masters players**, 14 swiss rounds
- **125 Gardevoir players** in published decklists (67 Gardevoir + 58 Gardevoir/Jellicent)
- **13.63% overall tournament tie rate**
- The deck had a ~17.56% metagame share

## What's Built

### `gardy.py`
Python script that:
1. Connects to the Limitless TCG play API (`play.limitlesstcg.com/api`)
2. Searches for a tournament by name or ID
3. Fetches standings (with deck names) and pairings (with round-by-round results)
4. Filters for Gardevoir/Gardevoir-Jellicent players
5. Tracks cumulative "has tied at least once" percentage after each swiss round
6. Outputs an ASCII table with progress bars

### `.github/workflows/gardy.yml`
GitHub Actions workflow (manual trigger) to run the analysis.

## The Blocker — What Needs to Happen Next

**The `play.limitlesstcg.com/api` only hosts online community tournaments, NOT official in-person championships like EUIC.** The script works for online tournaments but cannot pull EUIC 2026 data from the play API.

EUIC 2026 data lives on these platforms, all JavaScript-rendered SPAs without documented REST APIs:

| Platform | Tournament ID | URL |
|---|---|---|
| **Limitless Labs** (best source) | `0054` | `labs.limitlesstcg.com/0054/standings` |
| Limitless main | `517` | `limitlesstcg.com/tournaments/517` |
| Pokedata.ovh | `0000191` | `pokedata.ovh/standings/0000191/masters/` |
| RK9.gg | `EU01mU0Z1galE2FATDYs` | `rk9.gg/pairings/OCoavDStY0FSViwnpkxM` |

### What the next agent needs to do

1. **Discover the internal JSON API** that `labs.limitlesstcg.com` uses. The frontend is a JavaScript SPA — open the Network tab in DevTools on `labs.limitlesstcg.com/0054/standings?round=1` and look for XHR/fetch calls to find the actual data endpoint. This is the fastest path.

2. **If no internal API exists**, add **Playwright** or **Selenium** to scrape the Labs standings page round by round:
   - `labs.limitlesstcg.com/0054/standings?round=1` through `?round=14`
   - Each page shows player names, records, and deck archetypes
   - Also: `labs.limitlesstcg.com/0054/pairings?round=N` has individual match results

3. **Alternative approach**: Use `labs.limitlesstcg.com/0054/decks/gardevoir-ex-sv` and `labs.limitlesstcg.com/0054/decks/gardevoir-jellicent` — these deck-specific pages may show per-round win/tie/loss aggregates directly, which would be simpler than tracking individual players.

4. **The analysis logic in `gardy.py` is ready** — it just needs real data fed into it. The `find_gardevoir_players()` and `analyze_ties()` functions work correctly given properly shaped standings and pairings data.

## Expected Output

Something like:

```
  GARDEVOIR TIE TRACKER  —  EUIC 2026 London
  ============================================

  Gardevoir players: 125
    Gardevoir: 67
    Gardevoir Jellicent: 58

  Round   Tied    Total   Cum. %    Chart
  ─────── ─────── ─────── ───────── ────────────────────
  R1      8       125       6.4%    █░░░░░░░░░░░░░░░░░░░
  R2      19      125      15.2%    ███░░░░░░░░░░░░░░░░░
  R3      28      125      22.4%    ████░░░░░░░░░░░░░░░░
  ...
  R14     87      125      69.6%    █████████████░░░░░░░

  Result: 87/125 Gardevoir players (69.6%) tied at least once over 14 rounds.
```

(Numbers above are illustrative, not real data.)

## Known Context

- Grant Manley went **10-1-3** at EUIC 2026 (23rd place) — all 3 ties from "barely getting to the start of Game 3"
- At NAIC 2025, Gardevoir had a **~18.6% per-game tie rate** (599 ties in 3,226 games)
- The deck archetype slugs on Labs are `gardevoir-ex-sv` and `gardevoir-jellicent`

## Files

```
gardy.py                        # Main script
requirements.txt                # Python deps (just requests for now)
.github/workflows/gardy.yml     # GitHub Actions workflow
HANDOFF.md                      # This file
```
