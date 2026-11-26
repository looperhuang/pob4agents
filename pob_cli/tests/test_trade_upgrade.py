"""`pob trade upgrade`: weakest slots -> live trade per slot -> budget plan + free moves, offline on fakes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner, Result

import pob_cli.cli as cli_mod
from pob_cli.cli import main
from pob_cli.cli_trade import upgrade_cmd
from pob_cli.trade_eval.upgrade import rank_weak_slots, unequip_loss


def test_unequip_loss_weights_dps_and_ehp() -> None:
    res = {"before": {"primaryDps": 100.0, "totalEhp": 1000.0}, "after": {"primaryDps": 90.0, "totalEhp": 800.0}}
    assert unequip_loss(res, {"dps": 1.0, "ehp": 0.25}) == pytest.approx(10.0 + 0.25 * 20.0)
    assert unequip_loss({"before": {}, "after": {}}, {"dps": 1.0}) is None


def test_rank_weak_slots_empty_first() -> None:
    items = {"equippedSlots": [
        {"slotName": "Helmet", "itemId": 3}, {"slotName": "Boots", "itemId": 0},
        {"slotName": "Amulet", "itemId": 5}, {"slotName": "Weapon 2", "itemId": 9},
        {"slotName": "Belt", "itemId": 7, "inactive": True},
    ]}
    ranked = rank_weak_slots(items, {"Helmet": 4.0, "Amulet": 1.5}, top=2)
    assert [(r["slot"], r["tradeSlot"], r["reason"]) for r in ranked] == [
        ("Boots", "boots", "empty"), ("Amulet", "amulet", "lowest contribution")]


def test_rank_weak_slots_unknown_loss_last() -> None:
    items = {"equippedSlots": [{"slotName": "Helmet", "itemId": 3}, {"slotName": "Gloves", "itemId": 4}]}
    assert [r["slot"] for r in rank_weak_slots(items, {"Helmet": None, "Gloves": 2.0}, top=3)] == ["Gloves", "Helmet"]


def _cand(name: str, chaos: float, dps: float, ehp: float = 0.0) -> dict[str, Any]:
    return {"name": name, "price": {"chaos": chaos}, "pob": {"dps_pct": dps, "ehp_pct": ehp}, "url": f"https://x/{name}"}


_AMU = {"slot": "amulet", "candidates": [_cand("A-mid", 50, 12.0), _cand("A-cheap", 5, 2.0)]}
# What a real `trade search --auto-query` saves: PoB's query has stat filters.
_AMU_Q = {**_AMU, "query": {"query": {"stats": [{"type": "weight", "filters": [{"id": "pseudo.x"}]}]}}}
_HELM = {"slot": "helmet", "candidates": [_cand("H-big", 40, 8.0)]}
_RING = {"slot": "ring1", "candidates": [_cand("R-cheap", 10, 5.0)]}
_ITEMS = {"equippedSlots": [{"slotName": "Helmet", "itemId": 3}, {"slotName": "Amulet", "itemId": 5}, {"slotName": "Gloves", "itemId": 4}]}
_LOSS_DPS = {"Amulet": 99.0, "Helmet": 95.0, "Gloves": 50.0}  # primaryDps left after unequipping from 100


class _Calls(list):
    actions: list[str]


def _patch(monkeypatch: Any, *, search: dict[str, Any], respec_error: str | None = None) -> _Calls:
    searched = _Calls()
    searched.actions = []

    def _fake_call(action: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        searched.actions.append(action)
        params = params or {}
        if action == "items":
            return _ITEMS
        if action == "item_unequip":
            after = _LOSS_DPS[params["slot"]]
            return {"before": {"primaryDps": 100.0, "totalEhp": 1000.0}, "after": {"primaryDps": after, "totalEhp": 1000.0}}
        if action == "respec":
            if respec_error:
                raise click.ClickException(respec_error)
            return {"rounds": [], "score": params["score"], "ops": []}
        if action == "rank_gems":
            return {"swaps": [], "groupIndex": 1, "dpsField": "CombinedDPS", "before": 100.0, "after": 100.0}
        raise AssertionError(action)

    def _fake_search(_ctx: Any, trade_slot: str, **_: Any) -> dict[str, Any]:
        searched.append(trade_slot)
        res = search[trade_slot]
        if isinstance(res, Exception):
            raise res
        return res

    monkeypatch.setattr(cli_mod, "_daemon_call", _fake_call)
    monkeypatch.setattr(upgrade_cmd, "_search_slot", _fake_search)
    return searched


def _run(args: list[str]) -> Result:
    return CliRunner().invoke(main, args)


def test_upgrade_json_end_to_end(monkeypatch: Any) -> None:
    searched = _patch(monkeypatch, search={"amulet": _AMU, "helmet": _HELM})
    out = _run(["trade", "upgrade", "--budget", "100", "--top-slots", "2", "--json"])
    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert [s["tradeSlot"] for s in data["slots"]] == list(searched) == ["amulet", "helmet"]
    assert sorted(p["name"] for p in data["plan"]["picks"]) == ["A-mid", "H-big"]
    assert data["skippedSlots"] == []
    assert set(data["free"]) == {"respec", "gems"}
    assert data["free"]["respec"]["score"] == {"primaryDps": 1.0, "totalEhp": 0.25}


def test_upgrade_skips_failed_slot(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={"amulet": _AMU, "helmet": upgrade_cmd._SlotSearchError("rate limited", 4)})
    out = _run(["trade", "upgrade", "--budget", "100", "--top-slots", "2", "--json"])
    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert data["skippedSlots"] == [{"slot": "helmet", "error": "rate limited"}]
    assert [p["slot"] for p in data["plan"]["picks"]] == ["amulet"]


def test_upgrade_free_move_error_is_reported(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={"amulet": _AMU}, respec_error="engine busy")
    data = json.loads(_run(["trade", "upgrade", "--budget", "50", "--slot", "amulet", "--json"]).output)
    assert "engine busy" in data["free"]["respec"]["error"] and data["plan"]["picks"]


def test_upgrade_budget_zero_and_negative(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={"amulet": _AMU})
    assert json.loads(_run(["trade", "upgrade", "--budget", "0", "--slot", "amulet", "--json"]).output)["plan"]["picks"] == []
    assert _run(["trade", "upgrade", "--budget", "-5", "--slot", "amulet"]).exit_code == 1
    for bad in ("nan", "inf"):
        assert _run(["trade", "upgrade", "--budget", bad, "--slot", "amulet"]).exit_code == 1


def test_upgrade_explicit_slots_skip_probe(monkeypatch: Any) -> None:
    calls = _patch(monkeypatch, search={"ring1": _RING})
    data = json.loads(_run(["trade", "upgrade", "--budget", "50", "--slot", "Ring 1", "--json"]).output)
    assert data["slots"][0]["reason"] == "requested" and "item_unequip" not in calls.actions
    assert _run(["trade", "upgrade", "--budget", "50", "--slot", "flask9"]).exit_code == 1


def test_search_slot_invokes_trade_search_with_defaults(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def _fake_callback(**kwargs: Any) -> None:
        seen.update(kwargs)
        Path(kwargs["out_path"]).write_text(json.dumps(_AMU_Q), encoding="utf-8")

    monkeypatch.setattr(upgrade_cmd.cmd_trade_search, "callback", _fake_callback)
    with click.Context(upgrade_cmd.cmd_trade_upgrade) as ctx:
        data = upgrade_cmd._search_slot(ctx, "amulet", per_slot=3, league=None, proxy=None, target="main")
    assert data == _AMU_Q
    assert seen["slot"] == "amulet" and seen["auto_query"] is True and seen["pob_mode"] == "on" and seen["pob_limit"] == 3
    assert seen["max_results"] == 8 and seen["status"] and seen["as_json"] is True  # defaults filled by click


def test_search_slot_turns_nonzero_exit_into_error(monkeypatch: Any) -> None:
    def _fake_callback(**_: Any) -> None:
        click.get_current_context().exit(4)

    monkeypatch.setattr(upgrade_cmd.cmd_trade_search, "callback", _fake_callback)
    with click.Context(upgrade_cmd.cmd_trade_upgrade) as ctx, pytest.raises(upgrade_cmd._SlotSearchError, match="exited 4") as err:
        upgrade_cmd._search_slot(ctx, "amulet", per_slot=3, league=None, proxy=None, target="main")
    assert err.value.exit_code == 4


def test_upgrade_exits_with_trade_code_when_every_search_fails(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={"amulet": upgrade_cmd._SlotSearchError("exited 5", 5),
                                "helmet": upgrade_cmd._SlotSearchError("exited 4", 4)})
    out = _run(["trade", "upgrade", "--budget", "100", "--top-slots", "2", "--json"])
    assert out.exit_code == 4  # rate limit outranks a network error: the agent backs off first
    assert len(json.loads(out.output)["skippedSlots"]) == 2


def test_upgrade_markdown_sections(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={"amulet": _AMU, "helmet": upgrade_cmd._SlotSearchError("rate limited", 4)})
    text = _run(["trade", "upgrade", "--budget", "100", "--top-slots", "2"]).output
    assert "### Upgrade Plan" in text and "- Skipped: helmet (rate limited)" in text
    assert "- Slots searched: Amulet (lowest contribution), Helmet (lowest contribution)" in text
    assert "an estimate" in text and "### Free moves" in text and "### Respec Plan" in text
    assert "### Support Link Optimisation" in text


def test_upgrade_markdown_free_move_error(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={"amulet": _AMU}, respec_error="engine busy")
    text = _run(["trade", "upgrade", "--budget", "50", "--slot", "amulet"]).output
    assert "- respec: engine busy" in text and "### Support Link Optimisation" in text


_REAL_SEARCH_SLOT = upgrade_cmd._search_slot


def _real_search(monkeypatch: Any, *, auto_ok: bool = True) -> None:
    """Run the real `_search_slot`; the inner trade search writes its JSON like the real one does."""
    from pob_cli.cli_common import _emit_json

    def _fake_callback(**kwargs: Any) -> None:
        # Without PoB's query, trade search falls back to a stat-less one.
        _emit_json(_AMU_Q if auto_ok else {**_AMU, "query": {"query": {"stats": [{"type": "and", "filters": []}]}}},
                   out_path=kwargs["out_path"])

    monkeypatch.setattr(upgrade_cmd.cmd_trade_search, "callback", _fake_callback)
    monkeypatch.setattr(upgrade_cmd, "_search_slot", _REAL_SEARCH_SLOT)


def test_upgrade_json_stdout_stays_parseable(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={})
    _real_search(monkeypatch)
    out = _run(["trade", "upgrade", "--budget", "100", "--slot", "amulet", "--json"])
    assert out.exit_code == 0, out.output
    assert json.loads(out.output)["plan"]["picks"]


def test_upgrade_auto_query_failure_is_skipped(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={})
    _real_search(monkeypatch, auto_ok=False)
    data = json.loads(_run(["trade", "upgrade", "--budget", "100", "--slot", "amulet", "--json"]).output)
    assert data["skippedSlots"] == [{"slot": "amulet", "error": "auto-query failed"}] and data["plan"]["picks"] == []


def test_upgrade_probe_failure_keeps_free_moves(monkeypatch: Any) -> None:
    calls = _patch(monkeypatch, search={})
    fake = cli_mod._daemon_call

    def _items_down(action: str, params: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        if action == "items":
            raise click.ClickException("items failed")
        return fake(action, params, **kw)

    monkeypatch.setattr(cli_mod, "_daemon_call", _items_down)
    out = _run(["trade", "upgrade", "--budget", "100", "--json"])
    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert data["free"]["respec"]["rounds"] == [] and data["slots"] == []
    assert data["skippedSlots"] == [{"slot": "*", "error": "slot probe: items failed"}]
    assert "respec" in calls.actions


def test_upgrade_unequip_failure_ranks_slot_last(monkeypatch: Any) -> None:
    _patch(monkeypatch, search={"amulet": _AMU, "helmet": _HELM, "gloves": _HELM})
    fake = cli_mod._daemon_call

    def _amulet_probe_down(action: str, params: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        if action == "item_unequip" and (params or {}).get("slot") == "Amulet":
            raise click.ClickException("probe failed")
        return fake(action, params, **kw)

    monkeypatch.setattr(cli_mod, "_daemon_call", _amulet_probe_down)
    data = json.loads(_run(["trade", "upgrade", "--budget", "100", "--top-slots", "3", "--json"]).output)
    assert [s["tradeSlot"] for s in data["slots"]] == ["helmet", "gloves", "amulet"]
