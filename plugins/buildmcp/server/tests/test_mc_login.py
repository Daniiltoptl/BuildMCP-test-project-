"""The CI login client (tests/e2e/mc_login.py) against a fake server: framing, compression, the login
plugin request, login success -> configuration, and disconnect reasons."""

import json
import socket
import sys
import threading
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "e2e"))
import mc_login as M  # noqa: E402


def _serve(behaviour: str):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        s, _ = srv.accept()
        c = M.Conn.__new__(M.Conn)
        c.sock, c.threshold = s, -1
        pid, data = c.recv()                        # handshake
        proto, pos = M.varint_at(data, 0)
        n, pos = M.varint_at(data, pos)
        pos += n + 2
        nxt, _ = M.varint_at(data, pos)
        if nxt == 1:
            c.recv()
            body = json.dumps({"version": {"name": "Paper 1.21.8", "protocol": 772}})
            c.send(0x00, M.string(body))
            s.close()
            return
        pid, data = c.recv()                        # login start
        assert pid == 0x00 and len(data) == 1 + 12 + 16
        if behaviour == "velocity-required":
            c.send(0x04, M.varint(7) + M.string("velocity:player_info") + b"\x04")
            pid, data = c.recv()
            assert pid == 0x02 and data == M.varint(7) + b"\x00"
            c.send(0x00, M.string(json.dumps({"text": "This server requires you to connect with Velocity."})))
            s.close()
            return
        c.send(0x03, M.varint(64))                  # set compression
        c.threshold = 64
        c.send(0x02, b"\x00" * 16 + M.string("BuildMCPTest") + M.varint(0))
        pid, _ = c.recv()
        assert pid == 0x03                          # login acknowledged
        c.send(0x01, M.string("minecraft:brand") + M.string("Velocity") + b"x" * 100)  # compressed on the wire
        if behaviour == "kick":
            c.send(0x02, b"\x08\x00\x04text" + b"Unable to verify player details")
        else:
            c.send(0x0C, M.varint(1) + M.string("minecraft:vanilla"))
        s.close()

    threading.Thread(target=run, daemon=True).start()
    return port


def test_status_and_login_flows():
    assert M.status("127.0.0.1", _serve("ok"))["version"]["protocol"] == 772
    ok = M.login("127.0.0.1", _serve("ok"), 772)
    assert ok["ok"] and ok["seen"] == [0x01, 0x0C]
    kick = M.login("127.0.0.1", _serve("kick"), 772)
    assert not kick["ok"] and kick["stage"] == "configuration" and "Unable to verify player details" in kick["reason"]
    direct = M.login("127.0.0.1", _serve("velocity-required"), 772)
    assert not direct["ok"] and direct["stage"] == "login" and "connect with Velocity" in direct["reason"]
    assert zlib.decompress(zlib.compress(b"x")) == b"x"
