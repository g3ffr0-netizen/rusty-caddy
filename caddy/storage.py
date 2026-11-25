"""Crash-safe local persistence: every tap is written atomically with a .bak fallback."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .models import Round, Settings


class Store:
    def __init__(self, base_dir: str | os.PathLike):
        self.base = Path(base_dir)
        self.rounds_dir = self.base / "rounds"
        self.rounds_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.base / "settings.json"
        self.round_path = self.base / "current_round.json"

    # ---- low level -------------------------------------------------------
    @staticmethod
    def _bak(path: Path) -> Path:
        return path.with_name(path.name + ".bak")

    def _write_json(self, path: Path, data: Any) -> None:
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            shutil.copy2(path, self._bak(path))
        os.replace(tmp, path)

    def _read_json(self, path: Path) -> Any:
        for p in (path, self._bak(path)):
            if not p.exists():
                continue
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return None

    # ---- settings --------------------------------------------------------
    def load_settings(self) -> Settings:
        data = self._read_json(self.settings_path)
        try:
            return Settings.from_dict(data) if data else Settings()
        except (KeyError, TypeError, ValueError):
            return Settings()

    def save_settings(self, settings: Settings) -> None:
        self._write_json(self.settings_path, settings.to_dict())

    # ---- rounds ----------------------------------------------------------
    def load_round(self) -> Round | None:
        data = self._read_json(self.round_path)
        if not data:
            return None
        try:
            return Round.from_dict(data)
        except (KeyError, TypeError, ValueError):
            return None

    def save_round(self, rnd: Round) -> None:
        self._write_json(self.round_path, rnd.to_dict())

    def archive_round(self, rnd: Round) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M", time.localtime(rnd.started_at))
        dest = self.rounds_dir / f"{stamp}_{rnd.round_id}.json"
        self._write_json(dest, rnd.to_dict())
        for p in (self.round_path, self._bak(self.round_path)):
            if p.exists():
                p.unlink()
        return dest

    def list_archived(self) -> list[Path]:
        return sorted((p for p in self.rounds_dir.glob("*.json")), reverse=True)
