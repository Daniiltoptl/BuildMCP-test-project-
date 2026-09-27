"""A tiny Minecraft Java client for CI: a status ping, and an offline-mode login that goes just far
enough to see the server behind a proxy accept the player (it starts the configuration phase) or kick
them, and why. Protocol 1.20.2+ (login acknowledged, configuration state)."""

from __future__ import annotations

import json
import socket
import struct
import time
import uuid
import zlib


def varint(n: int) -> bytes:
    out = bytearray()
    n &= 0xFFFFFFFF
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def varint_at(data: bytes, pos: int) -> tuple[int, int]:
    n = shift = 0
    while True:
        b = data[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            break
        if shift > 35:
            raise ValueError("varint too long")
    return (n - (1 << 32) if n & (1 << 31) else n), pos


def string(s: str) -> bytes:
    b = s.encode("utf-8")
    return varint(len(b)) + b


class Conn:
    def __init__(self, host: str, port: int, timeout: float = 20.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.threshold = -1

    def _exact(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise EOFError("the server closed the connection")
            data += chunk
        return data

    def _varint(self) -> int:
        n = shift = 0
        while True:
            b = self._exact(1)[0]
            n |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                return n
            if shift > 35:
                raise ValueError("varint too long")

    def send(self, pid: int, payload: bytes = b"") -> None:
        body = varint(pid) + payload
        if self.threshold >= 0:
            body = (varint(len(body)) + zlib.compress(body)) if len(body) >= self.threshold else varint(0) + body
        self.sock.sendall(varint(len(body)) + body)

    def recv(self) -> tuple[int, bytes]:
        data = self._exact(self._varint())
        if self.threshold >= 0:
            size, pos = varint_at(data, 0)
            data = zlib.decompress(data[pos:]) if size else data[pos:]
        pid, pos = varint_at(data, 0)
        return pid, data[pos:]

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _text(data: bytes, nbt: bool = False) -> str:
    """A disconnect reason: a JSON string at login, an NBT text component in configuration (shown as its
    readable characters)."""
    if not nbt:
        try:
            n, pos = varint_at(data, 0)
            if 0 < n <= len(data) - pos:
                return data[pos:pos + n].decode("utf-8")
        except (IndexError, UnicodeDecodeError, ValueError):
            pass
    return " ".join("".join(chr(b) if 32 <= b < 127 else " " for b in data).split())


def status(host: str, port: int) -> dict:
    """Server list ping: {"version": {"name", "protocol"}, "description", "players"...}."""
    c = Conn(host, port)
    try:
        c.send(0x00, varint(-1) + string(host) + struct.pack(">H", port) + varint(1))
        c.send(0x00)
        pid, data = c.recv()
        n, pos = varint_at(data, 0)
        return json.loads(data[pos:pos + n].decode("utf-8"))
    finally:
        c.close()


def login(host: str, port: int, protocol: int, name: str = "BuildMCPTest", timeout: float = 30.0) -> dict:
    """Offline-mode login. ok=True once the (backend) server starts the configuration phase."""
    c = Conn(host, port, timeout=timeout)
    state, seen = "login", []
    t0 = time.time()
    try:
        c.send(0x00, varint(protocol) + string(host) + struct.pack(">H", port) + varint(2))
        c.send(0x00, string(name) + uuid.uuid3(uuid.NAMESPACE_OID, "OfflinePlayer:" + name).bytes)
        while time.time() - t0 < timeout:
            pid, data = c.recv()
            if state == "login":
                if pid == 0x03:                                   # set compression
                    c.threshold, _ = varint_at(data, 0)
                elif pid == 0x00:                                 # disconnect
                    return {"ok": False, "stage": "login", "reason": _text(data)}
                elif pid == 0x01:
                    return {"ok": False, "stage": "login", "reason": "encryption requested: the server is in online mode"}
                elif pid == 0x04:                                 # login plugin request: "not understood"
                    mid, _ = varint_at(data, 0)
                    c.send(0x02, varint(mid) + b"\x00")
                elif pid == 0x02:                                 # login success
                    c.send(0x03)                                  # login acknowledged
                    state = "configuration"
            else:
                seen.append(pid)
                if pid == 0x02:                                   # disconnect (configuration)
                    return {"ok": False, "stage": "configuration", "reason": _text(data, nbt=True), "seen": seen}
                if pid == 0x04:                                   # keep alive: answer it
                    c.send(0x04, data)
                if pid in (0x07, 0x0C, 0x0D, 0x0E):               # registry data, feature flags, tags, known packs
                    return {"ok": True, "stage": "configuration", "seen": seen}
        return {"ok": False, "stage": state, "reason": "timeout", "seen": seen}
    except (OSError, EOFError, ValueError, zlib.error) as e:
        return {"ok": False, "stage": state, "reason": f"{type(e).__name__}: {e}", "seen": seen}
    finally:
        c.close()
