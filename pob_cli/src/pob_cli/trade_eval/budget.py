"""`pob trade plan`: pick at most one PoB-verified listing per slot to maximise score within a chaos budget.

Inputs are saved `pob trade search --json` payloads, so no network call happens here. Each listing's
delta was verified alone against the current build; summing them across slots is an approximation.
"""

from __future__ import annotations

import math
from typing import Any

PLAN_STATS = ("dps", "ehp")
DEFAULT_PLAN_SCORE: dict[str, float] = {"dps": 1.0, "ehp": 0.25}  # same blend as `combined_pct`
_MAX_UNITS = 5000  # budget resolution; costs are rounded up so the plan never exceeds the budget


def _listing_score(cand: dict[str, Any], score: dict[str, float]) -> float | None:
    pob = cand.get("pob") or {}
    total = 0.0
    for key, weight in score.items():
        if not weight:
            continue
        pct = pob.get(f"{key}_pct")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not math.isfinite(pct):
            return None
        total += weight * pct
    return total


def collect_listings(payloads: list[dict[str, Any]], score: dict[str, float]) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Group priced, PoB-verified, positive-score listings by slot; returns (by_slot, skipped)."""
    by_slot: dict[str, list[dict[str, Any]]] = {}
    skipped = 0
    for payload in payloads:
        slot = str(payload.get("slot") or payload.get("category") or "?")
        for cand in payload.get("candidates") or []:
            chaos = (cand.get("price") or {}).get("chaos")
            value = _listing_score(cand, score)
            if not isinstance(chaos, (int, float)) or chaos < 0 or value is None or value <= 0:
                skipped += 1
                continue
            by_slot.setdefault(slot, []).append(
                {"slot": slot, "listingId": cand.get("listing_id"), "name": cand.get("name"), "chaos": float(chaos), "score": value,
                 "perChaos": value / chaos if chaos > 0 else None, "url": cand.get("url"),
                 "dpsPct": (cand.get("pob") or {}).get("dps_pct"), "ehpPct": (cand.get("pob") or {}).get("ehp_pct")}
            )
    # Ring 1 / Ring 2 searches can return the same listing: keep it once, in the slot where it scores best.
    best: dict[str, dict[str, Any]] = {}
    for item in (i for items in by_slot.values() for i in items if i["listingId"]):
        if item["listingId"] not in best or item["score"] > best[item["listingId"]]["score"]:
            best[item["listingId"]] = item
    by_slot = {s: [i for i in items if not i["listingId"] or best[i["listingId"]] is i] for s, items in by_slot.items()}
    return {s: items for s, items in by_slot.items() if items}, skipped


def plan_budget(payloads: list[dict[str, Any]], *, budget: float, score: dict[str, float] | None = None, top: int = 10) -> dict[str, Any]:
    """Multiple-choice knapsack over slots (at most one listing each) under `budget` chaos."""
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("--budget must be a non-negative number of chaos.")
    score = score or dict(DEFAULT_PLAN_SCORE)
    by_slot, skipped = collect_listings(payloads, score)
    unit = max(1.0, budget / _MAX_UNITS)
    cap = int(budget // unit)
    # best[b] = (score, picks) with total cost <= b units
    best: list[tuple[float, tuple[dict[str, Any], ...]]] = [(0.0, ())] * (cap + 1)
    for listings in by_slot.values():
        nxt = list(best)
        for item in listings:
            cost = math.ceil(item["chaos"] / unit - 1e-9)
            if cost > cap:
                continue
            for b in range(cap, cost - 1, -1):
                cand_score = best[b - cost][0] + item["score"]
                if cand_score > nxt[b][0]:
                    nxt[b] = (cand_score, (*best[b - cost][1], item))
        best = nxt
    total, picks = best[cap]
    every = [item for listings in by_slot.values() for item in listings]
    return {
        "budget": budget,
        "score": score,
        "picks": list(picks),
        "totalChaos": sum(p["chaos"] for p in picks),
        "totalScore": total,
        "bestPerChaos": sorted(every, key=lambda i: (i["perChaos"] is not None, -(i["perChaos"] or 0.0)))[:top],  # free first
        "slots": sorted(by_slot),
        "skippedUnverified": skipped,
    }
