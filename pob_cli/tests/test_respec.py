"""`pob respec`: greedy refund+allocate swaps are kept only when PoB shows a net gain, and the build is restored."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from click.testing import CliRunner

import pob_cli.cli as cli_mod
from pob_cli.cli import main
from pob_cli.comparator import respec

# Node id -> (dps, ehp) contribution; 30 is a 2-point path, so it costs more than one refunded point.
_VALUE = {1: (0, 0), 2: (100, 0), 3: (0, 0), 10: (300, 0), 20: (0, 500), 30: (900, 0)}
_COST = {10: 1, 20: 1, 30: 2}


class _Build:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.alloc = {1, 2, 3}
        self.imports: list[str] = []

    def summary(self) -> dict[str, Any]:
        dps = 1000 + sum(_VALUE[n][0] for n in self.alloc)
        ehp = 10000 + sum(_VALUE[n][1] for n in self.alloc)
        return {"primaryDps": dps, "totalEhp": ehp}

    def used(self) -> int:
        return sum(_COST.get(n, 1) for n in self.alloc)

    def call(self, method: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        if method == "export_code":
            return {"code": ",".join(str(n) for n in sorted(self.alloc))}
        if method == "import_code":
            self.imports.append(params["code"])
            self.alloc = {int(x) for x in params["code"].split(",") if x}
            return {}
        if method == "get_tree_state":
            return {"allocatedNodes": sorted(self.alloc), "points": {"used": self.used()}}
        raise AssertionError(method)


@pytest.fixture
def build(monkeypatch: Any) -> _Build:
    b = _Build()

    def _apply(w: _Build, alloc: list[tuple[int, Any]], dealloc: list[tuple[int, Any]], **_: Any) -> Any:
        w.alloc |= {n for n, _ in alloc}
        w.alloc -= {n for n, _ in dealloc}
        return [], {}, [], 0, None

    def _refunds(w: _Build, **_: Any) -> dict[str, Any]:
        return {"cheapest": [{"id": 1, "name": "Dead"}, {"id": 3, "name": "Dead2"}, {"id": 2, "name": "Dmg"}]}

    def _adds(w: _Build, **_: Any) -> dict[str, Any]:
        cands = [{"id": 30, "type": "Notable"}, {"id": 99, "type": "Mastery"}, {"id": 10, "type": "Notable"}, {"id": 20, "type": "Normal"}]
        return {"byPerPoint": [c for c in cands if c["id"] not in w.alloc]}

    monkeypatch.setattr(respec, "_apply_tree_changes_in_place", _apply)
    monkeypatch.setattr(respec, "rank_refunds", _refunds)
    monkeypatch.setattr(respec, "rank_nodes_scored", _adds)
    monkeypatch.setattr(respec, "capture_digest", lambda w: {"stats": w.summary()})
    monkeypatch.setattr(respec, "_compact_sweep_summary", lambda d: d["stats"])
    return b


def test_plan_respec_swaps_and_restores(build: _Build) -> None:
    res = respec.plan_respec(build, score={"primaryDps": 1.0}, rounds=5)  # type: ignore[arg-type]
    # Round 1: refund Dead, 30 needs 2 points so it is rejected, take 10. Round 2: refund Dead2, 20 gives no DPS.
    assert [(r["refund"]["id"], r["add"]["id"]) for r in res["rounds"]] == [(1, 10)]
    assert res["ops"] == [
        {"op": "tree", "deallocate": ["1"], "allowCascade": False},
        {"op": "tree", "allocate": ["10"], "allowCascade": False},
    ]
    assert res["totalGain"] == pytest.approx(300 / 1100 * 100)
    assert build.alloc == {1, 2, 3}  # build left unchanged
    assert res["restoreCheck"]["verified"] is True
    assert build.imports[-1] == "1,2,3"  # BuildTransaction rolled back to the entry build


class _CowBuild(_Build):
    def __init__(self) -> None:
        super().__init__()
        self.caps = {"cowSnapshot": True}
        self.snaps: dict[str, set[int]] = {}

    def call(self, method: str, params: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        if method == "cow_snapshot":
            sid = f"s{len(self.snaps)}"
            self.snaps[sid] = set(self.alloc)
            return {"snapId": sid}
        if method == "cow_restore":
            self.alloc = set(self.snaps[params["snapId"]])
            return {}
        if method == "cow_drop":
            return {}
        if method == "get_stats":
            return {"stats": self.summary()}
        return super().call(method, params, **kw)


def test_plan_respec_rolls_back_through_cow_without_imports(build: _Build) -> None:
    cow = _CowBuild()
    res = respec.plan_respec(cow, score={"primaryDps": 1.0}, rounds=5)  # type: ignore[arg-type]
    assert [(r["refund"]["id"], r["add"]["id"]) for r in res["rounds"]] == [(1, 10)]
    assert cow.alloc == {1, 2, 3}
    assert cow.imports == []  # every rejected try and the final rollback used cow_restore
    assert res["restoreCheck"]["verified"] is True


def test_plan_respec_respects_floor(build: _Build) -> None:
    res = respec.plan_respec(build, score={"primaryDps": 1.0, "totalEhp": 1.0}, floors=[("primaryDps", ">=", 1200.0)])  # type: ignore[arg-type]
    # 20 adds EHP but leaves DPS 1100 < 1200; 10 reaches 1400.
    assert [r["add"]["id"] for r in res["rounds"]][:1] == [10]
    assert build.alloc == {1, 2, 3}


def test_cmd_respec_prints_batch_ops(monkeypatch: Any) -> None:
    captured: list[tuple[str, dict[str, Any]]] = []

    def _fake(action: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        captured.append((action, dict(params or {})))
        return {"score": {"primaryDps": 1.0}, "rounds": [{"refund": {"id": 1, "name": "Dead"}, "add": {"id": 10, "name": "Big"},
                "gain": 27.3, "pointsDelta": 0}], "totalGain": 27.3, "before": {"primaryDps": 1100}, "after": {"primaryDps": 1400},
                "ops": [{"op": "tree", "deallocate": ["1"]}, {"op": "tree", "allocate": ["10"]}]}

    monkeypatch.setattr(cli_mod, "_daemon_call", _fake)
    r = CliRunner().invoke(main, ["respec", "--rounds", "2", "--score", "primaryDps=1"])
    assert r.exit_code == 0, r.output
    assert captured[-1][0] == "respec" and captured[-1][1]["rounds"] == 2
    assert "pob batch --json-ops" in r.output and "Dead (1)" in r.output and "1100 -> 1400" in r.output


def test_rank_score_maps_summary_keys_to_pob_stats() -> None:
    # node_power's stat lookup is case-sensitive and knows no `primaryDps`: summary keys must be translated.
    assert respec._rank_score({"primaryDps": 1.0, "totalEhp": 0.5}, "FullDPS") == {"FullDPS": 1.0, "TotalEHP": 0.5}
    assert respec._rank_score({"life": 1.0, "combinedDps": 2.0}, "CombinedDPS") == {"Life": 1.0, "CombinedDPS": 2.0}
    # Terms PoB cannot rank only leave the ordering; an empty ordering falls back to the primary DPS.
    assert respec._rank_score({"fireResist": 1.0, "physMaxHit": 1.0}, "MinionCombinedDPS") == {"MinionCombinedDPS": 1.0}


def test_plan_respec_ranks_adds_by_pob_stat_names(build: _Build, monkeypatch: Any) -> None:
    seen: list[dict[str, float]] = []

    def _adds(w: _Build, *, score: dict[str, float], **_: Any) -> dict[str, Any]:
        seen.append(dict(score))
        return {"byPerPoint": []}

    monkeypatch.setattr(respec, "rank_nodes_scored", _adds)
    respec.plan_respec(build, rounds=1)  # type: ignore[arg-type]
    assert seen and all(set(s) <= {"CombinedDPS", "FullDPS", "MinionCombinedDPS", "TotalEHP"} for s in seen)


def test_rank_score_ignores_case() -> None:
    assert respec._rank_score({"totalehp": 1.0, "COMBINEDDPS": 2.0}, "FullDPS") == {"TotalEHP": 1.0, "CombinedDPS": 2.0}


def test_plan_respec_only_ranks_adds_the_refund_can_pay_for(build: _Build, monkeypatch: Any) -> None:
    dists: list[int] = []

    def _adds(w: _Build, *, max_dist: int, **_: Any) -> dict[str, Any]:
        dists.append(max_dist)
        return {"byPerPoint": []}

    monkeypatch.setattr(respec, "rank_nodes_scored", _adds)
    respec.plan_respec(build, rounds=1, max_dist=5)  # type: ignore[arg-type]
    assert dists and set(dists) == {1}  # one refunded point pays for a 1-point path only


def test_plan_respec_surfaces_scoring_errors(build: _Build, monkeypatch: Any) -> None:
    def _adds(w: _Build, **_: Any) -> dict[str, Any]:
        raise ValueError("Baseline of EnergyShield is missing or 0")

    monkeypatch.setattr(respec, "rank_nodes_scored", _adds)
    with pytest.raises(ValueError, match="EnergyShield"):
        respec.plan_respec(build, rounds=1)  # type: ignore[arg-type]
    assert build.alloc == {1, 2, 3}  # the transaction still restored the build
