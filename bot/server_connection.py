"""
Connection to the Vintage Story server: RCON for commands, log tailing for chat and joins.
"""

import asyncio
import os
import re
import socket
import threading
import struct
from typing import Callable, Optional

from bot.actions import NAME_RE, clean_text
from bot.config import RCON_HOST, RCON_PORT, RCON_PASSWORD, CHAT_LOG_PATH, MAIN_LOG_PATH

# Divine colour styles (VTML, Vintage Story's chat markup)
STYLES = {
    "divine":  ('<i><font color="#AA77FF">',          '</font></i>'),
    "wrath":   ('<strong><font color="#FF4444">',     '</font></strong>'),
    "whisper": ('<i><font color="#999999">',          '</font></i>'),
    "gold":    ('<strong><font color="#FFDD55">',     '</font></strong>'),
    "normal":  ('<strong><font color="#FF8800">',     '</font></strong>'),
    "green":   ('<font color="#55FF55">',             '</font>'),
    "curse":   ('<i><font color="#AA0000">',          '</font></i>'),
    "bless":   ('<strong><font color="#55FFFF">',     '</font></strong>'),
}


class RCONClient:
    def __init__(self, host: str, port: int, password: str):
        self.host     = host
        self.port     = port
        self.password = password
        self._socket: Optional[socket.socket] = None
        self._request_id = 0
        # One socket, several executor threads (state polls, actions): serialise every exchange so
        # a reply is never attributed to another thread's command.
        self._lock = threading.RLock()

    def _create_packet(self, req_id: int, ptype: int, payload: str) -> bytes:
        b = payload.encode("utf-8") + b"\x00\x00"
        return struct.pack("<III", 4 + 4 + len(b), req_id, ptype) + b

    def _read_packet(self) -> tuple:
        raw = self._socket.recv(4)
        if len(raw) < 4:
            raise ConnectionError("Connection closed")
        length = struct.unpack("<I", raw)[0]
        data   = b""
        while len(data) < length:
            chunk = self._socket.recv(length - len(data))
            if not chunk:
                raise ConnectionError("Connection closed mid-packet")
            data += chunk
        # Signed: the server answers a failed login with request id -1.
        req_id = struct.unpack("<i", data[0:4])[0]
        ptype  = struct.unpack("<I", data[4:8])[0]
        return req_id, ptype, data[8:-2].decode("utf-8", errors="replace")

    def connect(self) -> bool:
        with self._lock:
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(10)
                self._socket.connect((self.host, self.port))
                self._request_id += 1
                self._socket.send(self._create_packet(self._request_id, 3, self.password))
                req_id, _, _ = self._read_packet()
                if req_id == -1:
                    print("[RCON] authentication failed: check RCON_PASSWORD")
                    self.disconnect()
                    return False
                return True
            except Exception as e:
                print(f"[RCON] connection error: {e}")
                self._socket = None
                return False

    def send_command(self, command: str) -> str:
        with self._lock:
            if not self._socket:
                if not self.connect():
                    return ""
            try:
                self._request_id += 1
                self._socket.send(self._create_packet(self._request_id, 2, command))
                _, _, payload = self._read_packet()
                return payload
            except Exception as e:
                print(f"[RCON] error: {e}")
                self._socket = None
                if self.connect():
                    try:
                        self._request_id += 1
                        self._socket.send(self._create_packet(self._request_id, 2, command))
                        _, _, payload = self._read_packet()
                        return payload
                    except Exception:
                        self._socket = None
                return ""

    def disconnect(self):
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None


class VintageStoryConnection:
    CHAT_PATTERN         = re.compile(r'\[Chat\] \d+ \| ([\w.\-]+): (.+)')
    PLAYER_JOIN_PATTERN  = re.compile(r'Player ([\w.\-]+) .+joins\.')
    PLAYER_LEAVE_PATTERN = re.compile(r'Player ([\w.\-]+) left\.')

    def __init__(self):
        self.rcon           = RCONClient(RCON_HOST, RCON_PORT, RCON_PASSWORD)
        self.chat_log_path  = CHAT_LOG_PATH
        self.main_log_path  = MAIN_LOG_PATH
        self._running       = False
        self._message_handlers: list[Callable] = []
        self._join_handlers:    list[Callable] = []
        self._leave_handlers:   list[Callable] = []

    def on_message(self, h): self._message_handlers.append(h)
    def on_player_join(self, h): self._join_handlers.append(h)
    def on_player_leave(self, h): self._leave_handlers.append(h)

    async def send_command(self, command: str) -> str:
        print(f"[RCON] > {command[:80]}")
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.rcon.send_command, command)
        if result:
            print(f"[RCON] < {result[:80]}")
        return result

    async def send_message(self, message: str, style: str = "normal"):
        """Broadcast to every player, styled with VTML.

        The text comes from the language model, so it is cleaned first: one
        line, no markup of its own, bounded length.
        """
        safe = clean_text(message, 300)
        if not safe:
            return ""
        open_tag, close_tag = STYLES.get(style, STYLES["normal"])
        return await self.send_command(f'announce {open_tag}{safe}{close_tag}')

    async def send_styled_message(self, message: str, style: str = "divine"):
        return await self.send_message(message, style)

    async def whisper(self, player: str, message: str, style: str = "whisper"):
        """A private message only one player sees."""
        if not NAME_RE.match(player or ""):
            return
        safe = clean_text(message)
        if not safe:
            return
        open_tag, close_tag = STYLES.get(style, STYLES["whisper"])
        await self.send_command(f'tell {player} {open_tag}{safe}{close_tag}')

    async def kick_player(self, player: str, reason: str):
        if not NAME_RE.match(player or ""):
            return
        await self.send_command(f'kick {player} {clean_text(reason, 100)}')

    async def trigger_tempstorm(self):
        """Triggers a temporal storm."""
        await self.send_command("nexttempstorm now")

    async def set_month(self, month: str):
        """Changes the month (and with it the season)."""
        await self.send_command(f"time setmonth {month}")

    async def _process_chat_line(self, line: str):
        m = self.CHAT_PATTERN.search(line)
        if m:
            player, message = m.groups()
            for h in self._message_handlers:
                asyncio.create_task(h(player, message))

    async def _process_main_line(self, line: str):
        m = self.PLAYER_JOIN_PATTERN.search(line)
        if m:
            for h in self._join_handlers:
                asyncio.create_task(h(m.group(1)))
            return
        m = self.PLAYER_LEAVE_PATTERN.search(line)
        if m:
            for h in self._leave_handlers:
                asyncio.create_task(h(m.group(1)))

    async def _watch_log(self, path: str, process_fn, label: str):
        self._running = True
        print(f"[LOG:{label}] waiting for {path}...")
        while self._running and not os.path.exists(path):
            await asyncio.sleep(5)

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            pos = f.tell()

        print(f"[LOG:{label}] started at offset {pos}")
        loop_n = 0

        while self._running:
            try:
                loop_n += 1
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    if size < pos:
                        pos = 0
                    if size > pos:
                        f.seek(pos)
                        for line in f.readlines():
                            line = line.strip()
                            if line:
                                await process_fn(line)
                        pos = f.tell()
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[LOG:{label}] error: {e}")
                await asyncio.sleep(2)

    async def watch_logs(self):
        await asyncio.gather(
            self._watch_log(self.chat_log_path, self._process_chat_line, "CHAT"),
            self._watch_log(self.main_log_path,  self._process_main_line, "MAIN"),
        )

    def stop(self):
        self._running = False
        self.rcon.disconnect()
