"""
Vintage Story god bot -- the main orchestrator.
"""

import asyncio
import random
import sys
import traceback

from bot.actions import ActionPolicy
from bot.config import (
    ACTION_WINDOW_MIN, ACTIONS_PER_PLAYER, ACTIONS_TOTAL, ALLOWED_ACTIONS, DATA_DIR,
    EXIT_CONFIG, ConfigError, GOD_KEYWORDS, LANGUAGE, MAX_SPONTANEOUS_DAYS, MIN_SPONTANEOUS_DAYS,
    PROB_RESPOND_ADDRESSED, PROB_RESPOND_PASSIVE,
    RANK_CHOSEN, RANK_FAVORED, RANK_NEUTRAL,
)
from bot.player_memory import PlayerMemory, get_divine_rank
from bot.texts import texts


def is_addressed(message: str, keywords: list[str] = GOD_KEYWORDS) -> bool:
    """Does the player speak to the deity directly?"""
    low = message.lower()
    return any(kw in low for kw in keywords)


class GodBot:
    def __init__(self, server=None, brain=None, memory=None, policy=None, language: str = LANGUAGE):
        # Imported here so tests can build a bot from fakes without an LLM or RCON.
        from bot.ai_brain import DeityBrain
        from bot.events import DivineEventEngine
        from bot.server_connection import VintageStoryConnection
        from bot.server_state import ServerStateMonitor

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.t = texts(language)
        self.memory = memory or PlayerMemory(DATA_DIR / "players.db")
        self.server = server or VintageStoryConnection()
        self.brain = brain or DeityBrain(language=language)
        self.policy = policy or ActionPolicy(
            ALLOWED_ACTIONS,
            {"neutral": RANK_NEUTRAL, "favored": RANK_FAVORED, "chosen": RANK_CHOSEN},
            ACTIONS_PER_PLAYER, ACTIONS_TOTAL, ACTION_WINDOW_MIN,
            audit_path=DATA_DIR / "actions.jsonl",
        )
        self.state_monitor = ServerStateMonitor(self.server)
        self.events = DivineEventEngine(self, language=language)

        self.server.on_message(self._handle_chat)
        self.server.on_player_join(self._handle_join)
        self.server.on_player_leave(self._handle_leave)
        print(f"God bot ready. Enabled actions: {', '.join(sorted(self.policy.allowed))}")

    # ------------------------------------------------------------------ #
    #  CHAT                                                                #
    # ------------------------------------------------------------------ #

    async def _handle_chat(self, player: str, message: str):
        try:
            print(f"[CHAT] {player}: {message}")
            addressed = is_addressed(message)
            mode = "respond" if addressed else "observe"

            # Probability gating
            if random.random() > (PROB_RESPOND_ADDRESSED if addressed else PROB_RESPOND_PASSIVE):
                return

            player_data = self.memory.get_or_create_player(player)
            notes = self.memory.get_notes(player, limit=8)
            relationship = player_data["relationship"]
            state = self.state_monitor.state

            result = await self.brain.respond(
                player=player, message=message,
                relationship=relationship, divine_rank=get_divine_rank(relationship),
                player_notes=[n["note"] for n in notes],
                active_effects=self.memory.get_active_effects(player),
                state=state, mode=mode,
            )

            if result.get("respond") and result.get("message"):
                await self.server.send_message(result["message"], style="divine")

            for action in result.get("actions", []):
                await self.execute_action(player, action, relationship, state.online_players)

            change = result.get("relationship_change", 0)
            if change:
                await self._change_relationship(player, change)

            if result.get("note"):
                self.memory.add_note(player, str(result["note"])[:300])

        except Exception as e:  # noqa: BLE001 - one bad message must not stop the bot
            print(f"[CHAT ERROR] {player}: {e}")
            traceback.print_exc()

    async def _change_relationship(self, player: str, change: int, reason: str | None = None):
        old_rank, new_rank = self.memory.update_relationship(player, change, reason)
        if old_rank != new_rank and new_rank in self.t["rank_announce"]:
            style, msg = self.t["rank_announce"][new_rank]
            await self.server.send_message(f"{player}: {msg}", style=style)

    # ------------------------------------------------------------------ #
    #  JOIN / LEAVE                                                        #
    # ------------------------------------------------------------------ #

    async def _handle_join(self, player: str):
        try:
            print(f"[JOIN] {player}")
            player_data = self.memory.get_or_create_player(player)
            days_away = self.memory.days_since_last_seen(player)
            self.memory.record_join(player)
            rank = get_divine_rank(player_data["relationship"])

            # Back after a long absence
            if days_away > 7:
                msg = random.choice(self.t["return_after_absence"])
                await self.server.send_message(
                    msg.format(player=player, days=f"{days_away:.0f}"), style="whisper")
                return

            if random.random() < 0.3:
                if rank == "CHOSEN":
                    await self.server.send_message(self.t["join_chosen"].format(player=player), style="gold")
                elif rank == "FAVORED":
                    await self.server.send_message(self.t["join_favored"].format(player=player), style="divine")
                elif rank in ("FORSAKEN", "HATED"):
                    await self.server.send_message(self.t["join_disliked"], style="curse")

        except Exception as e:  # noqa: BLE001
            print(f"[JOIN ERROR] {player}: {e}")
            traceback.print_exc()

    async def _handle_leave(self, player: str):
        try:
            print(f"[LEAVE] {player}")
            self.memory.record_leave(player)
            if random.random() < 0.1:
                rank = get_divine_rank(self.memory.get_or_create_player(player)["relationship"])
                if rank in ("CHOSEN", "FAVORED"):
                    await self.server.send_message(self.t["leave_liked"].format(player=player), style="whisper")
        except Exception as e:  # noqa: BLE001
            print(f"[LEAVE ERROR] {player}: {e}")

    # ------------------------------------------------------------------ #
    #  ACTIONS                                                             #
    # ------------------------------------------------------------------ #

    async def execute_action(self, player: str, action: object, relationship: int,
                             online_players: list[str]):
        """Run one model-proposed action -- only if the policy allows it."""
        try:
            decision = self.policy.decide(player, action, relationship, online_players)
            if not decision.allowed:
                print(f"[ACTION] refused for {player}: {decision.reason} -- {action}")
                return
            print(f"[ACTION] {player}: {action}")

            delivered = False
            try:
                delivered = await self._deliver(player, decision)
            finally:
                self.policy.record(player, action, decision, delivered)
            if not delivered:
                # Nothing is booked for an action the server never took: no gift, no effect,
                # no relationship change.
                print(f"[ACTION] not delivered to the server for {player}: {action}")
                return

            if decision.gift:
                item, amount = decision.gift
                self.memory.record_gift(player, item, amount, "divine gift")
            if decision.effect:
                kind, effect, days = decision.effect
                self.memory.add_curse_or_blessing(player, kind, effect, expires_days=days)
            if decision.relationship:
                await self._change_relationship(player, decision.relationship,
                                                f"{action.get('type')} by the deity")

        except Exception as e:  # noqa: BLE001
            print(f"[ACTION ERROR] {action}: {e}")
            traceback.print_exc()

    async def _deliver(self, player: str, decision) -> bool:
        """Send everything an allowed action consists of. False as soon as one part fails
        (send_command answers None when the command did not reach the server)."""
        for key, style in decision.announce:
            if await self.server.send_message(self.t[key].format(player=player), style=style) is None:
                return False
        for command in decision.commands:
            if await self.server.send_command(command) is None:
                return False
        if decision.kick_reason is not None:
            if not await self.server.kick_player(player, decision.kick_reason or self.t["kick_reason"]):
                return False
        if decision.whisper:
            if not await self.server.whisper(player, decision.whisper):
                return False
        return True

    # ------------------------------------------------------------------ #
    #  SPONTANEOUS MESSAGES                                                #
    # ------------------------------------------------------------------ #

    async def _spontaneous_messages(self):
        while True:
            try:
                wait = random.uniform(MIN_SPONTANEOUS_DAYS, MAX_SPONTANEOUS_DAYS) * 86400
                print(f"[SPONTANEOUS] next in {wait / 3600:.1f} h")
                await asyncio.sleep(wait)
                if self.state_monitor.state.online_players:
                    msg = random.choice(self.t["spontaneous"])
                    await self.server.send_message(msg, style="divine")
                    print(f"[SPONTANEOUS] sent: {msg}")
            except Exception as e:  # noqa: BLE001
                print(f"[SPONTANEOUS ERROR] {e}")
                await asyncio.sleep(60)

    # ------------------------------------------------------------------ #
    #  RUN                                                                 #
    # ------------------------------------------------------------------ #

    async def run(self):
        print("God bot starting...")
        await asyncio.gather(
            self.server.watch_logs(),
            self.state_monitor.run(interval=30),
            self.events.run(),
            self._spontaneous_messages(),
        )


def main():
    try:
        bot = GodBot()
    except ConfigError as e:
        # One line instead of a traceback: under `restart: unless-stopped` this repeats.
        print(f"[CONFIG] {e}")
        sys.exit(EXIT_CONFIG)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
