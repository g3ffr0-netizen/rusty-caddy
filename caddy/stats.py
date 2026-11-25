"""Round stats summary (GIR, fairways, putts, penalties, blow-ups) and Fines & Shouts tally."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fines import fines_by_player, shouts
from .handicap import playing_handicap, strokes_on_hole
from .models import N_HOLES, Round


@dataclass
class RoundStats:
    player: str
    holes_scored: int
    gross_total: int
    par_played: int
    to_par: int | None
    pickups: int
    blow_ups: int
    fir_hit: int
    fir_tracked: int
    gir_hit: int
    gir_tracked: int
    total_putts: int
    putts_tracked: int
    three_putts: int
    total_penalties: int
    fines_count: int
    fines_total_cents: int
    shouts_count: int
    player_fines_count: int
    player_fines_cents: int
    player_shouts_count: int
    shouts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def fir_pct(self) -> int | None:
        return round(100 * self.fir_hit / self.fir_tracked) if self.fir_tracked else None

    @property
    def gir_pct(self) -> int | None:
        return round(100 * self.gir_hit / self.gir_tracked) if self.gir_tracked else None

    @property
    def putts_per_hole(self) -> float | None:
        return round(self.total_putts / self.putts_tracked, 2) if self.putts_tracked else None


def format_ratio(hit: int, tracked: int) -> str:
    if tracked <= 0:
        return "—"
    pct = round(100 * hit / tracked)
    return f"{hit}/{tracked} ({pct}%)"


def format_to_par(to_par: int | None) -> str:
    if to_par is None:
        return "—"
    if to_par == 0:
        return "E"
    return f"+{to_par}" if to_par > 0 else str(to_par)


def blow_up_count(rnd: Round, player_name: str) -> int:
    """Count holes with net double bogey or worse (including pick-ups)."""
    try:
        player = rnd.player(player_name)
    except KeyError:
        return 0
    ph = playing_handicap(player.handicap)
    blow = 0
    for hh in range(1, N_HOLES + 1):
        if rnd.has_score(player_name, hh):
            g = rnd.gross(player_name, hh)
            hl = rnd.course.hole(hh)
            if g is None or g - strokes_on_hole(ph, hl.stroke_index) >= hl.par + 2:
                blow += 1
    return blow


def fines_and_shouts_tally(rnd: Round) -> dict[str, Any]:
    """Running group totals for Fines & Shouts."""
    by_player = fines_by_player(rnd)
    sh = shouts(rnd)
    return {
        "count": len(rnd.fines),
        "total_cents": sum(int(f.get("amount_cents", 0)) for f in rnd.fines),
        "shouts_count": len(sh),
        "shouts": sh,
        "by_player": by_player,
    }


def round_stats_summary(rnd: Round, player_name: str | None = None) -> RoundStats:
    """Compute GIR, fairways, putts, penalties, score-to-par, blow-ups, and running Fines & Shouts."""
    name = player_name or (rnd.players[0].name if rnd.players else "")
    gross_total = 0
    par_played = 0
    holes_scored = 0
    pickups = 0

    fir_hit = fir_tracked = 0
    gir_hit = gir_tracked = 0
    total_putts = putts_tracked = three_putts = 0
    total_penalties = 0

    if name:
        for hh in range(1, N_HOLES + 1):
            hl = rnd.course.hole(hh)
            if rnd.has_score(name, hh):
                holes_scored += 1
                g = rnd.gross(name, hh)
                if g is None:
                    pickups += 1
                else:
                    gross_total += g
                    par_played += hl.par
            st = rnd.get_hole_stats(name, hh)
            if hl.par >= 4 and st["fir"] is not None:
                fir_tracked += 1
                if st["fir"]:
                    fir_hit += 1
            if st["gir"] is not None:
                gir_tracked += 1
                if st["gir"]:
                    gir_hit += 1
            if st["putts"] is not None:
                putts_tracked += 1
                total_putts += int(st["putts"])
                if int(st["putts"]) >= 3:
                    three_putts += 1
            total_penalties += int(st["penalties"] or 0)

    to_par = (gross_total - par_played) if par_played > 0 else None
    tally = fines_and_shouts_tally(rnd)
    p_fines = tally["by_player"].get(name, {"count": 0, "cents": 0, "shouts": 0})

    return RoundStats(
        player=name,
        holes_scored=holes_scored,
        gross_total=gross_total,
        par_played=par_played,
        to_par=to_par,
        pickups=pickups,
        blow_ups=blow_up_count(rnd, name) if name else 0,
        fir_hit=fir_hit,
        fir_tracked=fir_tracked,
        gir_hit=gir_hit,
        gir_tracked=gir_tracked,
        total_putts=total_putts,
        putts_tracked=putts_tracked,
        three_putts=three_putts,
        total_penalties=total_penalties,
        fines_count=tally["count"],
        fines_total_cents=tally["total_cents"],
        shouts_count=tally["shouts_count"],
        player_fines_count=int(p_fines["count"]),
        player_fines_cents=int(p_fines["cents"]),
        player_shouts_count=int(p_fines["shouts"]),
        shouts=tally["shouts"],
    )
