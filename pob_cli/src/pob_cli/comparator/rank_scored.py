"""Multi-objective `rank-nodes --score/--floor`: one engine `node_power` pass per stat, merged by node and mastery effect."""

from __future__ import annotations

from typing import Any

from ..bridge_client import BridgeWorker
from ..formatters import _parse_numeric_or_none, strip_pob_escapes
from ..scoring import Floor, floor_failures, pct_change, stat_keys, weighted_score
from ..snapshot import capture_digest
from .ranking import _detect_equipped_weapon_types, _node_weapon_mastery_kind, _safe_dist, _safe_float

# Sweep-summary keys whose PoB power-stat name is not the key with its first letter raised ("life" -> "Life").
_POB_STAT = {"totalehp": "TotalEHP", "fulldps": "FullDPS", "combineddps": "CombinedDPS", "totaldps": "TotalDPS",
             "totaldotdps": "TotalDotDPS", "minioncombineddps": "MinionCombinedDPS"}


def pob_stat_name(key: str, primary_key: str) -> str:
    """PoB `node_power` stat name for a sweep-summary or PoB key, ignoring case (`totalehp` -> `TotalEHP`)."""
    low = key.lower()
    if low == "primarydps":
        return primary_key
    return _POB_STAT.get(low, key[:1].upper() + key[1:])


def _baseline(stats: dict[str, Any], key: str) -> float | None:
    low = key.lower()
    raw = stats.get(key, next((v for k, v in stats.items() if str(k).lower() == low), None))
    if raw is None:
        return None  # _parse_numeric_or_none reads a missing stat as 0
    val = _parse_numeric_or_none(raw)
    return float(val) if val is not None else None


def _node_power(worker: BridgeWorker, stat: str, max_dist: int) -> list[dict[str, Any]]:
    res = worker.call("node_power", {"stat": stat, "maxDepth": max_dist}, timeout=120.0)
    if not isinstance(res, dict) or res.get("error") or res.get("ok") is False:
        err = res.get("error") if isinstance(res, dict) else res
        # No silent fallback to another stat here: a mislabelled term would corrupt the score.
        raise ValueError(f"node_power cannot rank stat `{stat}`: {err or 'no report'}")
    return list(res.get("report") or [])


def rank_nodes_scored(
    worker: BridgeWorker,
    *,
    score: dict[str, float],
    floors: list[Floor],
    max_dist: int = 5,
    top: int = 15,
) -> dict[str, Any]:
    """Rank unallocated nodes by the weighted % gain over several stats, dropping nodes that break a floor."""
    with worker.lock:
        # Summary names (`primaryDps`, `totalEhp`, as `--refund` takes) map to PoB stat names here.
        primary = "CombinedDPS"
        if any(k.lower() == "primarydps" for k in stat_keys(score, floors)):
            primary = str(capture_digest(worker).get("primaryDpsKey") or "CombinedDPS")
        named: dict[str, float] = {}
        for k, wgt in score.items():
            named[pob_stat_name(k, primary)] = named.get(pob_stat_name(k, primary), 0.0) + wgt
        score, floors = named, [(pob_stat_name(k, primary), op, lim) for k, op, lim in floors]
        keys = stat_keys(score, floors)
        st = worker.call("get_stats", {})
        stats = (st.get("stats") if isinstance(st, dict) else None) or {}
        base = {k: _baseline(stats, k) for k in keys}
        missing = [k for k in keys if base[k] is None or (score.get(k) and base[k] == 0)]
        if missing:
            raise ValueError(f"Baseline of {', '.join(missing)} is missing or 0; it cannot be scored by percent.")
        # A mastery reports one row per effect under the same node id, so rows are keyed by (id, effectId).
        reports = {k: {(r.get("id"), r.get("effectId")): r for r in _node_power(worker, k, max_dist)} for k in keys}
        equipped_weapons = _detect_equipped_weapon_types(worker)

    ids = list(dict.fromkeys(i for rep in reports.values() for i in rep))
    candidates: list[dict[str, Any]] = []
    filtered_masteries: list[str] = []
    floor_excluded = 0
    for row_key in ids:
        node_id, effect_id = row_key
        meta = next(rep[row_key] for rep in reports.values() if row_key in rep)
        if meta.get("allocated") or _safe_dist(meta.get("pathDist")) > max_dist:
            continue
        if equipped_weapons is not None:
            wm_kind = _node_weapon_mastery_kind(meta)
            if wm_kind is not None and wm_kind not in equipped_weapons:
                filtered_masteries.append(strip_pob_escapes(str(meta.get("name") or meta.get("nameZh") or wm_kind)))
                continue
        # A node absent from one stat's report had no effect on that stat, so its delta is 0.
        power = {k: _safe_float((reports[k].get(row_key) or {}).get("power")) for k in keys}
        path_power = {k: _safe_float((reports[k].get(row_key) or {}).get("pathPower")) for k in keys}
        pcts = {k: pct_change(base[k], power[k]) for k in keys}
        node_score = weighted_score(pcts, score)
        per_point = weighted_score({k: pct_change(base[k], path_power[k]) for k in keys}, score)
        if node_score is None or per_point is None or not (node_score > 0 or per_point > 0):
            continue
        if floor_failures({k: base[k] + power[k] for k in keys if base[k] is not None}, floors):
            floor_excluded += 1
            continue
        row: dict[str, Any] = {
            "id": node_id,
            "name": meta.get("name"),
            "nameZh": meta.get("nameZh"),
            "type": meta.get("type"),
            "pathDist": meta.get("pathDist"),
            "score": node_score,
            "scorePerPoint": per_point,
            "pcts": {k: pcts[k] for k in score},
        }
        if effect_id is not None:
            row.update(effectId=effect_id, allocSpec=meta.get("allocSpec") or f"{node_id}:{effect_id}")
        candidates.append(row)

    # Keep each mastery effect once, at its best-scoring row (as `rank_nodes` does).
    best: dict[Any, dict[str, Any]] = {}
    for r in candidates:
        eff = r.get("effectId")
        if eff is not None and (eff not in best or (r["scorePerPoint"], r["score"], -_safe_dist(r["pathDist"]))
                                > (best[eff]["scorePerPoint"], best[eff]["score"], -_safe_dist(best[eff]["pathDist"]))):
            best[eff] = r
    candidates = [r for r in candidates if r.get("effectId") is None or best[r["effectId"]] is r]

    out: dict[str, Any] = {
        "stat": "score",
        "score": score,
        "floors": [f"{k}{op}{lim:g}" for k, op, lim in floors],
        "baseline": base,
        "maxDist": max_dist,
        "totalCandidates": len(candidates),
        "floorExcluded": floor_excluded,
        "byPerPoint": sorted(candidates, key=lambda r: (r["scorePerPoint"], r["score"]), reverse=True)[:top],
        "byTotalGain": sorted(candidates, key=lambda r: (r["score"], r["scorePerPoint"]), reverse=True)[:top],
    }
    if filtered_masteries:
        out["filteredIncompatibleMasteries"] = filtered_masteries
    return out
