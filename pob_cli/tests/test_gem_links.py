"""`rank-gems --optimize`: support-slot coordinate descent keeps only swaps PoB confirms, then restores."""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest
from click.testing import CliRunner

import pob_cli.cli as cli_mod
from pob_cli.cli import main
from pob_cli.comparator import gem_links

# DPS = 1000 * product of support multipliers; "Liar" ranks high but really lowers DPS.
_MULT = {"A": 1.0, "B": 1.0, "Big": 1.5, "Bigger": 1.6, "Liar": 0.9, "Mid": 1.2}


class _Group:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.gems = ["Skill", "A", "B"]
        self.imports = 0

    def dps(self) -> float:
        out = 1000.0
        for g in self.gems[1:]:
            out *= _MULT[g]
        return out

    def call(self, method: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        if method == "list_skills":
            return {"mainSocketGroup": 1, "groups": [{"index": 1, "gems": [
                {"index": i + 1, "name": g, "support": i > 0} for i, g in enumerate(self.gems)]}]}
        if method == "export_code":
            return {"code": json.dumps(self.gems)}
        if method == "import_code":
            self.imports += 1
            self.gems = json.loads(params["code"])
            return {}
        if method == "get_stats":
            return {"stats": {"CombinedDPS": self.dps()}}
        raise AssertionError(method)


@pytest.fixture
def group(monkeypatch: Any) -> _Group:
    g = _Group()

    def _rank(w: _Group, *, slot_idx: int, **_: Any) -> dict[str, Any]:
        others = [x for i, x in enumerate(w.gems[1:], start=2) if i != slot_idx]
        cands = [c for c in ("Liar", "Bigger", "Big", "Mid") if c not in others]
        return {"candidates": [{"name": c, "delta": 1} for c in cands]}

    def _exec(w: _Group, ops: list[dict[str, Any]], _cache: Any) -> list[dict[str, Any]]:
        for op in ops:
            w.gems[op["gem"] - 1] = op["newGem"]
        return []

    monkeypatch.setattr(gem_links, "rank_gems", _rank)
    monkeypatch.setattr(gem_links, "_execute_batch_ops", _exec)
    monkeypatch.setattr(gem_links, "_BatchCache", lambda w: None)
    monkeypatch.setattr(gem_links, "resolve_skill_group_index", lambda _s, _sel: 1)
    monkeypatch.setattr(gem_links, "capture_digest", lambda w: {})
    return g


def test_optimize_links_skips_liar_and_restores(group: _Group) -> None:
    res = gem_links.optimize_links(group, passes=3)  # type: ignore[arg-type]
    # Slot 2: Liar rejected after a real check, Bigger kept. Slot 3: Liar again rejected, Big kept.
    assert [(s["slot"], s["to"]) for s in res["swaps"]] == [(2, "Bigger"), (3, "Big")]
    assert res["before"] == 1000.0 and res["after"] == pytest.approx(2400.0)
    assert res["ops"] == [
        {"op": "skill", "group": "1", "gem": 2, "newGem": "Bigger"},
        {"op": "skill", "group": "1", "gem": 3, "newGem": "Big"},
    ]
    assert group.gems == ["Skill", "A", "B"]
    assert res["restoreCheck"]["verified"] is True


def test_cmd_rank_gems_optimize(monkeypatch: Any) -> None:
    captured: list[dict[str, Any]] = []

    def _fake(action: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        captured.append(dict(params or {}))
        return {"groupIndex": 1, "dpsField": "CombinedDPS", "before": 1000, "after": 2400, "pct": 140.0,
                "swaps": [{"slot": 2, "from": "A", "to": "Bigger", "dpsBefore": 1000, "dpsAfter": 1600}],
                "ops": [{"op": "skill", "group": "1", "gem": 2, "newGem": "Bigger"}]}

    monkeypatch.setattr(cli_mod, "_daemon_call", _fake)
    r = CliRunner().invoke(main, ["rank-gems", "--optimize", "--passes", "3"])
    assert r.exit_code == 0, r.output
    assert captured[-1]["optimize"] is True and captured[-1]["passes"] == 3
    assert "+140.00%" in r.output and "pob batch --json-ops" in r.output


def test_optimize_links_skips_a_gem_the_skill_op_rejects(group: _Group, monkeypatch: Any) -> None:
    def _exec(w: _Group, ops: list[dict[str, Any]], _cache: Any) -> list[dict[str, Any]]:
        for op in ops:
            if op["newGem"] == "Bigger":
                raise ValueError("gem not found")
            w.gems[op["gem"] - 1] = op["newGem"]
        return []

    monkeypatch.setattr(gem_links, "_execute_batch_ops", _exec)
    res = gem_links.optimize_links(group, passes=3)  # type: ignore[arg-type]
    assert [s["to"] for s in res["swaps"]] == ["Big", "Mid"]
    assert group.gems == ["Skill", "A", "B"]


def test_optimize_links_primary_field_uses_digest_key(group: _Group, monkeypatch: Any) -> None:
    monkeypatch.setattr(gem_links, "capture_digest", lambda w: {"primaryDpsKey": "CombinedDPS"})
    assert gem_links.optimize_links(group, field="primary")["dpsField"] == "CombinedDPS"  # type: ignore[arg-type]


def test_cmd_rank_gems_optimize_rejects_slot_and_top(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli_mod, "_daemon_call", lambda *_a, **_k: pytest.fail("no daemon call expected"))
    for extra in (["--slot", "2"], ["--add-link"], ["--top", "3"]):
        r = CliRunner().invoke(main, ["rank-gems", "--optimize", *extra])
        assert r.exit_code == 2 and "--optimize" in r.output


def test_optimize_links_field_ignores_case_and_rejects_unknown(group: _Group) -> None:
    assert gem_links.optimize_links(group, field="combineddps")["after"] > 1000.0  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="`Bogus` not found"):
        gem_links.optimize_links(group, field="Bogus")  # type: ignore[arg-type]
