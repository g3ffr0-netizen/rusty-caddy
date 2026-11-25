"""Core data model (pure Python, JSON-serialisable)."""
from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .clubs import DEFAULT_CLUBS
from .fines import DEFAULT_FINES

N_HOLES = 18
DEFAULT_PARS = [4, 4, 3, 5, 4, 4, 3, 4, 5, 4, 3, 4, 5, 4, 4, 3, 4, 5]
DEFAULT_STROKE_INDEX = [7, 13, 17, 1, 9, 5, 15, 11, 3, 8, 16, 12, 2, 10, 6, 18, 14, 4]
MAX_STROKES = 20


@dataclass
class Hole:
    number: int
    par: int
    stroke_index: int


def default_holes() -> list[Hole]:
    return [Hole(i + 1, DEFAULT_PARS[i], DEFAULT_STROKE_INDEX[i]) for i in range(N_HOLES)]


@dataclass
class Course:
    name: str = "My Club"
    holes: list[Hole] = field(default_factory=default_holes)

    def hole(self, number: int) -> Hole:
        return self.holes[number - 1]

    @property
    def par(self) -> int:
        return sum(h.par for h in self.holes)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if len(self.holes) != N_HOLES:
            problems.append(f"Course needs exactly {N_HOLES} holes (has {len(self.holes)}).")
        if sorted(h.stroke_index for h in self.holes) != list(range(1, len(self.holes) + 1)):
            problems.append("Stroke indexes must use 1-18 exactly once each.")
        for h in self.holes:
            if h.par not in (3, 4, 5, 6):
                problems.append(f"Hole {h.number}: par must be 3-6.")
        return problems

    def to_dict(self) -> dict:
        return {"name": self.name, "holes": [vars(h).copy() for h in self.holes]}

    @classmethod
    def from_dict(cls, d: dict | None) -> "Course":
        d = d or {}
        holes = [Hole(int(h["number"]), int(h["par"]), int(h["stroke_index"])) for h in d.get("holes", [])]
        return cls(name=str(d.get("name") or "My Club"), holes=holes or default_holes())


@dataclass
class Player:
    name: str
    handicap: float = 18.0

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        return cls(name=str(d["name"]), handicap=float(d.get("handicap", 18.0)))


def default_games() -> dict[str, dict[str, Any]]:
    return {
        "stableford": {"stake": 5.0, "allowance": 1.0},
        "skins": {"value": 1.0, "use_net": True, "allowance": 1.0},
    }


_MISSING = object()


@dataclass
class Round:
    course: Course
    players: list[Player]
    games: dict[str, dict[str, Any]] = field(default_factory=default_games)
    scores: dict[str, dict[int, int | None]] = field(default_factory=dict)
    team_scores: dict[str, dict[int, int | None]] = field(default_factory=dict)
    wolf_picks: dict[int, str] = field(default_factory=dict)
    fines: list[dict[str, Any]] = field(default_factory=list)
    current_hole: int = 1
    lightning_last: float | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    round_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # ---- players / teams -------------------------------------------------
    @property
    def player_names(self) -> list[str]:
        return [p.name for p in self.players]

    def player(self, name: str) -> Player:
        for p in self.players:
            if p.name == name:
                return p
        raise KeyError(name)

    @property
    def is_team_scoring(self) -> bool:
        return "ambrose" in self.games

    @property
    def team_names(self) -> list[str]:
        return [t["name"] for t in self.games.get("ambrose", {}).get("teams", [])]

    def scoring_entities(self) -> list[str]:
        return self.team_names if self.is_team_scoring else self.player_names

    # ---- scores ----------------------------------------------------------
    def _book(self, team: bool) -> dict[str, dict[int, int | None]]:
        return self.team_scores if team else self.scores

    @staticmethod
    def _check_hole(hole: int) -> int:
        hole = int(hole)
        if not 1 <= hole <= N_HOLES:
            raise ValueError(f"Hole must be 1-{N_HOLES}, got {hole}")
        return hole

    def has_score(self, name: str, hole: int, team: bool = False) -> bool:
        return hole in self._book(team).get(name, {})

    def gross(self, name: str, hole: int, team: bool = False) -> int | None:
        """Gross strokes, or None for a pick-up. Raises KeyError if not yet entered."""
        val = self._book(team).get(name, {}).get(hole, _MISSING)
        if val is _MISSING:
            raise KeyError((name, hole))
        return val  # type: ignore[return-value]

    def set_score(self, name: str, hole: int, strokes: int | None, team: bool = False) -> None:
        hole = self._check_hole(hole)
        if strokes is not None:
            strokes = int(strokes)
            if not 1 <= strokes <= MAX_STROKES:
                raise ValueError(f"Strokes must be 1-{MAX_STROKES}")
        self._book(team).setdefault(name, {})[hole] = strokes

    def clear_score(self, name: str, hole: int, team: bool = False) -> None:
        self._book(team).get(name, {}).pop(int(hole), None)

    def adjust_score(self, name: str, hole: int, delta: int, team: bool = False) -> int:
        """One-tap entry: first tap sets par (+) or birdie (-); later taps step by 1."""
        hole = self._check_hole(hole)
        par = self.course.hole(hole).par
        if not self.has_score(name, hole, team) or self.gross(name, hole, team) is None:
            new = par if delta > 0 else par - 1
        else:
            new = int(self.gross(name, hole, team)) + int(delta)
        new = max(1, min(MAX_STROKES, new))
        self.set_score(name, hole, new, team)
        return new

    def holes_complete(self, names: list[str] | None = None, team: bool = False) -> list[int]:
        names = names if names is not None else (self.team_names if team else self.player_names)
        if not names:
            return []
        return [h for h in range(1, N_HOLES + 1) if all(self.has_score(n, h, team) for n in names)]

    def is_complete(self) -> bool:
        return len(self.holes_complete(team=self.is_team_scoring)) == N_HOLES

    def go_to_hole(self, hole: int) -> int:
        self.current_hole = max(1, min(N_HOLES, int(hole)))
        return self.current_hole

    def total_gross(self, name: str, team: bool = False) -> tuple[int, int, int]:
        """(gross strokes, holes played, pick-ups) over entered holes."""
        book = self._book(team).get(name, {})
        played = [v for v in book.values() if v is not None]
        return sum(played), len(book), sum(1 for v in book.values() if v is None)

    # ---- serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        def book(b):
            return {n: {str(h): v for h, v in hs.items()} for n, hs in b.items()}

        return {
            "round_id": self.round_id,
            "course": self.course.to_dict(),
            "players": [vars(p).copy() for p in self.players],
            "games": copy.deepcopy(self.games),
            "scores": book(self.scores),
            "team_scores": book(self.team_scores),
            "wolf_picks": {str(h): v for h, v in self.wolf_picks.items()},
            "fines": copy.deepcopy(self.fines),
            "current_hole": self.current_hole,
            "lightning_last": self.lightning_last,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Round":
        def book(b):
            return {n: {int(h): (None if v is None else int(v)) for h, v in hs.items()} for n, hs in (b or {}).items()}

        return cls(
            course=Course.from_dict(d.get("course")),
            players=[Player.from_dict(p) for p in d.get("players", [])],
            games=dict(d.get("games") or {}),
            scores=book(d.get("scores")),
            team_scores=book(d.get("team_scores")),
            wolf_picks={int(h): str(v) for h, v in (d.get("wolf_picks") or {}).items()},
            fines=list(d.get("fines") or []),
            current_hole=int(d.get("current_hole", 1)),
            lightning_last=d.get("lightning_last"),
            started_at=float(d.get("started_at") or time.time()),
            finished_at=d.get("finished_at"),
            round_id=str(d.get("round_id") or uuid.uuid4().hex[:12]),
        )


@dataclass
class Settings:
    course: Course = field(default_factory=Course)
    players: list[Player] = field(default_factory=lambda: [Player("Rusty", 18.0)])
    clubs: list[list] = field(default_factory=lambda: copy.deepcopy(DEFAULT_CLUBS))
    fines_catalog: list[dict] = field(default_factory=lambda: copy.deepcopy(DEFAULT_FINES))
    fines_mode: str = "kitty"
    pro_shop_phone: str = ""
    location_name: str = ""
    latitude: float | None = None
    longitude: float | None = None
    bom_state: str = "nsw"
    bom_district: str = ""
    typical_miss: str = "Straight"

    def to_dict(self) -> dict:
        return {
            "course": self.course.to_dict(),
            "players": [vars(p).copy() for p in self.players],
            "clubs": copy.deepcopy(self.clubs),
            "fines_catalog": copy.deepcopy(self.fines_catalog),
            "fines_mode": self.fines_mode,
            "pro_shop_phone": self.pro_shop_phone,
            "location_name": self.location_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "bom_state": self.bom_state,
            "bom_district": self.bom_district,
            "typical_miss": self.typical_miss,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "Settings":
        d = d or {}
        base = cls()

        def opt_float(v):
            try:
                return None if v in (None, "") else float(v)
            except (TypeError, ValueError):
                return None

        return cls(
            course=Course.from_dict(d.get("course")),
            players=[Player.from_dict(p) for p in d.get("players", [])] or base.players,
            clubs=d.get("clubs") or base.clubs,
            fines_catalog=d.get("fines_catalog") or base.fines_catalog,
            fines_mode=str(d.get("fines_mode") or "kitty"),
            pro_shop_phone=str(d.get("pro_shop_phone") or ""),
            location_name=str(d.get("location_name") or ""),
            latitude=opt_float(d.get("latitude")),
            longitude=opt_float(d.get("longitude")),
            bom_state=str(d.get("bom_state") or "nsw"),
            bom_district=str(d.get("bom_district") or ""),
            typical_miss=str(d.get("typical_miss") or "Straight"),
        )


def new_round(settings: Settings, games: dict | None = None) -> Round:
    return Round(
        course=copy.deepcopy(settings.course),
        players=copy.deepcopy(settings.players),
        games=copy.deepcopy(games) if games is not None else default_games(),
    )
