"""Fines & Shouts ledger."""
from __future__ import annotations

import time
import uuid
from typing import Any

KITTY = "🍺 Kitty"

DEFAULT_FINES: list[dict[str, Any]] = [
    {"key": "tantrum", "label": "Thrown club / tantrum", "emoji": "🤬", "amount": 0.0, "shout": True},
    {"key": "obscenity", "label": "Obscenity", "emoji": "🙊", "amount": 2.0, "shout": False},
    {"key": "air_swing", "label": "Air swing", "emoji": "💨", "amount": 2.0, "shout": False},
    {"key": "front_tees", "label": "Didn't pass the front tees", "emoji": "🎀", "amount": 2.0, "shout": False},
    {"key": "three_putt", "label": "3-putt", "emoji": "⛳", "amount": 1.0, "shout": False},
]


def to_cents(dollars: Any) -> int:
    try:
        return int(round(float(dollars or 0) * 100))
    except (TypeError, ValueError):
        return 0


def normalise_catalog(catalog: list[dict] | None) -> list[dict[str, Any]]:
    """Clean a user-edited catalog; falls back to defaults if empty."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in catalog or []:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        key = str(row.get("key") or "").strip() or label.lower().replace(" ", "_")[:24]
        base, n = key, 2
        while key in seen:
            key, n = f"{base}_{n}", n + 1
        seen.add(key)
        try:
            amount = max(0.0, float(row.get("amount") or 0))
        except (TypeError, ValueError):
            amount = 0.0
        out.append(
            {
                "key": key,
                "label": label,
                "emoji": str(row.get("emoji") or "💸").strip() or "💸",
                "amount": amount,
                "shout": bool(row.get("shout", False)),
            }
        )
    return out or [dict(f) for f in DEFAULT_FINES]


def describe(fine_type: dict) -> str:
    cost = "Shout the round" if fine_type.get("shout") else f"${float(fine_type.get('amount', 0)):.2f}"
    if fine_type.get("shout") and float(fine_type.get("amount") or 0) > 0:
        cost = f"Shout + ${float(fine_type['amount']):.2f}"
    return f"{fine_type.get('emoji', '')} {fine_type.get('label', '')} ({cost})".strip()


def add_fine(rnd, player: str, fine_type: dict, hole: int | None = None, now: float | None = None) -> dict:
    if player not in rnd.player_names:
        raise ValueError(f"Unknown player: {player}")
    entry = {
        "id": uuid.uuid4().hex[:10],
        "player": player,
        "key": fine_type.get("key", ""),
        "label": fine_type.get("label", ""),
        "emoji": fine_type.get("emoji", ""),
        "amount_cents": to_cents(fine_type.get("amount", 0)),
        "shout": bool(fine_type.get("shout", False)),
        "hole": int(hole) if hole else None,
        "ts": float(now if now is not None else time.time()),
    }
    rnd.fines.append(entry)
    return entry


def undo_fine(rnd, fine_id: str) -> bool:
    for i, f in enumerate(rnd.fines):
        if f.get("id") == fine_id:
            del rnd.fines[i]
            return True
    return False


def undo_last(rnd) -> dict | None:
    return rnd.fines.pop() if rnd.fines else None


def fines_by_player(rnd) -> dict[str, dict[str, Any]]:
    out = {p: {"count": 0, "cents": 0, "shouts": 0} for p in rnd.player_names}
    for f in rnd.fines:
        row = out.setdefault(f["player"], {"count": 0, "cents": 0, "shouts": 0})
        row["count"] += 1
        row["cents"] += int(f.get("amount_cents", 0))
        row["shouts"] += 1 if f.get("shout") else 0
    return out


def shouts(rnd) -> list[dict]:
    return [f for f in rnd.fines if f.get("shout")]


def fine_balances(rnd, mode: str = "kitty") -> dict[str, int]:
    """Zero-sum cents. 'kitty': fines fund the 19th-hole bar tab. 'split': shared among the others."""
    bal: dict[str, int] = {p: 0 for p in rnd.player_names}
    for f in rnd.fines:
        amt = int(f.get("amount_cents", 0))
        if amt <= 0:
            continue
        payer = f["player"]
        bal[payer] = bal.get(payer, 0) - amt
        others = [p for p in rnd.player_names if p != payer]
        if mode == "split" and others:
            share, rem = divmod(amt, len(others))
            for i, p in enumerate(others):
                bal[p] += share + (1 if i < rem else 0)
        else:
            bal[KITTY] = bal.get(KITTY, 0) + amt
    return bal
