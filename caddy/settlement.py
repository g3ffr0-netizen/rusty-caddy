"""19th-hole settlement: combine game + fines balances and settle with the fewest payments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fines import KITTY, fine_balances, fines_by_player, shouts
from .formats import GameResult, compute_all

EXACT_LIMIT = 14  # exact subset DP up to 14 non-zero parties (2^14 states); greedy above that


@dataclass
class Transfer:
    payer: str
    payee: str
    cents: int


@dataclass
class Settlement:
    results: list[GameResult]
    fine_bal: dict[str, int]
    net: dict[str, int]
    transfers: list[Transfer]
    shouts: list[dict[str, Any]] = field(default_factory=list)


def money(c: int) -> str:
    sign = "-" if c < 0 else ""
    return f"{sign}${abs(c) / 100:,.2f}"


def combine_balances(*balances: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for b in balances:
        for k, v in b.items():
            out[k] = out.get(k, 0) + int(v)
    return out


def _greedy(items: list[tuple[str, int]]) -> list[Transfer]:
    creditors = sorted(([n, c] for n, c in items if c > 0), key=lambda x: -x[1])
    debtors = sorted(([n, -c] for n, c in items if c < 0), key=lambda x: -x[1])
    out: list[Transfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amt = min(debtors[i][1], creditors[j][1])
        if amt > 0:
            out.append(Transfer(debtors[i][0], creditors[j][0], amt))
        debtors[i][1] -= amt
        creditors[j][1] -= amt
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return out


def _zero_sum_groups(items: list[tuple[str, int]]) -> list[list[tuple[str, int]]]:
    """Partition into the maximum number of zero-sum groups (each group settles in size-1 payments)."""
    n = len(items)
    size = 1 << n
    sums = [0] * size
    for m in range(1, size):
        low = m & -m
        sums[m] = sums[m ^ low] + items[low.bit_length() - 1][1]
    dp = [0] * size
    choice = [-1] * size
    for m in range(1, size):
        best, bi, mm = -1, -1, m
        while mm:
            low = mm & -mm
            mm ^= low
            v = dp[m ^ low]
            if v > best:
                best, bi = v, low.bit_length() - 1
        dp[m] = best + (1 if sums[m] == 0 else 0)
        choice[m] = bi
    order, m = [], size - 1
    while m:
        i = choice[m]
        order.append(i)
        m ^= 1 << i
    order.reverse()
    groups, cur, s = [], [], 0
    for i in order:
        cur.append(items[i])
        s += items[i][1]
        if s == 0:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def min_transfers(balances: dict[str, int]) -> list[Transfer]:
    items = [(n, int(c)) for n, c in balances.items() if int(c) != 0]
    if sum(c for _, c in items) != 0:
        raise ValueError(f"Balances must sum to zero (got {sum(c for _, c in items)} cents).")
    if not items:
        return []
    groups = _zero_sum_groups(items) if len(items) <= EXACT_LIMIT else [items]
    out: list[Transfer] = []
    for g in groups:
        out.extend(_greedy(g))
    return out


def settle(rnd, fines_mode: str = "kitty") -> Settlement:
    results = compute_all(rnd)
    fb = fine_balances(rnd, fines_mode)
    net = combine_balances(*(r.balances for r in results), fb)
    for p in rnd.player_names:
        net.setdefault(p, 0)
    return Settlement(results=results, fine_bal=fb, net=net, transfers=min_transfers(net), shouts=shouts(rnd))


def summary_text(rnd, s: Settlement) -> str:
    lines = [f"⛳ {rnd.course.name}: 19th Hole Summary"]
    for r in s.results:
        if r.error:
            lines.append(f"• {r.title}: not scored ({r.error})")
            continue
        if r.standings:
            top = r.standings[0]
            label = top.get("Player") or top.get("Team") or top.get("Bet")
            metric = next((f"{k} {top[k]}" for k in ("Points", "Skins", "Net", "Score", "Status") if k in top), "")
            lines.append(f"• {r.title}: {label} ({metric})")
    fp = fines_by_player(rnd)
    fined = [f"{p} {money(v['cents'])}" for p, v in fp.items() if v["cents"]]
    if fined:
        lines.append("💸 Fines: " + ", ".join(fined))
    for sh in s.shouts:
        lines.append(f"🍻 {sh['player']} shouts the round ({sh['label']}" + (f", H{sh['hole']})" if sh.get("hole") else ")"))
    lines.append("💰 Settle up:")
    if s.transfers:
        for t in s.transfers:
            lines.append(f"   {t.payer} → {t.payee}: {money(t.cents)}")
    else:
        lines.append("   All square, nobody owes anything.")
    if KITTY in s.net and s.net[KITTY]:
        lines.append(f"   ({KITTY} goes on the bar tab.)")
    return "\n".join(lines)
