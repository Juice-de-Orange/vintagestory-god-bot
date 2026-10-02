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


class _FakeChatAPI(BaseHTTPRequestHandler):
    """Just enough of /chat/completions for the openai SDK."""

    requests: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeChatAPI.requests.append((self.path, body))
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
