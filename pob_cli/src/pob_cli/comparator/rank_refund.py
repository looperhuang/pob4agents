"""`rank-nodes --refund`: what each allocated passive is worth, by deallocating it alone and rolling back.

One `sweep` variant per allocated node (0-residue rollback). A node whose removal would orphan more
than the cascade threshold is reported as not refundable rather than silently dropping a branch.
"""

from __future__ import annotations

from typing import Any

from ..bridge_client import BridgeWorker
from ..formatters import strip_pob_escapes
from ..mutators import run_sweep
from ..scoring import Floor, floor_failures, pct_change, stat_keys, stat_value, weighted_score

# Start nodes cannot be refunded; ascendancy points come from a separate pool.
_SKIP_TYPES = frozenset({"ClassStart", "AscendClassStart"})
DEFAULT_REFUND_SCORE: dict[str, float] = {"primaryDps": 1.0, "totalEhp": 1.0}


def _refund_candidates(worker: BridgeWorker) -> list[dict[str, Any]]:
    tree_state = worker.call("get_tree_state", {})
    nodes_db = worker.get_cached_tree_data(tree_state.get("treeVersion")).get("nodes", {})
    dynamic_map = {str(n["id"]): n for n in tree_state.get("dynamicNodes", [])}
    out: list[dict[str, Any]] = []
    for nid in sorted(int(x) for x in tree_state.get("allocatedNodes", [])):
        meta = {**(nodes_db.get(str(nid)) or {}), **(dynamic_map.get(str(nid)) or {})}
        if meta.get("type") in _SKIP_TYPES or meta.get("asc") or meta.get("ascendancyName"):
            continue
        out.append({"id": nid, "name": meta.get("name"), "nameZh": meta.get("nameZh"), "type": meta.get("type")})
    return out


def _refund_row(node: dict[str, Any], var: dict[str, Any], base: dict[str, Any], score: dict[str, float], floors: list[Floor]) -> dict[str, Any]:
    row: dict[str, Any] = {**node, "name": strip_pob_escapes(node.get("name")), "nameZh": strip_pob_escapes(node.get("nameZh"))}
    if not var.get("ok"):
        row["refundable"] = False
        row["error"] = str(var.get("error") or "")
        return row
    step = next((s for s in var.get("steps") or [] if s.get("op") == "tree"), {})
    points = -int(step.get("pointsDelta") or 0)
    summary = var.get("summary") or {}
    keys = stat_keys(score, floors)
    after = {k: stat_value(summary, k) for k in keys}
    pcts: dict[str, float | None] = {}
    for k in keys:
        b, v = stat_value(base, k), after[k]
        pcts[k] = pct_change(b, None if b is None or v is None else v - b)
    node_score = weighted_score(pcts, score)
    loss = None if node_score is None else -node_score
    row.update(
        refundable=points > 0,
        pointsRefunded=points,
        orphanedNodes=step.get("orphanedNodes") or [],
        pcts={k: pcts[k] for k in score},
        loss=loss,
        lossPerPoint=(loss / points) if (loss is not None and points > 0) else None,
        floorFail=floor_failures(after, floors),
    )
    return row


def rank_refunds(
    worker: BridgeWorker,
    *,
    score: dict[str, float] | None = None,
    floors: list[Floor] | None = None,
    top: int = 15,
) -> dict[str, Any]:
    """Rank allocated passives by the score lost per refunded point (cheapest to respec first)."""
    score, floors = score or dict(DEFAULT_REFUND_SCORE), floors or []
    with worker.lock:
        nodes = _refund_candidates(worker)
        if not nodes:
            raise ValueError("No refundable allocated passives (only start/ascendancy nodes are allocated).")
        variants = [
            {"name": str(n["id"]), "ops": [{"op": "tree", "deallocate": [str(n["id"])], "allowCascade": False}]}
            for n in nodes
        ]
        res = run_sweep(worker, variants)
    base = (res.get("baseline") or {}).get("summary") or {}
    missing = [k for k, wgt in score.items() if wgt and not stat_value(base, k)]
    if missing:  # every lossPerPoint would be None, ranking nothing in silence
        raise ValueError(f"Baseline of {', '.join(missing)} is missing or 0; it cannot be scored by percent.")
    by_id = {v.get("name"): v for v in res.get("variants") or []}
    rows = [_refund_row(n, by_id.get(str(n["id"])) or {}, base, score, floors) for n in nodes]
    ranked = [r for r in rows if r.get("refundable") and r.get("lossPerPoint") is not None and not r.get("floorFail")]
    ranked.sort(key=lambda r: (r["lossPerPoint"], r["loss"]))
    return {
        "stat": "refund",
        "score": score,
        "floors": [f"{k}{op}{lim:g}" for k, op, lim in floors],
        "baseline": {k: stat_value(base, k) for k in stat_keys(score, floors)},
        "allocatedChecked": len(nodes),
        "refundable": len(ranked),
        "floorBlocked": sum(1 for r in rows if r.get("floorFail")),
        "notRefundable": [{"id": r["id"], "name": r["name"], "error": r.get("error")} for r in rows if r.get("refundable") is False][:top],
        "cheapest": ranked[:top],
        "restoreCheck": res.get("restoreCheck"),
    }
