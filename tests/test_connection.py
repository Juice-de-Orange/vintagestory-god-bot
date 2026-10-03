"""RCON wire format, log parsing and outgoing-text hygiene."""
import asyncio
import os
import socket
import struct
import threading

import pytest

from bot.server_connection import RCONClient, VintageStoryConnection


def _rcon_server(responses):
    """A one-connection Source-RCON server: answers each packet with the next response."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    received = []

    def serve():
        conn, _ = srv.accept()
        with conn:
            for reply in responses:
                head = conn.recv(4)
                if len(head) < 4:
                    return
                length = struct.unpack("<I", head)[0]
                data = b""
                while len(data) < length:
                    data += conn.recv(length - len(data))
                req_id, ptype = struct.unpack("<ii", data[:8])
                received.append((ptype, data[8:-2].decode()))
                body = reply.encode() + b"\x00\x00"
                conn.sendall(struct.pack("<iii", 8 + len(body), req_id, 0) + body)

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1], received


def test_rcon_auth_and_command_round_trip():
    port, received = _rcon_server(["", "Online (1): Alice"])
    client = RCONClient("127.0.0.1", port, "secret")
    assert client.send_command("list") == "Online (1): Alice"
    assert received == [(3, "secret"), (2, "list")]
    client.disconnect()


def test_packet_layout():
    pkt = RCONClient("h", 1, "p")._create_packet(7, 2, "time")
    assert pkt == struct.pack("<III", 4 + 4 + 6, 7, 2) + b"time\x00\x00"


def test_chat_and_join_lines_are_parsed():
    conn = VintageStoryConnection()
    seen = []

    async def on_chat(player, msg):
        seen.append(("chat", player, msg))

    async def on_join(player):
        seen.append(("join", player))

    conn.on_message(on_chat)
    conn.on_player_join(on_join)

    async def run():
        await conn._process_chat_line("12.3.2026 18:00:01 [Chat] 0 | Player_One: hello god")
        await conn._process_main_line("Player Player_One [::ffff:192.0.2.1]:4242 joins.")
        await asyncio.sleep(0)

    asyncio.run(run())
    assert ("chat", "Player_One", "hello god") in seen
    assert ("join", "Player_One") in seen


def test_outgoing_text_is_cleaned(monkeypatch):
    conn = VintageStoryConnection()
    sent = []

    async def fake_send(command):
        sent.append(command)
        return ""

    monkeypatch.setattr(conn, "send_command", fake_send)
    asyncio.run(conn.send_message('a "b"\n<strong>c</strong>', style="divine"))
    asyncio.run(conn.whisper("bad name;", "x"))
    asyncio.run(conn.kick_player("Alice", "go\naway"))
    assert sent == ['announce <i><font color="#AA77FF">a b strongc/strong</font></i>',
                    "kick Alice go away"]


def _rcon_server_denying_auth():
    """Server that answers the login with request id -1, as Source RCON does for a wrong password."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        with conn:
            head = conn.recv(4)
            length = struct.unpack("<I", head)[0]
            data = b""
            while len(data) < length:
                data += conn.recv(length - len(data))
            body = b"\x00\x00"
            conn.sendall(struct.pack("<iii", 8 + len(body), -1, 2) + body)

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1]


def test_wrong_password_is_reported_and_not_treated_as_connected(capsys):
    client = RCONClient("127.0.0.1", _rcon_server_denying_auth(), "wrong")
    assert client.connect() is False
    assert "authentication failed" in capsys.readouterr().out
    assert client._socket is None


def test_concurrent_commands_get_their_own_replies():
    """Two threads share one client; each must read the reply to its own command."""
    replies = [""] + [f"reply-{i}" for i in range(20)]
    port, received = _rcon_server(replies)
    client = RCONClient("127.0.0.1", port, "secret")
    assert client.connect()
    results: dict[str, str] = {}

    def run(i: int):
        results[f"cmd-{i}"] = client.send_command(f"cmd-{i}")

    threads = [threading.Thread(target=run, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    client.disconnect()
    # The stub answers in arrival order, so command n (in arrival order) must have got reply n.
    sent = [payload for ptype, payload in received if ptype == 2]
    assert len(sent) == 20
    assert [results[c] for c in sent] == [f"reply-{i}" for i in range(20)]


def _rcon_stub(mode, password="secret", stale=False):
    """A fake RCON server that checks the password and answers commands with `re: <command>`.

    mode "two": the Source convention -- an empty response packet (type 0), then the auth
    response (type 2). mode "one": the auth response alone. A refused login carries id -1.
    stale=True puts a packet with a foreign request id in front of every command reply.
    """
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)

    def packet(req_id, ptype, text=""):
        body = text.encode() + b"\x00\x00"
        return struct.pack("<iii", 8 + len(body), req_id, ptype) + body

    def read(conn):
        head = conn.recv(4)
        if len(head) < 4:
            return None
        length = struct.unpack("<I", head)[0]
        data = b""
        while len(data) < length:
            data += conn.recv(length - len(data))
        req_id, ptype = struct.unpack("<ii", data[:8])
        return req_id, ptype, data[8:-2].decode()

    def serve(conn):
        with conn:
            authed = False
            while (pkt := read(conn)) is not None:
                req_id, ptype, text = pkt
                if ptype == 3:
                    authed = text == password
                    if mode == "two":
                        conn.sendall(packet(req_id, 0))
                    conn.sendall(packet(req_id if authed else -1, 2))
                elif authed:
                    if stale:
                        conn.sendall(packet(req_id - 1, 0, "stale"))
                    conn.sendall(packet(req_id, 0, f"re: {text}"))

    def accept():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=serve, args=(conn,), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    return srv


@pytest.mark.parametrize("mode", ["one", "two"])
def test_right_password_in_both_handshake_conventions(mode):
    """With the two-packet handshake every reply used to be shifted by one command."""
    srv = _rcon_stub(mode)
    client = RCONClient("127.0.0.1", srv.getsockname()[1], "secret")
    assert client.connect() is True
    assert [client.send_command(c) for c in ("list", "time", "list")] == [
        "re: list", "re: time", "re: list"]
    client.disconnect()
    srv.close()


@pytest.mark.parametrize("mode", ["one", "two"])
def test_wrong_password_in_both_handshake_conventions(mode, capsys):
    """With the two-packet handshake a wrong password used to pass as connected."""
    srv = _rcon_stub(mode)
    client = RCONClient("127.0.0.1", srv.getsockname()[1], "wrong")
    assert client.connect() is False
    assert "authentication failed" in capsys.readouterr().out
    assert client._socket is None
    assert not client.send_command("list")
    srv.close()


@pytest.mark.parametrize("mode", ["one", "two"])
def test_stale_packet_before_the_reply_is_discarded(mode):
    srv = _rcon_stub(mode, stale=True)
    client = RCONClient("127.0.0.1", srv.getsockname()[1], "secret")
    assert [client.send_command(c) for c in ("list", "time")] == ["re: list", "re: time"]
    client.disconnect()
    srv.close()


def test_unreachable_server_is_none_not_an_empty_reply():
    """Callers must be able to tell "not delivered" from a command that answers nothing."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    assert RCONClient("127.0.0.1", port, "secret").send_command("list") is None


def test_log_rotation_to_a_file_already_past_the_old_offset(tmp_path):
    """A rotated log that has already grown beyond the old read offset lost its first lines."""
    path = tmp_path / "server-chat.log"
    path.write_text("1.1.2026 10:00:00 [Chat] 0 | Old: before the bot started\n")
    conn = VintageStoryConnection()
    seen = []

    async def collect(line):
        seen.append(line.split("| ")[1])

    async def until(n):
        for _ in range(100):
            if len(seen) >= n:
                return
            await asyncio.sleep(0.1)

    async def run():
        task = asyncio.create_task(conn._watch_log(str(path), collect, "TEST"))
        await asyncio.sleep(0.3)
        with path.open("a") as fh:
            fh.write("[Chat] 0 | Alice: one\n")
        await until(1)
        # Rotate: the old file is moved away and a new, longer one takes its name at once.
        fresh = tmp_path / "fresh.log"
        fresh.write_text("".join(f"[Chat] 0 | Alice: new {i} {'x' * 40}\n" for i in range(5)))
        assert fresh.stat().st_size > path.stat().st_size
        os.rename(path, tmp_path / "server-chat.log.1")
        os.rename(fresh, path)
        await until(6)
        conn._running = False
        await task

    asyncio.run(run())
    assert seen[0] == "Alice: one"
    assert [s[:12] for s in seen[1:]] == [f"Alice: new {i}" for i in range(5)]
