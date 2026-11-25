"""Social Club Mode game formats. All money is in integer cents and every balance map is zero-sum."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from .handicap import playing_handicap, stableford_points, strokes_on_hole

N_HOLES = 18

GAME_TITLES = {
    "stableford": "Stableford",
    "ambrose": "Ambrose / Scramble",
    "skins": "Skins",
    "best_ball": "2-Ball Best Ball (4BBB)",
    "wolf": "Wolf",
    "nassau": "Nassau",
}


def cents(dollars: Any) -> int:
    try:
        return int(round(float(dollars or 0) * 100))
    except (TypeError, ValueError):
        return 0


@dataclass
class GameResult:
    key: str
    title: str
    standings: list[dict[str, Any]] = field(default_factory=list)
    balances: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------- helpers
def _ph(rnd, name: str, allowance: float) -> int:
    return playing_handicap(rnd.player(name).handicap, allowance)


def _strokes(rnd, name: str, hole: int, allowance: float) -> int:
    return strokes_on_hole(_ph(rnd, name, allowance), rnd.course.hole(hole).stroke_index)


def _net(rnd, name: str, hole: int, allowance: float = 1.0, use_net: bool = True) -> float:
    """Net (or gross) strokes; a pick-up is +inf so it can never win a hole."""
    g = rnd.gross(name, hole)
    if g is None:
        return math.inf
    return g - (_strokes(rnd, name, hole, allowance) if use_net else 0)


def _points(rnd, name: str, hole: int, allowance: float) -> int:
    h = rnd.course.hole(hole)
    return stableford_points(rnd.gross(name, hole), h.par, _strokes(rnd, name, hole, allowance))


def _pot(everyone: list[str], winners: list[str], stake_c: int) -> dict[str, int]:
    """Everyone antes stake_c; winners split the pot (odd cents go to the first winners)."""
    if stake_c <= 0 or not winners:
        return {p: 0 for p in everyone}
    bal = {p: -stake_c for p in everyone}
    share, rem = divmod(stake_c * len(everyone), len(winners))
    for i, w in enumerate(winners):
        bal[w] += share + (1 if i < rem else 0)
    return bal


def _sequential_holes(rnd, names: list[str]) -> list[int]:
    """Holes 1..n in order, stopping at the first hole not yet scored by everyone."""
    out = []
    for h in range(1, N_HOLES + 1):
        if all(rnd.has_score(n, h) for n in names):
            out.append(h)
        else:
            break
    return out


def _check_players(rnd, names: list[str], what: str) -> None:
    missing = [n for n in names if n not in rnd.player_names]
    if missing:
        raise ValueError(f"{what}: unknown player(s) {', '.join(missing)}")


def _provisional(thru: int) -> list[str]:
    return [] if thru >= N_HOLES else [f"Provisional: thru {thru} of {N_HOLES}."]


# ---------------------------------------------------------------- Stableford
def stableford(rnd, cfg: dict) -> GameResult:
    allowance = float(cfg.get("allowance", 1.0))
    stake = cents(cfg.get("stake", 0))
    rows = []
    for p in rnd.player_names:
        holes = [h for h in range(1, N_HOLES + 1) if rnd.has_score(p, h)]
        rows.append(
            {
                "Player": p,
                "Points": sum(_points(rnd, p, h, allowance) for h in holes),
                "Thru": len(holes),
                "Hcp": _ph(rnd, p, allowance),
            }
        )
    rows.sort(key=lambda r: (-r["Points"], r["Player"]))
    started = any(r["Thru"] for r in rows)
    best = rows[0]["Points"] if rows else 0
    winners = [r["Player"] for r in rows if r["Points"] == best] if started else []
    notes = _provisional(min((r["Thru"] for r in rows), default=0))
    if stake and len(winners) > 1:
        notes.append(f"Tie on {best} pts: pot split {len(winners)} ways.")
    return GameResult("stableford", GAME_TITLES["stableford"], rows, _pot(rnd.player_names, winners, stake), notes)


# ---------------------------------------------------------------- Ambrose
def ambrose_team_handicap(handicaps: list[float], divisor: float | None = None) -> float:
    """Common Australian default: combined handicaps / (2 x team size), i.e. /4 for pairs, /8 for fours."""
    if not handicaps:
        return 0.0
    d = float(divisor) if divisor else 2.0 * len(handicaps)
    return round(sum(float(h) for h in handicaps) / d, 1)


def ambrose(rnd, cfg: dict) -> GameResult:
    teams = cfg.get("teams") or []
    if len(teams) < 1:
        raise ValueError("Ambrose: add at least one team.")
    stake = cents(cfg.get("stake", 0))
    divisor = cfg.get("divisor") or None
    rows = []
    for t in teams:
        members = list(t.get("players") or [])
        _check_players(rnd, members, f"Ambrose team {t.get('name')}")
        hcp = ambrose_team_handicap([rnd.player(m).handicap for m in members], divisor)
        book = rnd.team_scores.get(t["name"], {})
        gross = 0
        par_played = 0
        for h, v in book.items():
            par = rnd.course.hole(h).par
            gross += v if v is not None else par + 3  # pick-up counts as par + 3
            par_played += par
        thru = len(book)
        net = gross - hcp * thru / N_HOLES
        rows.append(
            {
                "Team": t["name"],
                "Players": ", ".join(members),
                "Gross": gross,
                "Team Hcp": hcp,
                "Net": round(net, 1),
                "To Par": gross - par_played,
                "Thru": thru,
            }
        )
    rows.sort(key=lambda r: (r["Net"], r["Team"]))
    notes = _provisional(min((r["Thru"] for r in rows), default=0))
    if any(r["Thru"] < N_HOLES for r in rows):
        notes.append("Net is pro-rated by holes played until the round is complete.")
    winners: list[str] = []
    if rows and any(r["Thru"] for r in rows):
        best = rows[0]["Net"]
        for r, t in ((r, next(t for t in teams if t["name"] == r["Team"])) for r in rows):
            if r["Net"] == best:
                winners += list(t["players"])
    everyone = [p for t in teams for p in t.get("players", [])]
    return GameResult("ambrose", GAME_TITLES["ambrose"], rows, _pot(everyone, winners, stake), notes)


# ---------------------------------------------------------------- Skins
def skins(rnd, cfg: dict) -> GameResult:
    value = cents(cfg.get("value", 0))
    use_net = bool(cfg.get("use_net", True))
    allowance = float(cfg.get("allowance", 1.0))
    carryover = bool(cfg.get("carryover", True))
    names = rnd.player_names
    won: dict[str, list[tuple[int, int]]] = {p: [] for p in names}
    carry = 0
    carry_from = None
    holes = _sequential_holes(rnd, names)
    for h in holes:
        nets = {p: _net(rnd, p, h, allowance, use_net) for p in names}
        best = min(nets.values())
        leaders = [p for p, v in nets.items() if v == best]
        if len(leaders) == 1 and best != math.inf:
            won[leaders[0]].append((h, carry + 1))
            carry, carry_from = 0, None
        elif carryover:
            carry += 1
            carry_from = carry_from or h
        else:
            carry = 0
    bal = {p: 0 for p in names}
    n = len(names)
    for p, wins in won.items():
        for _, k in wins:
            bal[p] += value * k * (n - 1)
            for o in names:
                if o != p:
                    bal[o] -= value * k
    rows = [
        {
            "Player": p,
            "Skins": sum(k for _, k in won[p]),
            "Holes": ", ".join(f"{h}" + (f" (x{k})" if k > 1 else "") for h, k in won[p]) or "-",
        }
        for p in names
    ]
    rows.sort(key=lambda r: (-r["Skins"], r["Player"]))
    notes = _provisional(len(holes))
    if carry:
        notes.append(f"{carry} skin(s) carrying over from hole {carry_from}.")
    return GameResult("skins", GAME_TITLES["skins"], rows, bal, notes)


# ---------------------------------------------------------------- 2-Ball Best Ball
def best_ball(rnd, cfg: dict) -> GameResult:
    teams = cfg.get("teams") or []
    if len(teams) < 2:
        raise ValueError("Best Ball: set up at least two teams of two.")
    mode = cfg.get("mode", "stableford")
    allowance = float(cfg.get("allowance", 0.85))
    stake = cents(cfg.get("stake", 0))
    rows = []
    for t in teams:
        members = list(t.get("players") or [])
        _check_players(rnd, members, f"Best Ball team {t.get('name')}")
        holes = [h for h in range(1, N_HOLES + 1) if members and all(rnd.has_score(m, h) for m in members)]
        total = 0.0
        for h in holes:
            if mode == "stroke":
                par = rnd.course.hole(h).par
                total += min(min(_net(rnd, m, h, allowance), par + 2) for m in members)  # cap at net double bogey
            else:
                total += max(_points(rnd, m, h, allowance) for m in members)
        rows.append({"Team": t["name"], "Players": ", ".join(members), "Score": total, "Thru": len(holes)})
    higher_better = mode != "stroke"
    rows.sort(key=lambda r: ((-r["Score"]) if higher_better else r["Score"], r["Team"]))
    for r in rows:
        r["Score"] = int(r["Score"]) if float(r["Score"]).is_integer() else round(r["Score"], 1)
    winners: list[str] = []
    if rows and any(r["Thru"] for r in rows):
        best = rows[0]["Score"]
        for r in rows:
            if r["Score"] == best:
                winners += next(t["players"] for t in teams if t["name"] == r["Team"])
    everyone = [p for t in teams for p in t.get("players", [])]
    notes = _provisional(min((r["Thru"] for r in rows), default=0))
    notes.append(f"{'Stableford points' if higher_better else 'Net strokes'}, {int(allowance * 100)}% handicap allowance.")
    return GameResult("best_ball", GAME_TITLES["best_ball"], rows, _pot(everyone, winners, stake), notes)


# ---------------------------------------------------------------- Wolf
def wolf_for_hole(order: list[str], hole: int) -> str:
    return order[(hole - 1) % len(order)]


def wolf(rnd, cfg: dict) -> GameResult:
    order = list(cfg.get("order") or rnd.player_names)
    if len(order) != 4:
        raise ValueError("Wolf needs exactly 4 players in the tee order.")
    _check_players(rnd, order, "Wolf")
    value = cents(cfg.get("value", 0))
    mult = int(cfg.get("lone_multiplier", 2))
    allowance = float(cfg.get("allowance", 1.0))
    use_net = bool(cfg.get("use_net", True))
    units = {p: 0 for p in order}
    log: list[str] = []
    played = 0
    for h in range(1, N_HOLES + 1):
        if h not in rnd.wolf_picks or not all(rnd.has_score(p, h) for p in order):
            continue
        played += 1
        w = wolf_for_hole(order, h)
        partner = rnd.wolf_picks[h] or None
        if partner is not None and partner not in order:
            raise ValueError(f"Wolf: hole {h} partner {partner} is not in the group.")
        wolf_side = [w] + ([partner] if partner else [])
        others = [p for p in order if p not in wolf_side]
        ws = min(_net(rnd, p, h, allowance, use_net) for p in wolf_side)
        os_ = min(_net(rnd, p, h, allowance, use_net) for p in others)
        if ws == os_:
            log.append(f"H{h}: halved")
            continue
        wolf_won = ws < os_
        if partner:
            winners, losers = (wolf_side, others) if wolf_won else (others, wolf_side)
            for p in winners:
                units[p] += 1
            for p in losers:
                units[p] -= 1
            log.append(f"H{h}: {' & '.join(winners)} win")
        else:
            sign = 1 if wolf_won else -1
            units[w] += sign * 3 * mult
            for p in others:
                units[p] -= sign * mult
            log.append(f"H{h}: Lone Wolf {w} {'wins' if wolf_won else 'loses'} (x{mult})")
    rows = [{"Player": p, "Points": units[p]} for p in order]
    rows.sort(key=lambda r: (-r["Points"], r["Player"]))
    notes = _provisional(played) + log[-6:]
    return GameResult("wolf", GAME_TITLES["wolf"], rows, {p: units[p] * value for p in order}, notes)


# ---------------------------------------------------------------- Nassau
def nassau(rnd, cfg: dict) -> GameResult:
    sides = [list(s) for s in (cfg.get("sides") or [])]
    if len(sides) != 2 or not sides[0] or not sides[1] or len(sides[0]) != len(sides[1]):
        raise ValueError("Nassau needs two equal sides (1v1 or 2v2).")
    _check_players(rnd, sides[0] + sides[1], "Nassau")
    if set(sides[0]) & set(sides[1]):
        raise ValueError("Nassau: a player can't be on both sides.")
    stake = cents(cfg.get("stake", 0))
    allowance = float(cfg.get("allowance", 1.0))
    use_net = bool(cfg.get("use_net", True))
    auto_press = bool(cfg.get("auto_press", True))
    trigger = int(cfg.get("press_trigger", 2))
    label = [" & ".join(s) for s in sides]

    bets = [
        {"name": "Front 9", "start": 1, "end": 9, "margin": 0, "pressed": False},
        {"name": "Back 9", "start": 10, "end": 18, "margin": 0, "pressed": False},
        {"name": "Overall", "start": 1, "end": 18, "margin": 0, "pressed": True},  # no presses on the overall
    ]
    holes = _sequential_holes(rnd, sides[0] + sides[1])
    for h in holes:
        a = min(_net(rnd, p, h, allowance, use_net) for p in sides[0])
        b = min(_net(rnd, p, h, allowance, use_net) for p in sides[1])
        delta = 0 if a == b else (1 if a < b else -1)
        new_bets = []
        for bet in bets:
            if bet["start"] <= h <= bet["end"]:
                bet["margin"] += delta
                if auto_press and not bet["pressed"] and abs(bet["margin"]) >= trigger and h < bet["end"]:
                    bet["pressed"] = True
                    new_bets.append(
                        {"name": f"Press (H{h + 1}-{bet['end']})", "start": h + 1, "end": bet["end"], "margin": 0, "pressed": False}
                    )
        bets.extend(new_bets)

    last = holes[-1] if holes else 0
    bal = {p: 0 for p in sides[0] + sides[1]}
    rows = []
    for bet in bets:
        m = bet["margin"]
        done = last >= bet["end"]
        status = "All square" if m == 0 else f"{label[0] if m > 0 else label[1]} {abs(m)} UP"
        rows.append({"Bet": bet["name"], "Status": status, "Final": "Yes" if done else "Live"})
        if m != 0:
            win, lose = (sides[0], sides[1]) if m > 0 else (sides[1], sides[0])
            for p in win:
                bal[p] += stake
            for p in lose:
                bal[p] -= stake
    notes = _provisional(len(holes))
    notes.append(f"{label[0]} vs {label[1]}: ${stake / 100:.2f} per bet" + (f", auto-press at {trigger} down." if auto_press else "."))
    return GameResult("nassau", GAME_TITLES["nassau"], rows, bal, notes)


GAMES: dict[str, Callable[[Any, dict], GameResult]] = {
    "stableford": stableford,
    "ambrose": ambrose,
    "skins": skins,
    "best_ball": best_ball,
    "wolf": wolf,
    "nassau": nassau,
}

INDIVIDUAL_GAMES = ("stableford", "skins", "best_ball", "wolf", "nassau")


def validate_games(games: dict) -> list[str]:
    problems = []
    if "ambrose" in games and any(k in games for k in INDIVIDUAL_GAMES):
        problems.append("Ambrose uses one team score per hole, so it can't be combined with individual-score games.")
    for k in games:
        if k not in GAMES:
            problems.append(f"Unknown game: {k}")
    return problems


def compute_all(rnd) -> list[GameResult]:
    """Run every enabled game; a misconfigured game returns an error result with zero balances."""
    out = []
    for key, cfg in rnd.games.items():
        fn = GAMES.get(key)
        if fn is None:
            continue
        try:
            out.append(fn(rnd, cfg or {}))
        except (ValueError, KeyError) as e:
            out.append(GameResult(key, GAME_TITLES.get(key, key), error=str(e)))
    return out
