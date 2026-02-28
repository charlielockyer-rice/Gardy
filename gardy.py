#!/usr/bin/env python3
"""
Gardy — Gardevoir Tie Tracker

Pulls EUIC 2026 tournament data from the Limitless TCG play API and
shows what percentage of Gardevoir players (including Gardevoir/Jellicent)
have tied at least one round, cumulative after each swiss round.

Data sources (tried in order):
  1. Limitless play API (play.limitlesstcg.com/api) — for online tournaments
  2. Direct tournament ID if provided

Usage:
    python gardy.py                          # Auto-finds EUIC or largest recent tournament
    python gardy.py -t <ID>                  # Specify a Limitless play tournament ID
    python gardy.py -s "Regional"            # Search by name
    python gardy.py -d                       # Debug mode: show raw API shapes

Known tournament IDs (cross-reference):
    Limitless main site:  517       (limitlesstcg.com/tournaments/517)
    Limitless Labs:       0054      (labs.limitlesstcg.com/0054/standings)
    Pokedata.ovh:         0000191   (pokedata.ovh/standings/0000191/masters/)
    RK9.gg pairings:      EU01mU0Z1galE2FATDYs
"""

import argparse
import json
import sys
import time

import requests

PLAY_API = "https://play.limitlesstcg.com/api"

GARDEVOIR_KEYWORDS = ["gardevoir"]


def api_get(url, params=None, headers=None):
    """GET request with retry + exponential backoff."""
    for attempt in range(4):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt+1}/3 in {wait}s... ({e})")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Tournament discovery
# ---------------------------------------------------------------------------

def find_tournament(search_term=None):
    """Search the Limitless play API for a tournament by name."""
    search = search_term or "International"
    print(f"Searching for '{search}' on play.limitlesstcg.com ...")

    tournaments = api_get(
        f"{PLAY_API}/tournaments",
        params={"game": "PTCG", "limit": 100},
    )

    matches = [t for t in tournaments if search.lower() in t.get("name", "").lower()]

    if not matches:
        # Fall back: show what's available
        print(f"  No match for '{search}'. Largest recent tournaments:")
        by_size = sorted(tournaments, key=lambda t: t.get("players", 0), reverse=True)
        for t in by_size[:10]:
            print(f"    [{t['id']}] {t['name']}  ({t.get('players', '?')} players, {t.get('date', '?')})")
        sys.exit(1)

    chosen = max(matches, key=lambda t: t.get("players", 0))
    print(f"  Found: {chosen['name']}  (ID: {chosen['id']}, {chosen.get('players', '?')} players)")
    return chosen["id"], chosen["name"]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_standings(tournament_id):
    print(f"Fetching standings for {tournament_id} ...")
    data = api_get(f"{PLAY_API}/tournaments/{tournament_id}/standings")
    print(f"  {len(data)} players")
    return data


def fetch_pairings(tournament_id):
    print(f"Fetching pairings for {tournament_id} ...")
    data = api_get(f"{PLAY_API}/tournaments/{tournament_id}/pairings")
    print(f"  {len(data)} match records")
    return data


# ---------------------------------------------------------------------------
# Deck identification
# ---------------------------------------------------------------------------

def extract_deck_name(player_entry):
    """Pull a deck/archetype name from a standings entry, trying many field shapes."""
    for field in ("deck", "deck_name", "deckIdentifier", "archetype"):
        val = player_entry.get(field)
        if val:
            return str(val)

    dl = player_entry.get("decklist")
    if isinstance(dl, dict):
        for f in ("name", "archetype", "identifier"):
            if dl.get(f):
                return str(dl[f])

    icons = player_entry.get("icons")
    if icons:
        return str(icons)

    return None


def is_gardevoir(deck_name):
    if not deck_name:
        return False
    low = deck_name.lower()
    return any(kw in low for kw in GARDEVOIR_KEYWORDS)


def player_key(entry):
    """Return a stable player identifier from a standings or pairing entry."""
    for f in ("name", "player", "id"):
        if entry.get(f):
            return str(entry[f])
    return None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def find_gardevoir_players(standings):
    gardy = {}
    variants = {}

    for entry in standings:
        deck = extract_deck_name(entry)
        pid = player_key(entry)
        if pid and is_gardevoir(deck):
            gardy[pid] = {
                "name": pid,
                "deck": deck,
                "placing": entry.get("placing", "?"),
            }
            variants[deck] = variants.get(deck, 0) + 1

    return gardy, variants


def analyze_ties(pairings, gardy_players):
    """Return cumulative tie % for Gardevoir players after each swiss round."""

    # Group by round, keep only swiss (phase == "swiss" or unset)
    rounds = {}
    for m in pairings:
        phase = str(m.get("phase", "")).lower()
        if phase and phase not in ("swiss", ""):
            continue
        rnd = m.get("round", 0)
        if rnd >= 1:
            rounds.setdefault(rnd, []).append(m)

    if not rounds:
        return []

    print(f"  {max(rounds)} swiss rounds detected")

    tied = set()
    total = len(gardy_players)
    results = []

    for rnd in sorted(rounds):
        for m in rounds[rnd]:
            winner = m.get("winner")
            is_tie = (
                winner is None
                or winner == ""
                or winner == 0
                or (isinstance(winner, str) and winner.lower() in ("tie", "draw", ""))
            )
            if not is_tie:
                continue

            for side in ("player1", "player2"):
                p = m.get(side)
                if p is None:
                    continue
                pid = p if isinstance(p, str) else player_key(p) if isinstance(p, dict) else None
                if pid and pid in gardy_players:
                    tied.add(pid)

        pct = (len(tied) / total * 100) if total else 0
        results.append({
            "round": rnd,
            "tied": len(tied),
            "total": total,
            "pct": pct,
        })

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_table(results, gardy_players, variants, name):
    print()
    print("=" * 62)
    print(f"  GARDEVOIR TIE TRACKER  —  {name}")
    print("=" * 62)
    print()

    print(f"  Gardevoir players: {len(gardy_players)}")
    for v, n in sorted(variants.items(), key=lambda x: -x[1]):
        print(f"    {v}: {n}")
    print()

    if not results:
        print("  (no round-by-round data)")
        return

    hdr = f"  {'Round':<8}{'Tied':<8}{'Total':<8}{'Cum. %':<10}{'Chart'}"
    print(hdr)
    print(f"  {'─'*7} {'─'*7} {'─'*7} {'─'*9} {'─'*20}")

    for r in results:
        fill = int(r["pct"] / 5)
        bar = "█" * fill + "░" * (20 - fill)
        print(f"  R{r['round']:<6}{r['tied']:<8}{r['total']:<8}{r['pct']:>5.1f}%    {bar}")

    final = results[-1]
    print()
    print(f"  Result: {final['tied']}/{final['total']} Gardevoir players "
          f"({final['pct']:.1f}%) tied at least once over {final['round']} rounds.")
    print()


def dump_debug(standings, pairings):
    print("\n--- Sample standing ---")
    if standings:
        print(json.dumps(standings[0], indent=2, default=str))
    print("\n--- Sample pairing ---")
    if pairings:
        print(json.dumps(pairings[0], indent=2, default=str))
    print()


def dump_all_decks(standings):
    """Show every unique deck identifier in the standings."""
    decks = set()
    for p in standings:
        d = extract_deck_name(p)
        if d:
            decks.add(d)
    if decks:
        print("  Deck archetypes found:")
        for d in sorted(decks):
            print(f"    - {d}")
    else:
        print("  No deck identifiers found in standings data.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Gardy — track how Gardevoir's tie rate builds round by round")
    parser.add_argument("-t", "--tournament-id", help="Limitless play API tournament ID")
    parser.add_argument("-s", "--search", help="Search for tournament by name")
    parser.add_argument("-d", "--debug", action="store_true", help="Dump raw API shapes")
    args = parser.parse_args()

    print()
    print("  Gardy — Gardevoir Tie Tracker")
    print()

    # 1. Find tournament
    if args.tournament_id:
        tid = args.tournament_id
        tname = f"Tournament {tid}"
    else:
        tid, tname = find_tournament(args.search)

    # 2. Fetch
    standings = fetch_standings(tid)
    pairings = fetch_pairings(tid)

    if args.debug:
        dump_debug(standings, pairings)

    # 3. Identify Gardevoir players
    gardy, variants = find_gardevoir_players(standings)

    if not gardy:
        print("\n  No Gardevoir players found!")
        print("  Possible reasons:")
        print("    - Deck names use an unexpected format")
        print("    - Decklists aren't published for this tournament")
        print()
        dump_all_decks(standings)
        if args.debug is False:
            print("  Tip: re-run with -d to inspect raw API response.\n")
        sys.exit(1)

    # 4. Analyze
    results = analyze_ties(pairings, gardy)

    # 5. Display
    print_table(results, gardy, variants, tname)


if __name__ == "__main__":
    main()
