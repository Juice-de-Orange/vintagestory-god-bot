"""
Server state monitor.
Polls time, season and online players via RCON at a fixed interval.
"""

import asyncio
import re
from dataclasses import dataclass, field


@dataclass
class ServerState:
    online_players:  list   = field(default_factory=list)
    time_of_day:     float  = 0.5    # 0.0 = midnight, 0.5 = noon
    total_days:      float  = 0.0
    season:          int    = 0      # 0 = spring, 1 = summer, 2 = autumn, 3 = winter
    month_name:      str    = "Mar"
    is_raining:      bool   = False
    server_reachable: bool  = False

    @property
    def time_key(self) -> str:
        """Part of the day as a key into the text tables (texts.py)."""
        t = self.time_of_day
        if t < 0.08 or t > 0.92: return "midnight"
        if t < 0.25:  return "early_morning"
        if t < 0.42:  return "morning"
        if t < 0.58:  return "noon"
        if t < 0.75:  return "afternoon"
        if t < 0.88:  return "evening"
        return "night"

    @property
    def is_night(self) -> bool:
        return self.time_of_day < 0.22 or self.time_of_day > 0.78

    @property
    def is_midnight(self) -> bool:
        return self.time_of_day < 0.06 or self.time_of_day > 0.96


class ServerStateMonitor:
    """Polls the server state every N seconds."""

    # "Online (2): PlayerOne, PlayerTwo"
    LIST_PATTERN    = re.compile(r'Online \((\d+)\):\s*(.+)')
    LIST_EMPTY      = re.compile(r'Online \(0\)')
    # Time: Vintage Story prints it in a few different shapes
    TOD_PATTERN     = re.compile(r'(?:time of day|tod)[:\s=]+([0-9.]+)', re.I)
    DAYS_PATTERN    = re.compile(r'(?:elapsed days?|total days?)[:\s=]+([0-9.]+)', re.I)
    SEASON_PATTERN  = re.compile(r'(?:season|jahreszeit)[:\s=]+(\w+)', re.I)
    MONTH_PATTERN   = re.compile(r'(?:month)[:\s=]+(\w+)', re.I)

    MONTH_TO_SEASON = {
        "jan": 3, "feb": 3,
        "mar": 0, "apr": 0, "may": 0,
        "jun": 1, "jul": 1, "aug": 1,
        "sep": 2, "oct": 2, "nov": 2,
        "dec": 3,
    }

    def __init__(self, connection):
        self.conn  = connection
        self.state = ServerState()
        self._prev_tod = -1.0

    @property
    def crossed_midnight(self) -> bool:
        """True if midnight was crossed since the last update."""
        return (self._prev_tod > 0.8 and self.state.time_of_day < 0.1) or \
               (self._prev_tod < 0.0 and self.state.is_midnight)

    async def update(self):
        prev_tod    = self.state.time_of_day
        prev_season = self.state.season

        await asyncio.gather(
            self._update_players(),
            self._update_time(),
        )

        self._prev_tod = prev_tod
        return prev_season != self.state.season  # True if the season changed

    async def _update_players(self):
        result = await self.conn.send_command("list")
        if not result:
            return
        self.state.server_reachable = True

        empty = self.LIST_EMPTY.search(result)
        if empty:
            self.state.online_players = []
            return
        match = self.LIST_PATTERN.search(result)
        if match:
            raw   = match.group(2)
            names = [n.strip() for n in raw.split(",") if n.strip()]
            self.state.online_players = names

    async def _update_time(self):
        result = await self.conn.send_command("time")
        if not result:
            return

        tod = self.TOD_PATTERN.search(result)
        if tod:
            val = float(tod.group(1))
            # VS reports the time of day either as hours (0-24) or as a fraction (0-1)
            self.state.time_of_day = val if val <= 1.0 else val / 24.0

        days = self.DAYS_PATTERN.search(result)
        if days:
            self.state.total_days = float(days.group(1))
            # Rough season estimate: one season every 20 in-game days
            self.state.season = int(self.state.total_days / 20) % 4

        month = self.MONTH_PATTERN.search(result)
        if month:
            m = month.group(1).lower()[:3]
            self.state.month_name = m.capitalize()
            if m in self.MONTH_TO_SEASON:
                self.state.season = self.MONTH_TO_SEASON[m]

    async def run(self, interval: float = 30.0):
        """Runs as a background task."""
        while True:
            try:
                await self.update()
            except Exception as e:
                print(f"[STATE] error: {e}")
            await asyncio.sleep(interval)
