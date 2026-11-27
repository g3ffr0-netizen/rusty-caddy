"""Pure-Python GPS rangefinder, slope/lie plays-like physics, and 3-Club Challenge recommender."""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Sequence

from .clubs import (
    Advice,
    get_caddy_advice,
    nearest_compass_point,
    normalise_clubs,
    plays_like,
    wind_plays_like,
)

EARTH_RADIUS_M = 6_371_000.0
DEFAULT_GREEN_HALF_DEPTH_M = 12.0

# Default 3-Club Challenge bag (editable in UI): 3 Wood (also putter), 7 Iron, 60° Wedge.
THREE_CLUB_DEFAULT: list[list] = [
    ["3 Wood", 190],
    ["7 Iron", 135],
    ["60° Wedge", 65],
]

# Lie conditions tailored for hilly, tight-grass courses like Mangrove Mountain.
# Each entry: (plays_like_delta_m, aim_and_setup_tip)
LIE_CONDITIONS: dict[str, tuple[float, str]] = {
    "Flat / Fairway": (0.0, ""),
    "Tight / Thin Grass": (
        0.0,
        "Tight/thin lie: clip it clean (ball slightly back, quiet hands). Avoid digging the 60° — consider a 7-iron bump-and-run if green is open.",
    ),
    "Uphill Lie": (
        8.0,
        "Uphill lie: adds loft (+~8 m plays-like) & tends to pull left. Swing along the slope, aim slightly right, take one extra club.",
    ),
    "Downhill Lie": (
        -6.0,
        "Downhill lie: delofts club (-~6 m carry, extra roll) & tends to leak right. Match shoulders to slope, chase it in low.",
    ),
    "Ball Above Feet": (
        2.0,
        "Ball above feet: pulls/hooks left. Choke down 2-3 cm, stand taller, aim right of target.",
    ),
    "Ball Below Feet": (
        4.0,
        "Ball below feet: pushes/slices right. Flex knees, stay down through impact, aim left of target.",
    ),
}


@dataclass(frozen=True)
class GPSFix:
    lat: float
    lon: float
    accuracy_m: float = 5.0
    elevation_m: float | None = None


@dataclass(frozen=True)
class GreenTargets:
    middle_lat: float
    middle_lon: float
    front_lat: float | None = None
    front_lon: float | None = None
    back_lat: float | None = None
    back_lon: float | None = None
    green_elevation_m: float | None = None


@dataclass(frozen=True)
class RangefinderReading:
    front_m: int
    middle_m: int
    back_m: int
    plays_like_front_m: int
    plays_like_middle_m: int
    plays_like_back_m: int
    bearing_deg: float
    compass: str
    elevation_delta_m: float
    lie: str
    lie_tip: str
    accuracy_badge: str


@dataclass(frozen=True)
class ThreeClubShot:
    club: str
    shot_type: str
    swing_feel: str
    plays_like_m: int
    strategy: str
    lie_tip: str
    next_shot: str


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 lat/lon coordinates."""
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlam = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    a = min(1.0, max(0.0, a))
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing in degrees [0, 360) from point 1 toward point 2."""
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dlam = math.radians(float(lon2) - float(lon1))
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return 0.0
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def accuracy_badge(accuracy_m: float | None) -> str:
    """Human-readable GPS fix quality label."""
    if accuracy_m is None or not math.isfinite(float(accuracy_m)):
        return "MANUAL"
    acc = float(accuracy_m)
    if acc <= 6.0:
        return f"GOOD (±{round(acc)} m)"
    if acc <= 12.0:
        return f"OK (±{round(acc)} m)"
    if acc <= 15.0:
        return f"FAIR (±{round(acc)} m)"
    return f"POOR (±{round(acc)} m)"


def smooth_gps_fixes(
    fixes: Sequence[GPSFix],
    max_accuracy_m: float = 15.0,
) -> GPSFix | None:
    """Filter noisy fixes (> max_accuracy_m) and return a robust median fix."""
    if not fixes:
        return None
    good = [
        f
        for f in fixes
        if math.isfinite(f.lat)
        and math.isfinite(f.lon)
        and math.isfinite(f.accuracy_m)
        and 0.0 <= f.accuracy_m <= max_accuracy_m
    ]
    if not good:
        # Fall back to best single fix if all exceed threshold
        finite = [f for f in fixes if math.isfinite(f.lat) and math.isfinite(f.lon)]
        if not finite:
            return None
        return min(finite, key=lambda f: f.accuracy_m if math.isfinite(f.accuracy_m) else 9999.0)

    med_lat = float(median(f.lat for f in good))
    med_lon = float(median(f.lon for f in good))
    med_acc = float(median(f.accuracy_m for f in good))
    elevs = [f.elevation_m for f in good if f.elevation_m is not None and math.isfinite(f.elevation_m)]
    med_elev = float(median(elevs)) if elevs else None
    return GPSFix(lat=med_lat, lon=med_lon, accuracy_m=med_acc, elevation_m=med_elev)


def measure_shot_m(start_fix: GPSFix, end_fix: GPSFix) -> int:
    """Return rounded shot distance in metres between two marked ball GPS fixes."""
    return int(round(haversine_m(start_fix.lat, start_fix.lon, end_fix.lat, end_fix.lon)))


def compute_rangefinder_reading(
    player: GPSFix,
    green: GreenTargets,
    *,
    wind_kmh: float = 0.0,
    wind_dir: str = "None",
    wind_dir_deg: float | None = None,
    elevation_override_m: float | None = None,
    lie: str = "Flat / Fairway",
    green_half_depth_m: float = DEFAULT_GREEN_HALF_DEPTH_M,
) -> RangefinderReading:
    """Compute Front / Middle / Back raw & plays-like distances from GPS + slope/wind/lie."""
    mid_raw = haversine_m(player.lat, player.lon, green.middle_lat, green.middle_lon)
    brg = bearing_deg(player.lat, player.lon, green.middle_lat, green.middle_lon)
    comp = nearest_compass_point(brg)

    if green.front_lat is not None and green.front_lon is not None:
        front_raw = haversine_m(player.lat, player.lon, green.front_lat, green.front_lon)
    else:
        front_raw = max(0.0, mid_raw - float(green_half_depth_m))

    if green.back_lat is not None and green.back_lon is not None:
        back_raw = haversine_m(player.lat, player.lon, green.back_lat, green.back_lon)
    else:
        back_raw = mid_raw + float(green_half_depth_m)

    if elevation_override_m is not None:
        elev_delta = float(elevation_override_m)
    elif player.elevation_m is not None and green.green_elevation_m is not None:
        elev_delta = float(green.green_elevation_m) - float(player.elevation_m)
    else:
        elev_delta = 0.0

    lie_delta, lie_tip = LIE_CONDITIONS.get(lie, (0.0, ""))

    def _pl(raw_d: float) -> int:
        if wind_dir_deg is not None:
            adj = wind_plays_like(raw_d, wind_kmh, wind_dir_deg, brg, elevation_m=elev_delta)
            base_pl = adj.plays_like_m
        else:
            base_pl = plays_like(raw_d, wind_kmh=wind_kmh, wind_dir=wind_dir, elevation_m=elev_delta)
        return max(0, int(round(base_pl + lie_delta)))

    return RangefinderReading(
        front_m=int(round(front_raw)),
        middle_m=int(round(mid_raw)),
        back_m=int(round(back_raw)),
        plays_like_front_m=_pl(front_raw),
        plays_like_middle_m=_pl(mid_raw),
        plays_like_back_m=_pl(back_raw),
        bearing_deg=round(brg, 1),
        compass=comp,
        elevation_delta_m=round(elev_delta, 1),
        lie=lie,
        lie_tip=lie_tip,
        accuracy_badge=accuracy_badge(player.accuracy_m),
    )


def recommend_three_club_shot(
    plays_like_m: float,
    *,
    three_clubs: Sequence[Sequence] = THREE_CLUB_DEFAULT,
    lie: str = "Flat / Fairway",
    wind_kmh: float = 0.0,
    pressure: int = 5,
    on_green_or_fringe: bool = False,
) -> ThreeClubShot:
    """Smart shot & club recommendation for a 3-Club Challenge (e.g., 3W / 7I / 60°).

    Handles Mangrove Mountain's tight/thin grass and sloping lies by preferring
    controlled knockdown 7-irons and 3-wood putts/bumpers over risky thin-lie 60° shots.
    """
    table = normalise_clubs(list(three_clubs))
    # Expect longest = Wood/Putter, middle = Iron, shortest = Wedge (graceful fallback if <3)
    wood_name, wood_carry = table[0]
    iron_name, iron_carry = table[1] if len(table) >= 2 else table[0]
    wedge_name, wedge_carry = table[-1]

    d = max(0.0, float(plays_like_m))
    lie_delta, lie_tip = LIE_CONDITIONS.get(lie, (0.0, ""))
    is_tight = "tight" in lie.lower() or "thin" in lie.lower()

    if on_green_or_fringe or d <= 18.0:
        return ThreeClubShot(
            club=f"{wood_name} (Putter)",
            shot_type="Putted / Texas Wedge",
            swing_feel="Choke down, hands high, pure pendulum stroke",
            plays_like_m=int(round(d)),
            strategy=f"⛳ PUTT WITH {wood_name.upper()}: Flat sole glides cleanly off tight fringes and greens — zero chunk risk.",
            lie_tip=lie_tip,
            next_shot="Lag it stone dead inside 1 m.",
        )

    if d <= wedge_carry + 4:
        if is_tight or wind_kmh >= 22:
            pct = max(20, min(65, int(round((d / max(1, iron_carry)) * 100))))
            return ThreeClubShot(
                club=iron_name,
                shot_type="Low Bump-and-Run",
                swing_feel=f"~{pct}% putting-style chip, ball back, low release",
                plays_like_m=int(round(d)),
                strategy=f"🎯 TIGHT-LIE SMART PLAY: Keep it under the wind/off thin grass with a {iron_name} bump-and-run instead of risking a thin/fat {wedge_name}.",
                lie_tip=lie_tip,
                next_shot=f"Let it land short and release to the flag ({wood_name} putt to finish).",
            )
        pct = max(35, min(100, int(round((d / max(1, wedge_carry)) * 100))))
        return ThreeClubShot(
            club=wedge_name,
            shot_type="Controlled Pitch" if pct < 90 else "Full Wedge",
            swing_feel=f"~{pct}% smooth tempo, accelerate through",
            plays_like_m=int(round(d)),
            strategy=f"🎯 WEDGE WINDOW: {int(round(d))} m plays right in your {wedge_name} zone (max {wedge_carry} m). Commit to the finish.",
            lie_tip=lie_tip,
            next_shot=f"Middle of the green, then smooth {wood_name} putt.",
        )

    if d <= iron_carry + 8:
        pct = max(55, min(100, int(round((d / max(1, iron_carry)) * 100))))
        shot_lbl = "Punch / Knockdown" if (pct < 85 or wind_kmh >= 18 or is_tight) else "Full Iron"
        return ThreeClubShot(
            club=iron_name,
            shot_type=shot_lbl,
            swing_feel=f"~{pct}% swing, grip down 2 cm, hold finish low" if shot_lbl != "Full Iron" else "Smooth 90% rhythm, centre of green",
            plays_like_m=int(round(d)),
            strategy=f"🔥 3-CLUB MONEY SHOT: {shot_lbl} {iron_name} owns the {wedge_carry + 5}-{iron_carry + 8} m gap — way safer off Mangrove slopes than forcing a wedge.",
            lie_tip=lie_tip,
            next_shot=f"Hit the fat part of the green, two-putt with {wood_name}.",
        )

    # Beyond 7-iron carry: 3-Wood vs 7-Iron layup
    if d <= wood_carry + 10 and pressure <= 7 and not (is_tight and d > wood_carry - 10):
        return ThreeClubShot(
            club=wood_name,
            shot_type="Full / Swept Fairway Wood",
            swing_feel="Wide arc, shallow sweep, smooth 85% tempo",
            plays_like_m=int(round(d)),
            strategy=f"🔥 GO ZONE: {wood_name} reaches ({wood_carry} m carry). Aim for the widest side of the green.",
            lie_tip=lie_tip,
            next_shot=f"Chip or {wood_name} putt from around the green.",
        )

    if pressure >= 8 or is_tight:
        rem = max(0, int(round(d - iron_carry)))
        return ThreeClubShot(
            club=iron_name,
            shot_type="Smart Positional Layup",
            swing_feel="Smooth full iron to widest fairway shelf",
            plays_like_m=int(round(d)),
            strategy=f"🧘 COURSE MANAGEMENT: Tight/high-pressure spot — hit {iron_name} ({iron_carry} m) into play rather than gambling on a thin-lie {wood_name}.",
            lie_tip=lie_tip,
            next_shot=f"Leaves ~{rem} m in (perfect for {wedge_name if rem <= wedge_carry else iron_name}).",
        )

    rem = max(0, int(round(d - wood_carry)))
    return ThreeClubShot(
        club=wood_name,
        shot_type="Fairway Advance / Tee Shot",
        swing_feel="Smooth 85% fairway finder",
        plays_like_m=int(round(d)),
        strategy=f"🟢 ADVANCE IT: Smooth {wood_name} ({wood_carry} m) down the widest line.",
        lie_tip=lie_tip,
        next_shot=f"Leaves ~{rem} m in ({wedge_name if rem <= wedge_carry else iron_name}).",
    )
