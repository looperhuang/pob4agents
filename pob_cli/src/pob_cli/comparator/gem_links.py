"""`rank-gems --optimize`: coordinate descent over a group's support slots, each swap PoB-verified.

Single-slot ranking (`rank_gems`) can miss the best set because supports interact. This loops over
every support slot, swaps in the best candidate for that slot given the others, and repeats until a
pass changes nothing. The build is restored; the result is a `batch` ops list.
"""

from __future__ import annotations

from typing import Any

from ..analyzer import resolve_skill_group_index
from ..bridge_client import BridgeWorker
from ..formatters import _parse_numeric_or_none, strip_pob_escapes
from ..mutators import _BatchCache, _execute_batch_ops
from ..snapshot import BuildTransaction, capture_digest
from .rank_scored import _baseline
from .ranking import rank_gems

_ZERO_CHARGE_CAVEAT = "0 charges on 0-mana skill!"
_TRIES_PER_SLOT = 3


def _field_value(worker: BridgeWorker, field: str) -> float | None:
    return _baseline((worker.call("get_stats", {}) or {}).get("stats") or {}, field)


def _support_slots(worker: BridgeWorker, g_idx: int) -> list[dict[str, Any]]:
    group = next((g for g in worker.call("list_skills", {}).get("groups", []) if g.get("index") == g_idx), None)
    if group is None:
        raise ValueError(f"Skill group #{g_idx} not found.")
    return [gm for gm in group.get("gems", []) if gm.get("support") and not gm.get("fromItem") and not gm.get("fromNode")]


def _best_swap(worker: BridgeWorker, tx: BuildTransaction, g_idx: int, slot: dict[str, Any], *, field: str, include_legacy: bool) -> dict[str, Any] | None:
    """Apply the first ranked candidate for `slot` that PoB confirms raises `field`; None leaves the slot as is."""
    idx = int(slot["index"])
    current = strip_pob_escapes(str(slot.get("name") or slot.get("nameSpec") or ""))
    res = rank_gems(worker, group_selector=str(g_idx), slot_idx=idx, field=field, top=5,
                    exclude_archetype_swaps=True, include_legacy=include_legacy)
    cands = [
        c for c in res.get("candidates") or []
        if str(c.get("name") or "") != current
        and c.get("caveat") != _ZERO_CHARGE_CAVEAT
        and (_parse_numeric_or_none(c.get("delta")) or 0) > 0
    ]
    prev = _field_value(worker, field)
    if prev is None:
        return None
    if not cands:
        return None
    slot_cp = tx.checkpoint()
    try:
        for cand in cands[:_TRIES_PER_SLOT]:
            op = {"op": "skill", "group": str(g_idx), "gem": idx, "newGem": str(cand["name"])}
            try:
                _execute_batch_ops(worker, [op], _BatchCache(worker))
            except ValueError:
                tx.restore(slot_cp)  # the skill op cannot place this gem: try the next candidate
                continue
            now = _field_value(worker, field)
            if now is not None and now > prev:
                return {"slot": idx, "from": current, "to": str(cand["name"]), "dpsBefore": prev, "dpsAfter": now, "op": op}
            # The engine's ranking and the applied gem disagree: undo and try the next candidate.
            tx.restore(slot_cp)
        return None
    finally:
        tx.drop(slot_cp)


def optimize_links(
    worker: BridgeWorker,
    *,
    group_selector: str = "main",
    field: str = "CombinedDPS",
    passes: int = 2,
    include_legacy: bool = False,
) -> dict[str, Any]:
    """Greedy support-set optimisation for one skill group; never leaves the build changed."""
    swaps: list[dict[str, Any]] = []
    with BuildTransaction(worker) as tx:
        g_idx = resolve_skill_group_index(worker.call("list_skills", {}), group_selector)
        orig_digest = capture_digest(worker)
        if field.lower() == "primary":  # FullDPS / MinionCombinedDPS / CombinedDPS, as the build's digest picks
            field = str(orig_digest.get("primaryDpsKey") or "CombinedDPS")
        before = _field_value(worker, field)
        if before is None:
            raise ValueError(f"Stat `{field}` not found in the build's stats; it cannot be optimised.")
        for _ in range(max(1, passes)):
            changed = False
            for slot in _support_slots(worker, g_idx):
                swap = _best_swap(worker, tx, g_idx, slot, field=field, include_legacy=include_legacy)
                if swap is not None:
                    swaps.append(swap)
                    changed = True
            if not changed:
                break
        after = swaps[-1]["dpsAfter"] if swaps else before
        restore_check = tx.rollback_verified(orig_digest)

    pct = ((after - before) / abs(before) * 100.0) if (before and after is not None) else None
    return {
        "groupIndex": g_idx,
        "dpsField": field,
        "before": before,
        "after": after,
        "pct": pct,
        "swaps": [{k: v for k, v in s.items() if k != "op"} for s in swaps],
        "ops": [s["op"] for s in swaps],
        "restoreCheck": restore_check,
    }
