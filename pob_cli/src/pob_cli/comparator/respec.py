"""`pob respec`: greedy refund-one / allocate-one passive swaps, each verified by a real PoB recalculation.

Every round deallocates a cheap allocated passive (`rank_refunds`), allocates the best unallocated node
by score per point (`rank_nodes_scored`), and keeps the swap only if PoB shows a net score gain, no
broken floor and no extra points used. The build is always restored; the result is a `batch` ops list.
"""

from __future__ import annotations

from typing import Any

from ..bridge_client import BridgeWorker
from ..mutators import _apply_tree_changes_in_place, _compact_sweep_summary
from ..scoring import Floor, floor_failures, pct_change, stat_keys, stat_value, weighted_score
from ..snapshot import BuildTransaction, capture_digest
from .rank_refund import DEFAULT_REFUND_SCORE, rank_refunds
from .rank_scored import pob_stat_name, rank_nodes_scored

_REFUND_TRIES_PER_ROUND = 3
_ADD_TRIES_PER_REFUND = 5


def _rank_score(score: dict[str, float], primary_key: str) -> dict[str, float]:
    """Translate a sweep-summary score to PoB `node_power` stat names, which only order the add candidates.

    Every swap is still judged on the summary score by a real recalculation, so a term PoB cannot rank
    (a max-hit or resistance key) is left out of the ordering, not out of the verdict.
    """
    out: dict[str, float] = {}
    for k, wgt in score.items():
        name = pob_stat_name(k, primary_key)
        if "MaxHit" not in name and "Resist" not in name and "Chance" not in name and name != "SpellSuppression":
            out[name] = out.get(name, 0.0) + wgt
    return out or {primary_key: 1.0}


def _state(w: BridgeWorker) -> tuple[set[int], int]:
    st = w.call("get_tree_state", {})
    return {int(x) for x in st.get("allocatedNodes", [])}, int((st.get("points") or {}).get("used") or 0)


def _score_vs(before: dict[str, Any], after: dict[str, Any], score: dict[str, float], floors: list[Floor]) -> tuple[float | None, list[str]]:
    pcts: dict[str, float | None] = {}
    vals: dict[str, float | None] = {}
    for k in stat_keys(score, floors):
        b, v = stat_value(before, k), stat_value(after, k)
        vals[k] = v
        pcts[k] = pct_change(b, None if b is None or v is None else v - b)
    return weighted_score(pcts, score), floor_failures(vals, floors)


def _try_round(
    w: BridgeWorker,
    tx: BuildTransaction,
    refund: dict[str, Any],
    *,
    banned: set[int],
    used_before: int,
    before_sum: dict[str, Any],
    score: dict[str, float],
    floors: list[Floor],
    max_dist: int,
) -> dict[str, Any] | None:
    """Deallocate `refund`, then try the best adds; leaves the swap applied only when it is returned."""
    rid = int(refund["id"])
    try:
        _apply_tree_changes_in_place(w, [], [(rid, None)], allow_cascade=False)
    except ValueError:
        return None  # cascade-blocked: try the next refund; scoring errors still reach the caller
    mid = tx.checkpoint()
    try:
        return _try_adds(w, tx, mid, refund, banned=banned, used_before=used_before, before_sum=before_sum,
                         score=score, floors=floors, max_dist=max_dist)
    finally:
        tx.drop(mid)


def _try_adds(
    w: BridgeWorker,
    tx: BuildTransaction,
    mid: Any,
    refund: dict[str, Any],
    *,
    banned: set[int],
    used_before: int,
    before_sum: dict[str, Any],
    score: dict[str, float],
    floors: list[Floor],
    max_dist: int,
) -> dict[str, Any] | None:
    rid = int(refund["id"])
    rank_score = _rank_score(score, str(before_sum.get("primaryDpsKey") or "CombinedDPS"))
    # An add must fit in the points the refund freed, or the points check below always rejects it.
    freed = max(1, int(refund.get("pointsRefunded") or 1))
    # Floors are checked on the applied swap below, not on the per-stat engine estimate.
    adds = rank_nodes_scored(w, score=rank_score, floors=[], max_dist=min(max_dist, freed),
                             top=_ADD_TRIES_PER_REFUND * 3)["byPerPoint"]
    tried = 0
    for add in adds:
        aid = int(add["id"])
        if aid in banned or aid == rid or add.get("type") == "Mastery":
            continue  # masteries need an effect id; re-adding a refunded node just undoes the swap
        if tried >= _ADD_TRIES_PER_REFUND:
            break
        tried += 1
        try:
            _apply_tree_changes_in_place(w, [(aid, None)], [], allow_cascade=False)
            _, used_after = _state(w)
            if used_after <= used_before:
                after_sum = _compact_sweep_summary(capture_digest(w))
                gain, fails = _score_vs(before_sum, after_sum, score, floors)
                if gain is not None and gain > 0 and not fails:
                    return {"refund": refund, "add": add, "gain": gain, "pointsDelta": used_after - used_before, "after": after_sum}
        except ValueError:
            pass  # needsConfirm / cascade-blocked: try the next candidate
        tx.restore(mid)
    return None


def plan_respec(
    worker: BridgeWorker,
    *,
    score: dict[str, float] | None = None,
    floors: list[Floor] | None = None,
    rounds: int = 3,
    max_dist: int = 5,
) -> dict[str, Any]:
    """Greedy respec plan; never leaves the build changed (0-residue restore + verify)."""
    score, floors = score or dict(DEFAULT_REFUND_SCORE), floors or []
    accepted: list[dict[str, Any]] = []
    with BuildTransaction(worker) as tx:
        orig_digest = capture_digest(worker)
        orig_sum = _compact_sweep_summary(orig_digest)
        queue = list(rank_refunds(worker, score=score, floors=floors, top=max(10, rounds * _REFUND_TRIES_PER_ROUND))["cheapest"])
        banned: set[int] = set()
        # An accepted round's summary is the next round's baseline, so no round re-reads the build.
        final_sum = orig_sum
        for _ in range(max(0, rounds)):
            round_cp = tx.checkpoint()
            alloc, used_before = _state(worker)
            result = None
            tries = 0
            while queue and result is None and tries < _REFUND_TRIES_PER_ROUND:
                refund = queue.pop(0)
                if int(refund["id"]) not in alloc:
                    continue
                tries += 1
                result = _try_round(worker, tx, refund, banned=banned, used_before=used_before, before_sum=final_sum,
                                    score=score, floors=floors, max_dist=max_dist)
                if result is None:
                    tx.restore(round_cp)
            tx.drop(round_cp)
            if result is None:
                break
            banned.add(int(result["refund"]["id"]))
            accepted.append(result)
            final_sum = result["after"]
        restore_check = tx.rollback_verified(orig_digest)

    total, fails = _score_vs(orig_sum, final_sum, score, floors)
    ops: list[dict[str, Any]] = []
    for r in accepted:
        ops.append({"op": "tree", "deallocate": [str(r["refund"]["id"])], "allowCascade": False})
        ops.append({"op": "tree", "allocate": [str(r["add"]["id"])], "allowCascade": False})
    keys = stat_keys(score, floors)
    return {
        "score": score,
        "floors": [f"{k}{op}{lim:g}" for k, op, lim in floors],
        "rounds": [
            {
                "refund": {k: r["refund"].get(k) for k in ("id", "name", "nameZh", "type", "pointsRefunded", "lossPerPoint")},
                "add": {k: r["add"].get(k) for k in ("id", "name", "nameZh", "type", "pathDist", "scorePerPoint")},
                "gain": r["gain"],
                "pointsDelta": r["pointsDelta"],
            }
            for r in accepted
        ],
        "totalGain": total if accepted else 0.0,
        "floorFail": fails if accepted else [],
        "before": {k: stat_value(orig_sum, k) for k in keys},
        "after": {k: stat_value(final_sum, k) for k in keys},
        "ops": ops,
        "restoreCheck": restore_check,
    }
