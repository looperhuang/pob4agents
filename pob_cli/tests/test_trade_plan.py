"""`pob trade plan`: one listing per slot, max score within budget, offline from saved search JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from pob_cli.cli import main
from pob_cli.trade_eval.budget import plan_budget


def _cand(name: str, chaos: float | None, dps: float | None, ehp: float | None = 0.0) -> dict[str, Any]:
    pob = None if dps is None else {"dps_pct": dps, "ehp_pct": ehp}
    return {"name": name, "price": {"chaos": chaos}, "pob": pob, "url": f"https://x/{name}"}


_RING = {"slot": "Ring 1", "candidates": [_cand("R-cheap", 10, 5.0), _cand("R-big", 80, 20.0), _cand("R-nopob", 5, None)]}
_AMU = {"slot": "Amulet", "candidates": [_cand("A-mid", 50, 12.0), _cand("A-free", 0, 1.0), _cand("A-worse", 5, -3.0)]}


def test_plan_budget_picks_best_combo_within_budget() -> None:
    res = plan_budget([_RING, _AMU], budget=100)
    # R-big + A-free = 80c, 21.0 beats R-cheap + A-mid = 60c, 17.0 (R-big + A-mid = 130c is over budget).
    assert sorted(p["name"] for p in res["picks"]) == ["A-free", "R-big"]
    assert res["totalChaos"] == 80 and res["totalScore"] == pytest.approx(21.0)
    assert res["skippedUnverified"] == 2
    assert res["bestPerChaos"][0]["name"] == "A-free"


def test_plan_budget_one_per_slot_and_rejects_bad_budget() -> None:
    two_rings = {"slot": "Ring 1", "candidates": [_cand("R1", 10, 5.0), _cand("R2", 10, 6.0)]}
    res = plan_budget([two_rings], budget=100)
    assert [p["name"] for p in res["picks"]] == ["R2"]
    with pytest.raises(ValueError):
        plan_budget([two_rings], budget=-1)


def test_plan_budget_ehp_weight() -> None:
    tank = {"slot": "Helmet", "candidates": [_cand("dps", 10, 4.0, 0.0), _cand("tank", 10, 0.0, 10.0)]}
    assert plan_budget([tank], budget=10)["picks"][0]["name"] == "dps"  # default ehp weight 0.25
    assert plan_budget([tank], budget=10, score={"ehp": 1.0})["picks"][0]["name"] == "tank"


def test_cmd_trade_plan(tmp_path: Path) -> None:
    ring, amu = tmp_path / "ring.json", tmp_path / "amu.json"
    ring.write_text(json.dumps(_RING), encoding="utf-8")
    amu.write_text(json.dumps(_AMU), encoding="utf-8")
    r = CliRunner().invoke(main, ["trade", "plan", str(ring), str(amu), "--budget", "100"])
    assert r.exit_code == 0, r.output
    assert "R-big" in r.output and "Spend 80c" in r.output
    bad = CliRunner().invoke(main, ["trade", "plan", str(ring), "--budget", "100", "--score", "life=1"])
    assert bad.exit_code == 1
    missing = CliRunner().invoke(main, ["trade", "plan", str(tmp_path / "nope.json"), "--budget", "1"])
    assert missing.exit_code == 1


def test_plan_budget_buys_a_listing_once_across_slots() -> None:
    same = {**_cand("R-shared", 10, 9.0), "listing_id": "abc"}
    ring1 = {"slot": "Ring 1", "candidates": [same, _cand("R1-other", 10, 2.0)]}
    ring2 = {"slot": "Ring 2", "candidates": [{**same, "pob": {"dps_pct": 7.0, "ehp_pct": 0.0}}, _cand("R2-other", 10, 3.0)]}
    res = plan_budget([ring1, ring2], budget=100)
    # The shared ring stays in Ring 1, where it scores 9; Ring 2 takes its own best.
    assert sorted((p["slot"], p["name"]) for p in res["picks"]) == [("Ring 1", "R-shared"), ("Ring 2", "R2-other")]
    assert res["totalChaos"] == 20
