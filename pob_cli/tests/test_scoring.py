"""`--score` / `--floor`: parsing, weighted % math, and their use in `weights` and `rank-nodes`."""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest
from click.testing import CliRunner

import pob_cli.cli as cli_mod
from pob_cli import comparator
from pob_cli.cli import main
from pob_cli.cli_weights import compute_weights, format_weights_markdown
from pob_cli.scoring import floor_failures, parse_floors, parse_score, weighted_score


def test_parse_score_accepts_repeat_and_commas() -> None:
    assert parse_score(["CombinedDPS=1,TotalEHP=0.5", "Life=2"]) == {"CombinedDPS": 1.0, "TotalEHP": 0.5, "Life": 2.0}
    assert parse_score(None) == {}


@pytest.mark.parametrize("bad", ["CombinedDPS", "CombinedDPS=x", "Life=inf", "1bad=1", "Life=0"])
def test_parse_score_rejects_bad_terms(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_score([bad])


def test_parse_floors() -> None:
    assert parse_floors(["TotalEHP>=8,000", "ManaCost<=50"]) == [("TotalEHP", ">=", 8000.0), ("ManaCost", "<=", 50.0)]
    with pytest.raises(ValueError):
        parse_floors(["TotalEHP>8000"])


def test_weighted_score_and_floor_failures() -> None:
    assert weighted_score({"a": 10.0, "b": 4.0}, {"a": 1.0, "b": 0.5}) == 12.0
    assert weighted_score({"a": 10.0, "b": None}, {"a": 1.0, "b": 0.5}) is None  # unverified, never 0
    assert weighted_score({"a": 10.0}, {"a": 1.0, "b": 0.0}) == 10.0  # zero weight needs no value
    floors = [("x", ">=", 5.0), ("y", "<=", 1.0)]
    assert floor_failures({"x": 5.0, "y": 1.0}, floors) == []
    assert floor_failures({"x": 4.0, "y": None}, floors) == ["x>=5", "y<=1"]


_SWEEP = {
    "baseline": {"summary": {"primaryDpsKey": "CombinedDPS", "primaryDps": 1000, "combinedDps": 1000, "totalEhp": 10000}},
    "variants": [
        {"name": "dmg", "ok": True, "summary": {"primaryDps": 1100, "combinedDps": 1100, "totalEhp": 9000}},
        {"name": "life", "ok": True, "summary": {"primaryDps": 1000, "combinedDps": 1000, "totalEhp": 11500}},
        {"name": "both", "ok": True, "summary": {"primaryDps": 1040, "combinedDps": 1040, "totalEhp": 10400}},
    ],
}


def test_compute_weights_score_and_floor() -> None:
    w = compute_weights(_SWEEP, score={"CombinedDPS": 1.0, "TotalEHP": 0.5}, floors=[("TotalEHP", ">=", 9500.0)])
    # dmg: 10 - 5 = 5 but breaks the floor; life: 7.5; both: 4 + 2 = 6.
    assert [r["mod"] for r in w["weights"]] == ["life", "both", "dmg"]
    assert w["weights"][0]["score"] == pytest.approx(7.5)
    assert w["weights"][2]["floorFail"] == ["TotalEHP>=9500"]
    md = format_weights_markdown(w, target="main")
    assert "Score |" in md and "(breaks TotalEHP>=9500)" in md


def test_compute_weights_default_order_unchanged() -> None:
    assert [r["mod"] for r in compute_weights(_SWEEP)["weights"]] == ["dmg", "both", "life"]


def test_cmd_weights_rejects_unknown_score_stat_before_sweep(monkeypatch: Any) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli_mod, "_daemon_call", lambda action, *_a, **_k: calls.append(action) or {})
    r = CliRunner().invoke(main, ["weights", "--score", "Bogus=1"])
    assert r.exit_code == 1 and "Unknown --score/--floor stat Bogus" in r.output
    r2 = CliRunner().invoke(main, ["weights", "--floor", "TotalEHP>8000"])
    assert r2.exit_code == 1
    assert calls == []


class _ScoredNodeWorker:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.stats_called: list[str] = []

    def call(self, method: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        p = dict(params or {})
        if method == "get_stats":
            return {"stats": {"CombinedDPS": 1000.0, "TotalEHP": "10,000"}}
        if method == "node_power":
            st = p["stat"]
            self.stats_called.append(st)
            if st == "CombinedDPS":
                return {"report": [
                    {"id": 1, "name": "Dmg", "allocated": False, "pathDist": 2, "pathPower": 50.0, "power": 100.0},
                    {"id": 2, "name": "Life", "allocated": False, "pathDist": 1, "pathPower": 0.0, "power": 0.0},
                    {"id": 3, "name": "Owned", "allocated": True, "pathDist": 0, "pathPower": 99.0, "power": 99.0},
                    {"id": 4, "name": "Glass", "allocated": False, "pathDist": 1, "pathPower": 300.0, "power": 300.0},
                ]}
            if st == "TotalEHP":
                return {"report": [
                    {"id": 2, "name": "Life", "allocated": False, "pathDist": 1, "pathPower": 1500.0, "power": 1500.0},
                    {"id": 4, "name": "Glass", "allocated": False, "pathDist": 1, "pathPower": -2000.0, "power": -2000.0},
                ]}
            return {"ok": False, "error": "unknown power stat"}
        if method == "list_items":
            return {"slots": [], "items": []}
        return {}


def test_rank_nodes_scored_merges_stats_and_applies_floor() -> None:
    w = _ScoredNodeWorker()
    res = comparator.rank_nodes_scored(  # type: ignore[arg-type]
        w, score={"CombinedDPS": 1.0, "TotalEHP": 0.5}, floors=[("TotalEHP", ">=", 9000.0)], max_dist=5, top=10
    )
    assert w.stats_called == ["CombinedDPS", "TotalEHP"]
    # Dmg: 10%; Life: 0.5 * 15% = 7.5; Glass: 30 - 10 = 20 but EHP 8000 breaks the floor; Owned is allocated.
    assert [r["name"] for r in res["byTotalGain"]] == ["Dmg", "Life"]
    assert res["byTotalGain"][0]["score"] == pytest.approx(10.0)
    assert res["byPerPoint"][0]["name"] == "Life"  # 7.5 per point beats Dmg's 5
    assert res["floorExcluded"] == 1


def test_rank_nodes_scored_errors_instead_of_falling_back() -> None:
    with pytest.raises(ValueError, match="cannot rank stat `Mana`"):
        comparator.rank_nodes_scored(_ScoredNodeWorkerWithMana(), score={"Mana": 1.0}, floors=[])  # type: ignore[arg-type]


class _ScoredNodeWorkerWithMana(_ScoredNodeWorker):
    def call(self, method: str, params: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        if method == "get_stats":
            return {"stats": {"Mana": 500}}
        return super().call(method, params, **kw)


def test_cmd_rank_nodes_passes_score_and_floors(monkeypatch: Any) -> None:
    captured: list[tuple[str, dict[str, Any], float]] = []

    def _fake_call(action: str, params: dict[str, Any] | None = None, timeout: float = 0, **_: Any) -> dict[str, Any]:
        captured.append((action, dict(params or {}), timeout))
        return {"stat": "score", "score": {"CombinedDPS": 1.0}, "floors": ["Life>=4000"], "floorExcluded": 2,
                "byPerPoint": [{"id": 9, "name": "X", "type": "Notable", "pathDist": 2, "score": 4.0, "scorePerPoint": 2.0,
                                "pcts": {"CombinedDPS": 4.0}}]}

    monkeypatch.setattr(cli_mod, "_daemon_call", _fake_call)
    r = CliRunner().invoke(main, ["rank-nodes", "--score", "CombinedDPS=1", "--floor", "Life>=4000"])
    assert r.exit_code == 0, r.output
    _, params, timeout = captured[-1]
    assert params["score"] == {"CombinedDPS": 1.0} and params["floors"] == [["Life", ">=", 4000.0]]
    assert timeout == 360.0
    assert "CombinedDPS +4.00%" in r.output and "2 node(s) dropped" in r.output
    r2 = CliRunner().invoke(main, ["rank-nodes", "--json"])
    assert "score" not in captured[-1][1]
    assert r2.exit_code == 0
    json.loads(r2.output)


class _RefundWorker:
    def __init__(self) -> None:
        self.lock = threading.RLock()

    def call(self, method: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        assert method == "get_tree_state"
        return {"treeVersion": "3_30", "allocatedNodes": [1, 2, 3, 4, 5, 6]}

    def get_cached_tree_data(self, _v: Any = None) -> dict[str, Any]:
        return {"nodes": {
            "1": {"name": "Start", "type": "ClassStart"},
            "2": {"name": "Dmg", "type": "Notable"},
            "3": {"name": "Life", "type": "Normal"},
            "4": {"name": "Dead", "type": "Normal"},
            "5": {"name": "Hub", "type": "Normal"},
            "6": {"name": "Asc", "type": "Notable", "ascendancyName": "Elementalist"},
        }}


def test_rank_refunds_orders_cheapest_first(monkeypatch: Any) -> None:
    from pob_cli.comparator import rank_refund

    seen: list[list[str]] = []

    def _fake_sweep(_w: Any, variants: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        seen.append([v["ops"][0]["deallocate"][0] for v in variants])
        assert all(v["ops"][0]["allowCascade"] is False for v in variants)

        def _ok(name: str, dps: float, ehp: float, pts: int = -1) -> dict[str, Any]:
            return {"name": name, "ok": True, "steps": [{"op": "tree", "pointsDelta": pts, "orphanedNodes": []}],
                    "summary": {"primaryDps": dps, "totalEhp": ehp}}

        return {
            "baseline": {"summary": {"primaryDps": 1000, "totalEhp": 10000}},
            "variants": [
                _ok("2", 900, 10000),            # -10% DPS
                _ok("3", 1000, 9800),            # -2% EHP
                _ok("4", 1000, 10000),           # free point
                {"name": "5", "ok": False, "error": "Cascade deallocation blocked: 7 orphaned"},
            ],
            "restoreCheck": {"verified": True},
        }

    monkeypatch.setattr(rank_refund, "run_sweep", _fake_sweep)
    res = comparator.rank_refunds(_RefundWorker(), floors=[("totalEhp", ">=", 9900.0)])  # type: ignore[arg-type]
    assert seen == [["2", "3", "4", "5"]]  # start and ascendancy nodes never probed
    assert [r["name"] for r in res["cheapest"]] == ["Dead", "Dmg"]  # Life breaks the EHP floor
    assert res["cheapest"][0]["lossPerPoint"] == pytest.approx(0.0)
    assert res["cheapest"][1]["lossPerPoint"] == pytest.approx(10.0)
    assert res["floorBlocked"] == 1
    assert res["notRefundable"] == [{"id": 5, "name": "Hub", "error": "Cascade deallocation blocked: 7 orphaned"}]


def test_cmd_rank_nodes_refund(monkeypatch: Any) -> None:
    captured: list[dict[str, Any]] = []

    def _fake_call(action: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        captured.append(dict(params or {}))
        return {"stat": "refund", "score": params["score"], "floors": [], "allocatedChecked": 3, "refundable": 1,
                "cheapest": [{"id": 4, "name": "Dead", "type": "Normal", "pointsRefunded": 1, "lossPerPoint": 0.0,
                              "pcts": {"primaryDps": 0.0}}]}

    monkeypatch.setattr(cli_mod, "_daemon_call", _fake_call)
    r = CliRunner().invoke(main, ["rank-nodes", "--refund", "--score", "CombinedDPS=1"])
    assert r.exit_code == 0, r.output
    assert captured[-1]["refund"] is True and captured[-1]["score"] == {"CombinedDPS": 1.0}
    assert "Passive Refund Ranking" in r.output and "Dead" in r.output
    r2 = CliRunner().invoke(main, ["rank-nodes", "--refund", "--score", "Bogus=1"])
    assert r2.exit_code == 1 and len(captured) == 1


class _MasteryWorker(_ScoredNodeWorker):
    """One mastery (id 9) with two effects: effect 11 adds DPS, effect 12 adds EHP."""

    def call(self, method: str, params: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        if method == "node_power":
            row = {"id": 9, "name": "Mastery", "type": "Mastery", "allocated": False, "pathDist": 1}
            dps = {"CombinedDPS": 100.0, "TotalEHP": 0.0}[params["stat"]]
            ehp = {"CombinedDPS": 0.0, "TotalEHP": 1000.0}[params["stat"]]
            return {"report": [{**row, "effectId": 11, "power": dps, "pathPower": dps},
                               {**row, "effectId": 12, "power": ehp, "pathPower": ehp}]}
        return super().call(method, params, **kw)


def test_rank_nodes_scored_keeps_mastery_effects_apart() -> None:
    res = comparator.rank_nodes_scored(  # type: ignore[arg-type]
        _MasteryWorker(), score={"CombinedDPS": 1.0, "TotalEHP": 1.0}, floors=[], top=10
    )
    rows = {r["effectId"]: r for r in res["byTotalGain"]}
    # Each effect scores only its own stat (10% each), never the sum of both effects.
    assert rows[11]["score"] == pytest.approx(10.0) and rows[12]["score"] == pytest.approx(10.0)
    assert rows[11]["allocSpec"] == "9:11" and rows[12]["allocSpec"] == "9:12"


def test_rank_nodes_refund_rejects_stat_and_max_dist(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli_mod, "_daemon_call", lambda *_a, **_k: pytest.fail("no daemon call expected"))
    for extra in (["--stat", "Life"], ["--max-dist", "3"]):
        r = CliRunner().invoke(main, ["rank-nodes", "--refund", *extra])
        assert r.exit_code == 2 and "--refund" in r.output


def test_rank_nodes_scored_takes_summary_names(monkeypatch: Any) -> None:
    from pob_cli.comparator import rank_scored

    monkeypatch.setattr(rank_scored, "capture_digest", lambda _w: {"primaryDpsKey": "CombinedDPS"})
    w = _ScoredNodeWorker()
    res = comparator.rank_nodes_scored(  # type: ignore[arg-type]
        w, score={"primaryDps": 1.0, "totalehp": 0.5}, floors=[("totalEhp", ">=", 9000.0)], max_dist=5, top=10
    )
    assert w.stats_called == ["CombinedDPS", "TotalEHP"]
    assert [r["name"] for r in res["byTotalGain"]] == ["Dmg", "Life"]


def test_rank_refunds_rejects_zero_baseline(monkeypatch: Any) -> None:
    from pob_cli.comparator import rank_refund

    monkeypatch.setattr(rank_refund, "run_sweep", lambda _w, _v, **_: {
        "baseline": {"summary": {"primaryDps": 1000, "energyShield": 0}}, "variants": []})
    with pytest.raises(ValueError, match="energyShield is missing or 0"):
        comparator.rank_refunds(_RefundWorker(), score={"primaryDps": 1.0, "energyShield": 0.5})  # type: ignore[arg-type]
