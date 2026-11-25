"""Club-distance table, wind plays-like physics, and the distance-aware mental caddy."""
from __future__ import annotations

import math
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

COMPASS_BEARINGS: dict[str, float] = {
    "N": 0.0,
    "NE": 45.0,
    "E": 90.0,
    "SE": 135.0,
    "S": 180.0,
    "SW": 225.0,
    "W": 270.0,
    "NW": 315.0,
}

# Rules of thumb: ~1% per mph into the wind, ~0.5% per mph downwind (1 mph = 1.609 km/h).
HEAD_PER_KMH = 0.01 / 1.609
TAIL_PER_KMH = 0.005 / 1.609
CROSS_PER_KMH = 0.0025 / 1.609


def nearest_compass_point(deg: float | None) -> str:
    """Map any bearing in degrees to the nearest 8-point compass direction."""
    if deg is None:
        return "N"
    pts = list(COMPASS_BEARINGS)
    idx = int((float(deg) % 360.0) / 45.0 + 0.5) % len(pts)
    return pts[idx]


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
    """Effective distance after manual wind direction and elevation (uphill positive)."""
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


@dataclass
class WindAdjustment:
    raw_distance_m: float
    plays_like_m: float
    wind_effect_m: float
    elevation_m: float
    wind_kmh: float
    gust_kmh: float | None
    wind_dir_deg: float
    shot_bearing_deg: float
    headwind_kmh: float  # positive = into the wind, negative = downwind
    crosswind_kmh: float  # positive = wind from right (pushes left), negative = wind from left (pushes right)
    relative_label: str
    gust_plays_like_m: float | None = None
    aim_drift_tip: str = ""


def decompose_wind(wind_kmh: float, wind_dir_deg: float, shot_bearing_deg: float) -> tuple[float, float]:
    """Decompose meteorological wind (coming FROM wind_dir_deg) against shot direction (TOWARD shot_bearing_deg).

    Returns (headwind_kmh, crosswind_kmh):
      - headwind_kmh > 0: headwind (hurting); < 0: tailwind (helping)
      - crosswind_kmh > 0: from right (drifts ball left); < 0: from left (drifts ball right)
    """
    speed = max(0.0, float(wind_kmh))
    delta_rad = math.radians((float(wind_dir_deg) - float(shot_bearing_deg)) % 360.0)
    head = speed * math.cos(delta_rad)
    cross = speed * math.sin(delta_rad)
    # Clean floating-point noise near exact cardinals
    if abs(head) < 1e-9:
        head = 0.0
    if abs(cross) < 1e-9:
        cross = 0.0
    return head, cross


def _wind_multiplier(headwind_kmh: float, crosswind_kmh: float) -> float:
    longitudinal = headwind_kmh * HEAD_PER_KMH if headwind_kmh >= 0 else headwind_kmh * TAIL_PER_KMH
    cross_drag = abs(crosswind_kmh) * CROSS_PER_KMH
    return max(0.5, 1.0 + longitudinal + cross_drag)


def _describe_relative_wind(head: float, cross: float, wind_kmh: float) -> tuple[str, str]:
    if wind_kmh < 2.0:
        return "Calm", ""
    side = ""
    drift_tip = ""
    if abs(cross) >= 5.0:
        if cross > 0:
            side = "from right"
            drift_tip = f"Crosswind ~{round(abs(cross))} km/h from right — favour right side (ball drifts left)."
        else:
            side = "from left"
            drift_tip = f"Crosswind ~{round(abs(cross))} km/h from left — favour left side (ball drifts right)."
    abs_h, abs_c = abs(head), abs(cross)
    if abs_h >= 2.0 * abs_c:
        label = "Headwind" if head > 0 else "Tailwind"
    elif abs_c >= 2.0 * abs_h:
        label = f"Crosswind ({side})" if side else "Crosswind"
    else:
        kind = "Quartering headwind" if head > 0 else "Quartering tailwind"
        label = f"{kind} ({side})" if side else kind
    return label, drift_tip


def wind_plays_like(
    distance_m: float,
    wind_kmh: float,
    wind_dir_deg: float,
    shot_bearing_deg: float,
    elevation_m: float = 0.0,
    gust_kmh: float | None = None,
) -> WindAdjustment:
    """Compute plays-like distance from live Open-Meteo wind speed/direction and shot bearing."""
    d = float(distance_m)
    w = max(0.0, float(wind_kmh))
    w_dir = float(wind_dir_deg) % 360.0
    s_dir = float(shot_bearing_deg) % 360.0
    elev = float(elevation_m)

    head, cross = decompose_wind(w, w_dir, s_dir)
    mult = _wind_multiplier(head, cross)
    wind_only_m = d * mult
    total_m = max(0.0, wind_only_m + elev)
    wind_effect_m = wind_only_m - d

    gust_val = float(gust_kmh) if gust_kmh is not None else None
    gust_pl: float | None = None
    if gust_val is not None and gust_val > w + 1.0:
        g_head, g_cross = decompose_wind(gust_val, w_dir, s_dir)
        gust_pl = max(0.0, d * _wind_multiplier(g_head, g_cross) + elev)

    label, drift_tip = _describe_relative_wind(head, cross, w)
    return WindAdjustment(
        raw_distance_m=d,
        plays_like_m=total_m,
        wind_effect_m=wind_effect_m,
        elevation_m=elev,
        wind_kmh=w,
        gust_kmh=gust_val,
        wind_dir_deg=w_dir,
        shot_bearing_deg=s_dir,
        headwind_kmh=head,
        crosswind_kmh=cross,
        relative_label=label,
        gust_plays_like_m=gust_pl,
        aim_drift_tip=drift_tip,
    )


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
    wind_adjustment: WindAdjustment | None = None


def get_caddy_advice(
    clubs: list,
    par: int,
    distance_m: float,
    wind_kmh: float = 0.0,
    wind_dir: str = "None",
    pressure: int = 5,
    miss: str = "Straight",
    elevation_m: float = 0.0,
    wind_dir_deg: float | None = None,
    shot_bearing_deg: float | None = None,
    gust_kmh: float | None = None,
) -> Advice:
    table = normalise_clubs(clubs)
    wind_adj: WindAdjustment | None = None
    if wind_dir_deg is not None and shot_bearing_deg is not None:
        wind_adj = wind_plays_like(distance_m, wind_kmh, wind_dir_deg, shot_bearing_deg, elevation_m, gust_kmh)
        pl = wind_adj.plays_like_m
    else:
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

    tips: list[str] = []
    if miss == "Slice":
        tips.append("FIX: Aim left, close the face.")
    elif miss == "Hook":
        tips.append("FIX: Aim right, open the face.")
    if wind_adj and wind_adj.aim_drift_tip:
        tips.append(wind_adj.aim_drift_tip)

    return Advice(
        club=name,
        carry_m=int(carry),
        plays_like_m=int(round(pl)),
        reachable=reachable,
        strategy=strategy,
        aim_tip=" ".join(tips),
        next_shot=next_shot,
        wind_adjustment=wind_adj,
    )


def mental_state(pressure: int) -> str:
    if pressure >= 8:
        return "🚨 SYSTEM OVERRIDE: Step back. 3 deep breaths. Do not swing until your heart rate drops."
    if pressure >= 5:
        return "🟡 MODERATE PRESSURE: Stick to your pre-shot routine."
    return "🟢 CALM STATE: Trust your swing. Execute."
