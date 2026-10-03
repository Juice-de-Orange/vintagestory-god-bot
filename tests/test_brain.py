"""The model client: reply parsing, the system prompt, and the real SDK against a fake API."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from openai import OpenAI

from bot.ai_brain import DeityBrain, parse_reply
from bot.server_state import ServerState


def test_parse_reply_variants():
    assert parse_reply('{"respond": true, "message": "Hi", "actions": []}')["message"] == "Hi"
    fenced = '```json\n{"message": "Hi", "action": {"type": "heal"}}\n```'
    d = parse_reply(fenced)
    assert d["actions"] == [{"type": "heal"}] and d["respond"] is True
    assert parse_reply('Sure! {"respond": false} hope that helps')["respond"] is False
    assert parse_reply("no json at all")["respond"] is False
    assert parse_reply('["a list"]')["actions"] == []
    assert parse_reply('{"actions": "kill everyone"}')["actions"] == []
    assert parse_reply('{"relationship_change": 999}')["relationship_change"] == 20


def _state():
    return ServerState(online_players=["Alice", "Bob"], time_of_day=0.5, season=1,
                       server_reachable=True)


def test_system_prompt_in_both_languages_lists_only_enabled_actions():
    for lang, word in (("de", "Sommer"), ("en", "summer")):
        brain = DeityBrain(client=object(), language=lang, allowed_actions={"give", "time"})
        text = brain.build_system("Alice", 50, "FAVORED", ["helped a newcomer"], [], _state(), "respond")
        assert word in text and "Alice, Bob" in text and "helped a newcomer" in text
        assert '"type":"give"' in text and '"type":"kill"' not in text
        assert "Arathos" in text


def test_prompt_rank_of_a_new_player_and_the_ladder_agree_with_the_code():
    """Issue #12: relationship 0 must not be presented to the model as CURSED."""
    from bot.player_memory import get_divine_rank
    for lang, line, ladder in (
        ("en", "Relationship: 0 | Rank: UNNOTICED", "NOTICED(≥15) · UNNOTICED(in between"),
        ("de", "Beziehung: 0 | Rang: UNBEMERKT", "BEMERKT(≥15) · UNBEMERKT(dazwischen"),
    ):
        brain = DeityBrain(client=object(), language=lang, allowed_actions={"give"})
        text = brain.build_system("Alice", 0, get_divine_rank(0), [], [], _state(), "respond")
        assert line in text and ladder in text
        assert "(≤-25)" in text and "(≤-60)" in text and "(≤-80)" in text


class _FakeChatAPI(BaseHTTPRequestHandler):
    """Just enough of /chat/completions for the openai SDK."""

    requests: list = []
    auth: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeChatAPI.requests.append((self.path, body))
        _FakeChatAPI.auth.append(self.headers.get("Authorization"))
        reply = {"respond": True, "message": "...I see you.", "relationship_change": 2,
                 "actions": [{"type": "give", "item": "torch", "amount": 2}]}
        payload = {
            "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(reply)}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


def test_real_sdk_against_an_openai_compatible_server():
    """Pins the SDK version in requirements.txt to something that still speaks
    plain /chat/completions the way local model servers do."""
    server = HTTPServer(("127.0.0.1", 0), _FakeChatAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = OpenAI(base_url=f"http://127.0.0.1:{server.server_port}/api/v1", api_key="k",
                        max_retries=0)
        brain = DeityBrain(client=client, language="en", allowed_actions={"give"}, model="tiny")
        result = asyncio.run(brain.respond("Alice", "god, help me", 50, "FAVORED", [], [],
                                           _state()))
    finally:
        server.shutdown()

    assert result["message"] == "...I see you."
    assert result["actions"] == [{"type": "give", "item": "torch", "amount": 2}]
    path, body = _FakeChatAPI.requests[-1]
    assert path == "/api/v1/chat/completions"
    assert body["model"] == "tiny"
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][-1]["content"].startswith("Alice: god, help me")


def test_empty_api_key_is_accepted_and_sends_no_authorization_header(monkeypatch):
    """A local server without a key: LOCAL_API_KEY may be empty, the SDK then sends no header."""
    server = HTTPServer(("127.0.0.1", 0), _FakeChatAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("bot.ai_brain.LOCAL_API_KEY", "")
    monkeypatch.setattr("bot.ai_brain.LOCAL_API_BASE_URL",
                        f"http://127.0.0.1:{server.server_port}/api/v1")
    try:
        brain = DeityBrain(language="en", allowed_actions={"give"}, model="tiny")
        result = asyncio.run(brain.respond("Alice", "god, help me", 50, "FAVORED", [], [],
                                           _state()))
    finally:
        server.shutdown()
    assert result["message"] == "...I see you."
    assert _FakeChatAPI.auth[-1] is None
