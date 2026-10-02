"""RCON wire format, log parsing and outgoing-text hygiene."""
import asyncio
import socket
import struct
import threading

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
