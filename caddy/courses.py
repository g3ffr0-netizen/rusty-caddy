"""Local JSON course-data loader, validator, and exporter (pure Python)."""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Iterable

from .models import Course, Round, Settings

DEFAULT_COURSES_DIR = Path(__file__).resolve().parents[1] / "courses"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "course").lower()).strip("_")
    return slug[:48] or "course"


def load_course_dict(data: dict) -> Course:
    """Parse and strictly validate a course JSON object."""
    if not isinstance(data, dict):
        raise ValueError("Course JSON must be an object.")
    if not data.get("holes"):
        raise ValueError("Course JSON must include a 'holes' list with 18 entries.")
    try:
        course = Course.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid course data: {exc}") from exc
    problems = course.validate()
    if problems:
        raise ValueError(" ".join(problems))
    return course


def load_course_json(text: str | bytes) -> Course:
    """Parse and validate a course from a JSON string or UTF-8 bytes."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"Could not parse course JSON: {exc}") from exc
    return load_course_dict(data)


def load_course_file(path: str | os.PathLike) -> Course:
    """Load and validate a course JSON file from disk."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Course file not found: {p}")
    return load_course_json(p.read_text(encoding="utf-8"))


def export_course_json(course: Course) -> str:
    """Serialise a Course (including distances, pars, Pro Shop, location) as formatted JSON."""
    return json.dumps(course.to_dict(), indent=2, ensure_ascii=False) + "\n"


def save_course_file(course: Course, directory: str | os.PathLike, filename: str | None = None) -> Path:
    """Atomically save a validated Course JSON template to disk."""
    problems = course.validate()
    if problems:
        raise ValueError(" ".join(problems))
    dest_dir = Path(directory)
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = filename or f"{_slugify(course.name)}.json"
    if not fname.lower().endswith(".json"):
        fname += ".json"
    dest = dest_dir / fname
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(export_course_json(course), encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def list_course_files(search_dirs: Iterable[str | os.PathLike] | None = None) -> list[Path]:
    """Discover local .json course templates across bundled and user data directories."""
    dirs = [Path(d) for d in search_dirs] if search_dirs is not None else [DEFAULT_COURSES_DIR]
    found: list[Path] = []
    seen: set[Path] = set()
    for d in dirs:
        if not d.exists() or not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                found.append(p)
    return found


def course_label(path: Path) -> str:
    """Readable label for a local course file (falls back to filename if unreadable)."""
    try:
        c = load_course_file(path)
        tee = f" — {c.tee}" if c.tee else ""
        return f"{c.name}{tee} (Par {c.par}, {c.total_distance_m} m)"
    except Exception:
        return path.name


def apply_course_to_settings(settings: Settings, course: Course, rnd: Round | None = None) -> None:
    """Apply a loaded course template to Settings (and optionally the active Round)."""
    settings.course = copy.deepcopy(course)
    if course.pro_shop_phone:
        settings.pro_shop_phone = course.pro_shop_phone
    if course.location_name:
        settings.location_name = course.location_name
    if course.latitude is not None and course.longitude is not None:
        settings.latitude = course.latitude
        settings.longitude = course.longitude
    if course.bom_state:
        settings.bom_state = course.bom_state
    if course.bom_district:
        settings.bom_district = course.bom_district
    if rnd is not None:
        rnd.course = copy.deepcopy(course)
