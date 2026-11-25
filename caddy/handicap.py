"""Handicap strokes and Stableford points."""
from __future__ import annotations

import math

N_HOLES = 18


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def playing_handicap(handicap: float, allowance: float = 1.0) -> int:
    """Course/daily handicap scaled by a format allowance (e.g. 0.85 for four-ball)."""
    return round_half_up(float(handicap or 0) * float(allowance))


def strokes_on_hole(playing_hcp: int, stroke_index: int, n_holes: int = N_HOLES) -> int:
    """Strokes received (positive) or given back (negative, plus handicaps) on a hole."""
    if playing_hcp >= 0:
        base, rem = divmod(playing_hcp, n_holes)
        return base + (1 if stroke_index <= rem else 0)
    base, rem = divmod(-playing_hcp, n_holes)
    return -(base + (1 if stroke_index > n_holes - rem else 0))


def stableford_points(gross: int | None, par: int, strokes: int) -> int:
    """2 points for net par, +1 per stroke better, 0 for net double bogey or a pick-up."""
    if gross is None:
        return 0
    return max(0, 2 + par - (gross - strokes))
