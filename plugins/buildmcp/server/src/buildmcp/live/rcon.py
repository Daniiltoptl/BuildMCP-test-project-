"""Minecraft RCON client.

The vanilla/Paper RCON server reads one packet per socket read and expects exactly one packet in it,
so requests are strictly sequential (no pipelining) and a packet may not exceed 1460 bytes
(1446 bytes of command text).
"""

from __future__ import annotations

import socket
import struct
import threading

MAX_COMMAND_BYTES = 1446
TYPE_LOGIN = 3
TYPE_COMMAND = 2
TYPE_RESPONSE = 0


class RconError(RuntimeError):
    pass


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 15.0):
        self.host, self.port, self.password, self.timeout = host, int(port), password, timeout
        self._sock: socket.socket | None = None
        self._id = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------ connection
    def connect(self) -> "RconClient":
        if self._sock is not None:
            return self
        try:
            s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as e:
            raise RconError(f"cannot connect to RCON {self.host}:{self.port}: {e}") from e
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = s
        rid = self._send(TYPE_LOGIN, self.password)
        while True:
            pid, ptype, _ = self._recv()
            if pid == -1:
                self.close()
                raise RconError("RCON login failed: wrong rcon.password")
            if pid == rid and ptype == TYPE_COMMAND:
                return self

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "RconClient":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    # -------------------------------------------------------------- packets
    def _send(self, ptype: int, body: str) -> int:
        self._id = (self._id + 1) % 0x7FFFFFFF or 1
        payload = body.encode("utf-8")
        if len(payload) > MAX_COMMAND_BYTES:
            raise RconError(f"RCON command too long ({len(payload)} bytes, max {MAX_COMMAND_BYTES})")
        pkt = struct.pack("<iii", len(payload) + 10, self._id, ptype) + payload + b"\x00\x00"
        assert self._sock is not None
        self._sock.sendall(pkt)
        return self._id

    def _read_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                self.close()
                raise RconError("RCON connection closed by the server")
            buf += chunk
        return bytes(buf)

    def _recv(self) -> tuple[int, int, str]:
        (length,) = struct.unpack("<i", self._read_exact(4))
        if length < 10 or length > 1 << 20:
            self.close()
            raise RconError(f"bad RCON packet length {length}")
        data = self._read_exact(length)
        pid, ptype = struct.unpack("<ii", data[:8])
        return pid, ptype, data[8:-2].decode("utf-8", errors="replace")

    # -------------------------------------------------------------- commands
    def command(self, cmd: str) -> str:
        """Run one command and return its output (long outputs arrive in several packets)."""
        with self._lock:
            self.connect()
            try:
                rid = self._send(TYPE_COMMAND, cmd.removeprefix("/"))
                pid, _, text = self._recv()
                if pid != rid:
                    raise RconError(f"RCON answer for request {pid}, expected {rid}")
                if len(text.encode("utf-8")) < 4096:
                    return text
                # a full 4096-byte packet may be followed by more: probe with an unknown request type
                parts = [text]
                probe = self._send(200, "")
                while True:
                    pid, _, more = self._recv()
                    if pid == probe:
                        return "".join(parts)
                    parts.append(more)
            except (OSError, struct.error) as e:
                self.close()
                raise RconError(f"RCON error: {e}") from e

    def run_many(self, commands: list[str], on_progress=None, every: int = 200) -> list[str]:
        out = []
        for i, c in enumerate(commands):
            out.append(self.command(c))
            if on_progress and (i + 1) % every == 0:
                on_progress(i + 1, len(commands))
        return out
