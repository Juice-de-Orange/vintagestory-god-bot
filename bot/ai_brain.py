"""The deity's brain: a client for any OpenAI-compatible chat API (local models welcome)."""

import asyncio
import json
import traceback

from openai import OpenAI

from bot.actions import prompt_actions
from bot.config import (
    ALLOWED_ACTIONS, DEITY_NAME, LANGUAGE, LOCAL_API_BASE_URL, LOCAL_API_KEY, LOCAL_MODEL,
)
from bot.texts import texts

MAX_PLAYERS = 50
SILENT = {"respond": False, "message": None, "note": None, "relationship_change": 0, "actions": []}


class DeityBrain:
    def __init__(self, client: OpenAI | None = None, language: str = LANGUAGE,
                 allowed_actions: set[str] = ALLOWED_ACTIONS, model: str = LOCAL_MODEL):
        if client is None:
            if not LOCAL_API_KEY:
                raise ValueError("LOCAL_API_KEY is not set")
            client = OpenAI(base_url=LOCAL_API_BASE_URL, api_key=LOCAL_API_KEY)
            print(f"[AI] using {LOCAL_API_BASE_URL}, model {model}")
        self.client = client
        self.model = model
        self.t = texts(language)
        self.actions_text = prompt_actions(allowed_actions, self.t["actions"])
        self._conversations: dict[str, list] = {}
        self._conv_order: list[str] = []

    def _get_history(self, player: str) -> list:
        if player not in self._conversations:
            if len(self._conversations) >= MAX_PLAYERS:
                old = self._conv_order.pop(0)
                del self._conversations[old]
            self._conversations[player] = []
            self._conv_order.append(player)
        else:
            self._conv_order.remove(player)
            self._conv_order.append(player)
        return self._conversations[player]

    def build_system(self, player: str, relationship: int, divine_rank: str,
                     player_notes: list, active_effects: list, state, mode: str) -> str:
        t = self.t
        notes_text = "\n".join(f"- {n}" for n in player_notes[-8:]) if player_notes else t["none"]
        effects_text = (", ".join(f"{e['type']}:{e['effect']}" for e in active_effects)
                        if active_effects else t["none"])
        online = ", ".join(state.online_players) if state.online_players else t["nobody"]
        return t["system"].format(
            deity_name=DEITY_NAME,
            time_name=t["time_names"][state.time_key], time_of_day=state.time_of_day,
            season_name=t["season_names"][state.season], online_players=online,
            is_night=state.is_night,
            player=player, relationship=relationship,
            divine_rank=t["rank_names"][divine_rank],
            player_notes=notes_text, active_effects=effects_text,
            mode_instruction=t["mode_respond"] if mode == "respond" else t["mode_observe"],
            actions=self.actions_text,
        )

    async def respond(self, player: str, message: str, relationship: int,
                      divine_rank: str, player_notes: list, active_effects: list,
                      state, mode: str = "respond") -> dict:
        history = self._get_history(player)
        history.append({"role": "user", "content": f"{player}: {message}\n{self.t['json_only']}"})
        if len(history) > 8:
            self._conversations[player] = history[-8:]
            history = self._conversations[player]

        messages = [
            {"role": "system", "content": self.build_system(
                player, relationship, divine_rank, player_notes, active_effects, state, mode)},
            *history,
        ]
        try:
            # The SDK call is blocking; run it off the event loop so the log
            # watchers keep reading chat while the model thinks.
            resp = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model, max_tokens=500, temperature=0.9, messages=messages,
            )
            raw = (resp.choices[0].message.content or "").strip()
            print(f"[AI] raw: {raw[:150]}")
            result = parse_reply(raw)
        except Exception as exc:  # noqa: BLE001 - a model hiccup must not kill the bot
            print(f"[AI ERROR] {exc}")
            traceback.print_exc()
            result = dict(SILENT)

        history.append({"role": "assistant", "content": result.get("message") or self.t["silent"]})
        return result

    def clear_history(self, player: str):
        if player in self._conversations:
            del self._conversations[player]
            self._conv_order.remove(player)


def parse_reply(text: str) -> dict:
    """Pull the JSON object out of a model reply and normalise its shape.

    Models wrap JSON in code fences, add prose around it, or send a single
    "action" instead of "actions". Anything unparseable means silence.
    """
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    try:
        d = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[AI] JSON error: {exc}")
        return dict(SILENT)
    if not isinstance(d, dict):
        return dict(SILENT)
    if "action" in d and "actions" not in d:
        d["actions"] = [d["action"]] if d["action"] else []
    if not isinstance(d.get("actions"), list):
        d["actions"] = []
    if "respond" not in d:
        d["respond"] = bool(d.get("message"))
    try:
        d["relationship_change"] = max(-20, min(20, int(d.get("relationship_change") or 0)))
    except (TypeError, ValueError):
        d["relationship_change"] = 0
    return d
