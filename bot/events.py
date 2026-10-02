"""
Divine events -- things the deity does on its own, independent of player chat.
Reacts to the time of day, the season and whether anybody is online.
"""

import asyncio
import random
from typing import TYPE_CHECKING

from bot.config import LANGUAGE
from bot.texts import texts

if TYPE_CHECKING:
    from bot.main import GodBot


class DivineEventEngine:
    """Schedules and fires divine events."""

    def __init__(self, bot: "GodBot", language: str = LANGUAGE):
        self.bot = bot
        self.t = texts(language)
        self._last_tod = -1.0
        self._last_season = -1
        self._midnight_fired = False
        self._dawn_fired = False

    async def check(self):
        state = self.bot.state_monitor.state
        if not state.server_reachable or not state.online_players:
            return

        tod = state.time_of_day
        season = state.season

        # --- midnight ---
        is_mid = tod < 0.06 or tod > 0.94
        if is_mid and not self._midnight_fired:
            self._midnight_fired = True
            if random.random() < 0.35:
                await self.bot.server.send_message(random.choice(self.t["midnight"]), style="whisper")
        elif not is_mid:
            self._midnight_fired = False

        # --- dawn ---
        is_dawn = 0.22 <= tod <= 0.28
        if is_dawn and not self._dawn_fired:
            self._dawn_fired = True
            if random.random() < 0.2:
                await self.bot.server.send_message(random.choice(self.t["dawn"]), style="divine")
        elif not is_dawn:
            self._dawn_fired = False

        # --- season change ---
        if self._last_season != -1 and season != self._last_season:
            msgs = self.t["seasons"].get(season, [self.t["season_default"]])
            await self.bot.server.send_message(random.choice(msgs), style="divine")
            # Weather to match the new season
            if season == 3:    # winter
                await self.bot.server.send_command("weather setprecip 0.3")
            elif season == 1:  # summer
                await self.bot.server.send_command("weather setprecip -0.5")

        self._last_tod = tod
        self._last_season = season

    async def run(self):
        while True:
            try:
                await self.check()
            except Exception as e:  # noqa: BLE001 - one bad tick must not stop the loop
                print(f"[EVENTS] error: {e}")
            await asyncio.sleep(15)
