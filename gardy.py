#!/usr/bin/env python3
"""
Gardy — Gardevoir Tie Tracker

Pulls tournament data from the Limitless Labs API (mew.limitlesstcg.com)
and shows what percentage of Gardevoir players (including Gardevoir/Jellicent)
have tied at least one round, cumulative after each swiss round.

Usage:
    python gardy.py                          # Default: Seattle Regionals 2026 (0055)
    python gardy.py -t 0054                  # EUIC 2026
    python gardy.py -r 9                     # Analyze 9 rounds instead of default
    python gardy.py -l                       # List available tournaments
    python gardy.py -d                       # Debug mode: show raw API shapes
"""

import argparse
import json
import sys
import time

import requests

LABS_API = "https://mew.limitlesstcg.com/labs"
DEFAULT_TOURNAMENT = "0055"
DEFAULT_DIVISION = "MA"
DAY1_ROUNDS = 8
META_THRESHOLD = 0.01  # 1% meta share to get its own column


def api_get(url, params=None):
    """GET request with retry + exponential backoff. Unwraps Labs {ok, message} envelope."""
    for attempt in range(4):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, dict) and "ok" in body:
                if not body["ok"]:
                    raise RuntimeError(f"API error: {body.get('message', 'unknown')}")
                return body["message"]
            return body
        except requests.exceptions.RequestException as e:
            if attempt < 3:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt+1}/3 in {wait}s... ({e})")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Tournament info
# ---------------------------------------------------------------------------

def fetch_tournament_info(tournament_id, division=DEFAULT_DIVISION):
    print(f"Fetching tournament info for {tournament_id} ...")
    info = api_get(f"{LABS_API}/data/tcg/tournament", params={"id": tournament_id, "division": division})
    name = f"{info.get('type', '').title()} {info.get('city', '')}".strip() or f"Tournament {tournament_id}"
    print(f"  {name} — {info.get('players', '?')} players, {info.get('round', '?')} rounds")
    return info, name


def list_tournaments():
    print("Fetching tournament list ...")
    tournaments = api_get(f"{LABS_API}/data/tcg/tournaments")
    print(f"\n  {'ID':<8}{'Type':<16}{'City':<20}{'Date':<24}{'Status'}")
    print(f"  {'─'*7} {'─'*15} {'─'*19} {'─'*23} {'─'*10}")
    for t in tournaments:
        tid = str(t.get("id", "?"))
        status = "done" if t.get("completed") else "live" if t.get("started") else "upcoming"
        print(f"  {tid:<8}{t.get('type', '?'):<16}{t.get('city', '?'):<20}{t.get('date', '?'):<24}{status}")
    print()


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_standings(tournament_id, division=DEFAULT_DIVISION):
    print(f"Fetching standings ...")
    data = api_get(f"{LABS_API}/data/tcg/standings", params={"tournamentId": tournament_id, "division": division})
    print(f"  {len(data)} players")
    return data


def fetch_pairings_all_rounds(tournament_id, num_rounds, division=DEFAULT_DIVISION):
    """Fetch pairings for each swiss round individually."""
    all_pairings = []
    print(f"Fetching pairings for rounds 1-{num_rounds} ...")
    for rnd in range(1, num_rounds + 1):
        data = api_get(
            f"{LABS_API}/data/tcg/pairings",
            params={"tournamentId": tournament_id, "division": division, "round": rnd},
        )
        for m in data:
            m["round"] = rnd
        all_pairings.extend(data)
        sys.stdout.write(f"\r  Round {rnd}/{num_rounds} ({len(data)} matches)")
        sys.stdout.flush()
    print(f"\n  {len(all_pairings)} total match records")
    return all_pairings


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def group_players_by_deck(standings):
    """Group all players by deck archetype. Returns {deck_name: set(tp_id)}."""
    decks = {}
    for entry in standings:
        tp_id = entry.get("tp_id")
        if tp_id is None:
            continue
        deck_name = entry.get("deck_name") or "Unknown"
        decks.setdefault(deck_name, set()).add(tp_id)
    return decks


def is_gardevoir(deck_name):
    return "gardevoir" in deck_name.lower()


def analyze_ties(pairings, player_set, num_rounds):
    """Return cumulative tie % for a set of players over num_rounds.
    Returns list of {round, tied, total, pct} dicts."""
    rounds = {}
    for m in pairings:
        rnd = m.get("round", 0)
        if 1 <= rnd <= num_rounds:
            rounds.setdefault(rnd, []).append(m)

    tied = set()
    total = len(player_set)
    results = []

    for rnd in range(1, num_rounds + 1):
        for m in rounds.get(rnd, []):
            if m.get("winner") != 0:
                continue
            for id_field in ("player1", "player2"):
                pid = m.get(id_field)
                if pid and pid in player_set:
                    tied.add(pid)

        pct = (len(tied) / total * 100) if total else 0
        results.append({"round": rnd, "tied": len(tied), "total": total, "pct": pct})

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_round_by_round(columns, num_rounds, tname):
    """Print a wide table: rows = rounds, columns = deck groups.
    columns is a list of (label, player_count, results_list) tuples."""
    print()
    print("=" * 70)
    print(f"  GARDEVOIR TIE TRACKER  —  {tname}")
    print(f"  Cumulative % who have tied at least once (Rounds 1-{num_rounds})")
    print("=" * 70)
    print()

    # Column widths
    col_w = 10
    label_w = 8  # "Round" column

    # Header row 1: deck names
    header = f"  {'':>{label_w}}"
    for label, count, _ in columns:
        short = label if len(label) <= col_w - 1 else label[:col_w - 2] + "."
        header += f"{short:>{col_w}}"
    print(header)

    # Header row 2: player counts
    counts = f"  {'':>{label_w}}"
    for _, count, _ in columns:
        counts += f"{'('+str(count)+')':>{col_w}}"
    print(counts)

    # Separator
    print(f"  {'─'*label_w}" + "─" * (col_w * len(columns)))

    # Data rows
    for rnd in range(num_rounds):
        row = f"  {'R'+str(rnd+1):>{label_w}}"
        for _, _, results in columns:
            pct = results[rnd]["pct"]
            row += f"{pct:>{col_w - 1}.1f}%"
        print(row)

    # Final row
    print(f"  {'─'*label_w}" + "─" * (col_w * len(columns)))
    final_row = f"  {'Final':>{label_w}}"
    for _, _, results in columns:
        r = results[-1]
        final_row += f"{r['pct']:>{col_w - 1}.1f}%"
    print(final_row)

    # Absolute numbers
    abs_row = f"  {'':>{label_w}}"
    for _, _, results in columns:
        r = results[-1]
        abs_row += f"{str(r['tied'])+'/'+str(r['total']):>{col_w}}"
    print(abs_row)
    print()


def dump_debug(standings, pairings):
    print("\n--- Sample standing ---")
    if standings:
        print(json.dumps(standings[0], indent=2, default=str))
    print("\n--- Sample pairing ---")
    if pairings:
        print(json.dumps(pairings[0], indent=2, default=str))
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Gardy — track how Gardevoir's tie rate builds round by round")
    parser.add_argument("-t", "--tournament-id", default=DEFAULT_TOURNAMENT,
                        help=f"Limitless Labs tournament ID (default: {DEFAULT_TOURNAMENT})")
    parser.add_argument("-r", "--rounds", type=int, default=DAY1_ROUNDS,
                        help=f"Number of rounds to analyze (default: {DAY1_ROUNDS})")
    parser.add_argument("-l", "--list", action="store_true", help="List available tournaments")
    parser.add_argument("-d", "--debug", action="store_true", help="Dump raw API shapes")
    args = parser.parse_args()

    print()
    print("  Gardy — Gardevoir Tie Tracker")
    print()

    if args.list:
        list_tournaments()
        return

    # 1. Tournament info
    info, tname = fetch_tournament_info(args.tournament_id)
    num_rounds = args.rounds

    # 2. Fetch data
    standings = fetch_standings(args.tournament_id)
    pairings = fetch_pairings_all_rounds(args.tournament_id, num_rounds)

    if args.debug:
        dump_debug(standings, pairings)

    # 3. Group players by deck
    deck_players = group_players_by_deck(standings)
    total_players = sum(len(p) for p in deck_players.values())

    # Gardevoir combined (all variants)
    gardy = set()
    for name, players in deck_players.items():
        if is_gardevoir(name):
            gardy.update(players)

    # Field = everyone except Gardevoir
    field = set()
    for name, players in deck_players.items():
        if not is_gardevoir(name):
            field.update(players)

    everyone = gardy | field

    # Top decks by player count (excluding Gardevoir variants), 1% threshold
    non_gardy_decks = [(name, players) for name, players in deck_players.items()
                       if not is_gardevoir(name)]
    non_gardy_decks.sort(key=lambda x: -len(x[1]))

    top_decks = [(name, players) for name, players in non_gardy_decks
                 if len(players) / total_players >= META_THRESHOLD]
    top_decks = top_decks[:10]

    # "Other" = field minus the top decks
    top_deck_players = set()
    for _, players in top_decks:
        top_deck_players.update(players)
    other = field - top_deck_players

    print(f"\n  {total_players} total players, analyzing rounds 1-{num_rounds}")
    print(f"  Gardevoir: {len(gardy)} players")
    print(f"  Field (non-Gardevoir): {len(field)} players")
    print(f"  Top decks (≥1% meta): {len(top_decks)}")

    # 4. Run analysis for each group
    columns = [
        ("Overall", len(everyone), analyze_ties(pairings, everyone, num_rounds)),
        ("Field", len(field), analyze_ties(pairings, field, num_rounds)),
        ("Gardevoir", len(gardy), analyze_ties(pairings, gardy, num_rounds)),
    ]
    for name, players in top_decks:
        columns.append((name, len(players), analyze_ties(pairings, players, num_rounds)))
    if other:
        columns.append(("Other", len(other), analyze_ties(pairings, other, num_rounds)))

    # 5. Display
    print_round_by_round(columns, num_rounds, tname)


if __name__ == "__main__":
    main()
