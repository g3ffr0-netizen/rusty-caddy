"""Club-distance table and the distance-aware mental caddy."""
from __future__ import annotations

from dataclasses import dataclass

# Typical carry distances (metres) for a mid-handicap amateur. Fully editable in Setup.
DEFAULT_CLUBS: list[list] = [
    ["Driver", 210],
    ["3 Wood", 190],
    ["5 Wood", 175],
    ["4 Hybrid", 165],
    ["5 Iron", 155],
    ["6 Iron", 145],
    ["7 Iron", 135],
    ["8 Iron", 125],
    ["9 Iron", 115],
    ["PW", 100],
    ["GW", 85],
    ["SW", 70],
    ["LW", 55],
]

WIND_DIRECTIONS = ("None", "Headwind", "Tailwind", "Cross")
MISSES = ("Straight", "Slice", "Hook")

# Rules of thumb: ~1% per mph into the wind, ~0.5% per mph downwind (1 mph = 1.609 km/h).
HEAD_PER_KMH = 0.01 / 1.609
TAIL_PER_KMH = 0.005 / 1.609
CROSS_PER_KMH = 0.0025 / 1.609


def normalise_clubs(clubs: list) -> list[tuple[str, int]]:
    """Clean a user-edited club table: drop blanks, coerce ints, sort longest first."""
    out: list[tuple[str, int]] = []
    for row in clubs or []:
        try:
            name = str(row[0]).strip()
            carry = int(round(float(row[1])))
        except (TypeError, ValueError, IndexError):
            continue
        if name and carry > 0:
            out.append((name, carry))
    out.sort(key=lambda c: -c[1])
    return out or [tuple(c) for c in DEFAULT_CLUBS]


def plays_like(distance_m: float, wind_kmh: float = 0.0, wind_dir: str = "None", elevation_m: float = 0.0) -> float:
    """Effective distance after wind and elevation (uphill positive)."""
    d = float(distance_m)
    w = max(0.0, float(wind_kmh))
    if wind_dir == "Headwind":
        d *= 1 + HEAD_PER_KMH * w
    elif wind_dir == "Tailwind":
        d *= 1 - TAIL_PER_KMH * w
    elif wind_dir == "Cross":
        d *= 1 + CROSS_PER_KMH * w
    d += float(elevation_m)
    return max(0.0, d)


def pick_club(clubs: list, target_m: float) -> tuple[str, int, bool]:
    """Shortest club that carries the target. Returns (club, carry, reachable)."""
    table = normalise_clubs(clubs)
    for name, carry in reversed(table):  # shortest first
        if carry >= target_m:
            return name, carry, True
    name, carry = table[0]
    return name, carry, False


def _club_index(table: list[tuple[str, int]], name: str) -> int:
    for i, (n, _) in enumerate(table):
        if n == name:
            return i
    return len(table) - 1


@dataclass
class Advice:
    club: str
    carry_m: int
    plays_like_m: int
    reachable: bool
    strategy: str
    aim_tip: str
    next_shot: str


def get_caddy_advice(
    clubs: list,
    par: int,
    distance_m: float,
    wind_kmh: float = 0.0,
    wind_dir: str = "None",
    pressure: int = 5,
    miss: str = "Straight",
    elevation_m: float = 0.0,
) -> Advice:
    table = normalise_clubs(clubs)
    pl = plays_like(distance_m, wind_kmh, wind_dir, elevation_m)
    max_carry = table[0][1]

    if pl > max_carry:
        # Can't get there in one: this is a positional (tee / lay-up) shot.
        if pressure > 7 or wind_kmh > 20:
            target = 0.72 * max_carry
            name, carry = min(table, key=lambda c: abs(c[1] - target))
            strategy = "🚩 FAKE FAVOURITE: Pressure/wind is high. Swing smooth, keep it in play. Do not be a hero."
        elif par >= 5 and pressure <= 5:
            name, carry = table[0]
            strategy = "🔥 VALUE PLAY: Let the big dog eat. Aim for the widest part of the fairway."
        else:
            name, carry = table[1] if len(table) > 1 else table[0]
            strategy = "🟢 STANDARD PLAY: Fairway first. Set up a good approach shot."
        remaining = pl - carry
        if remaining > max_carry:
            wedge = next((c for c in table if c[1] <= 105), table[-1])
            next_shot = f"Two more shots needed: plan to leave yourself ~{wedge[1]} m ({wedge[0]})."
        else:
            nxt, nxt_carry, _ = pick_club(table, remaining)
            next_shot = f"Leaves ~{int(round(remaining))} m: likely a {nxt} in."
        reachable = False
    else:
        name, carry, reachable = pick_club(table, pl)
        if pressure >= 8:
            idx = _club_index(table, name)
            if idx > 0:
                name, carry = table[idx - 1]
            strategy = "🧘 CLUB UP & SWING 80%: Pressure is high. One more club, smooth tempo, centre of the green."
        elif par == 3:
            strategy = "🔥 VALUE PLAY: Aim for the centre of the green. Pin-hunting is for the pros."
        else:
            strategy = f"🎯 GREEN LIGHT: Plays like {int(round(pl))} m. Commit to the number, centre of the green."
        next_shot = "Two-putt from the middle is a win."

    aim_tip = ""
    if miss == "Slice":
        aim_tip = "FIX: Aim left, close the face."
    elif miss == "Hook":
        aim_tip = "FIX: Aim right, open the face."

    return Advice(
        club=name,
        carry_m=int(carry),
        plays_like_m=int(round(pl)),
        reachable=reachable,
        strategy=strategy,
        aim_tip=aim_tip,
        next_shot=next_shot,
    )


def mental_state(pressure: int) -> str:
    if pressure >= 8:
        return "🚨 SYSTEM OVERRIDE: Step back. 3 deep breaths. Do not swing until your heart rate drops."
    if pressure >= 5:
        return "🟡 MODERATE PRESSURE: Stick to your pre-shot routine."
    return "🟢 CALM STATE: Trust your swing. Execute."
