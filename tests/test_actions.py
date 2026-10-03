"""The policy between the language model and RCON."""
import json

import pytest

from bot.actions import ActionPolicy, ALL_ACTIONS, clean_text, prompt_actions
from bot.config import SAFE_ACTIONS
from bot.texts import texts

THRESHOLDS = {"neutral": 15, "favored": 40, "chosen": 70}
SAFE = set(SAFE_ACTIONS.split(","))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def policy(allowed=SAFE, per_player=3, total=20, clock=None, audit=None):
    return ActionPolicy(set(allowed), THRESHOLDS, per_player, total, 10,
                        audit_path=audit, clock=clock or Clock())


def test_default_set_cannot_hurt_anybody():
    p = policy()
    for kind in ("kill", "clearinv", "smite", "kick", "gamemode", "freeze", "teleport",
                 "tempstorm", "month"):
        d = p.decide("Alice", {"type": kind}, 100, ["Alice", "Bob"])
        assert not d.allowed and "not enabled" in d.reason, kind
        assert d.commands == []


def test_prompt_injection_for_creative_mode_is_refused():
    """The case G01 is about: a player talks the model into a privileged action."""
    d = policy().decide("Mallory", {"type": "gamemode", "mode": "creative"}, 100, ["Mallory"])
    assert not d.allowed
    # Even with the action enabled, the rank gate holds.
    d = policy(SAFE | {"gamemode"}).decide("Mallory", {"type": "gamemode"}, 10, ["Mallory"])
    assert not d.allowed and "rank" in d.reason
    d = policy(SAFE | {"gamemode"}).decide("Mallory", {"type": "gamemode"}, 80, ["Mallory"])
    assert d.allowed and d.commands == ["player Mallory gamemode creative"]


def test_actions_only_target_the_speaker():
    d = policy(SAFE | {"kill"}).decide("Mallory", {"type": "kill", "player": "Bob"}, -90, ["Bob"])
    assert not d.allowed and "only target" in d.reason
    d = policy().decide("Alice", {"type": "heal", "player": "Alice"}, 50, ["Alice"])
    assert d.allowed and d.commands[0] == "player Alice hp set 15"


@pytest.mark.parametrize("item", ["diamond", "bread-spelt 64; op Mallory", "", None, 5])
def test_unknown_or_injected_items_are_refused(item):
    d = policy().decide("Alice", {"type": "give", "item": item}, 50, ["Alice"])
    assert not d.allowed


def test_values_are_clamped():
    p = policy(per_player=99)
    assert p.decide("Alice", {"type": "give", "item": "torch", "amount": 999}, 50, []).commands == [
        "give Alice torch 10"]
    assert p.decide("Alice", {"type": "giveblock", "block": "log-oak", "amount": "-5"}, 50, []).commands == [
        "giveblock log-oak 1 Alice"]
    assert p.decide("Alice", {"type": "intoxicate", "level": 7}, 0, []).commands == [
        "player Alice entity intox 1.00"]
    assert p.decide("Alice", {"type": "time", "hour": 99}, 0, []).commands == ["time set 0.9583"]
    assert p.decide("Alice", {"type": "time", "hour": 12}, 0, []).commands == ["time set noon"]
    assert p.decide("Alice", {"type": "weather", "value": "clear", "intensity": 0.4}, 0, []).commands == [
        "weather setprecip -0.40"]
    assert not p.decide("Alice", {"type": "weather", "value": "lava"}, 0, []).allowed


def test_rank_gates():
    p = policy(per_player=99)
    assert not p.decide("Alice", {"type": "give", "item": "torch"}, 0, []).allowed
    assert not p.decide("Alice", {"type": "heal"}, 20, []).allowed
    assert p.decide("Alice", {"type": "heal"}, 40, []).allowed


def test_hostile_spawns_need_their_own_switch():
    d = policy().decide("Alice", {"type": "spawn", "entity": "drifter-nightmare"}, 0, [])
    assert not d.allowed and "spawn_hostile" in d.reason
    d = policy().decide("Alice", {"type": "spawn", "entity": "chicken-hen", "amount": 50}, 0, [])
    assert d.commands == ["entity spawn chicken-hen 5"]
    d = policy(SAFE | {"spawn_hostile"}).decide("Alice", {"type": "spawn", "entity": "bear-polar"}, 0, [])
    assert d.allowed


def test_teleport_only_to_another_online_player():
    p = policy(SAFE | {"teleport"}, per_player=9)
    assert not p.decide("Alice", {"type": "teleport", "target": "Ghost"}, 0, ["Alice", "Bob"]).allowed
    assert not p.decide("Alice", {"type": "teleport", "target": "Alice"}, 0, ["Alice"]).allowed
    assert p.decide("Alice", {"type": "teleport", "target": "Bob"}, 0, ["Alice", "Bob"]).commands == [
        "tp Alice Bob"]


def test_rate_limit_per_player_and_in_total():
    clock = Clock()
    p = policy(per_player=2, total=3, clock=clock)
    ok = lambda who: p.decide(who, {"type": "time", "hour": 6}, 0, []).allowed  # noqa: E731
    assert ok("Alice") and ok("Alice")
    assert not ok("Alice"), "third action for the same player in the window"
    assert ok("Bob")
    assert not ok("Carol"), "total limit reached"
    clock.now += 601
    assert ok("Alice") and ok("Carol"), "the window has passed"


def test_every_decision_is_audited(tmp_path):
    log = tmp_path / "actions.jsonl"
    p = policy(audit=log)
    p.decide("Alice", {"type": "kill"}, 0, [])
    for delivered in (True, False):
        action = {"type": "time", "hour": 0}
        p.record("Alice", action, p.decide("Alice", action, 0, []), delivered)
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [entry["allowed"] for entry in lines] == [False, True, True]
    assert [entry["delivered"] for entry in lines] == [False, True, False]
    assert lines[1]["commands"] == ["time set midnight"] and lines[1]["reason"] == "ok"
    assert lines[2]["reason"].startswith("not delivered")


def test_whisper_and_kick_text_is_cleaned():
    p = policy(SAFE | {"kick"}, per_player=9)
    d = p.decide("Alice", {"type": "whisper", "message": 'hi <font color="red">x</font>\nannounce boo'}, 0, [])
    assert d.whisper == "hi font color=redx/font announce boo"
    d = p.decide("Alice", {"type": "kick", "reason": "bye\r\nkick Bob"}, 0, [])
    assert d.allowed and d.kick_reason == "bye kick Bob"
    assert clean_text("x" * 500) == "x" * 200


def test_garbage_is_refused():
    p = policy()
    assert not p.decide("Alice", "give me stuff", 0, []).allowed
    assert not p.decide("Alice", {"type": "op"}, 0, []).allowed
    assert not p.decide("bad name;", {"type": "time"}, 0, []).allowed


def test_config_typos_fail_loudly():
    with pytest.raises(ValueError):
        policy({"give", "nuke"})


def test_prompt_lists_only_enabled_actions():
    for lang in ("de", "en"):
        text = prompt_actions(SAFE, texts(lang)["actions"])
        assert '"type":"give"' in text and '"type":"kill"' not in text
        assert "drifter" not in text
    assert set(texts("de")["actions"]) == set(texts("en")["actions"]) == ALL_ACTIONS
