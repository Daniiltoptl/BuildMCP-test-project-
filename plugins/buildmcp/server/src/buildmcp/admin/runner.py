"""Keeps one Minecraft server (or proxy) running.

It owns the server's console (stdin/stdout), writes everything to ``.buildmcp/console.log``, starts
the server again after a crash (at most 3 times in 10 minutes) and takes console commands from
BuildMCP over a local socket guarded by a random token. BuildMCP starts it detached, so the server
keeps running when Claude Code is closed.

    python -m buildmcp.admin.runner <server folder>

Reads ``.buildmcp/run.json`` ({"cmd": [...], "stop_command": "stop", "restart_on_crash": true}) and
writes ``.buildmcp/runner.json`` (pids, port, token, state) in the server folder.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

RUN_FILE = "run.json"
STATE_FILE = "runner.json"
CONSOLE_LOG = "console.log"
MAX_LOG = 20 * 1024 * 1024
CRASH_WINDOW = 600.0
MAX_CRASHES = 3


def _atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), "utf-8")
    os.replace(tmp, path)


class Runner:
    def __init__(self, root: Path):
        self.root = root
        self.sd = root / ".buildmcp"
        self.cfg = json.loads((self.sd / RUN_FILE).read_text("utf-8"))
        self.token = secrets.token_hex(16)
        self.proc: subprocess.Popen | None = None
        self.state = "starting"
        self.started = 0.0
        self.stopping = False
        self.crashes: list[float] = []
        self.write_lock = threading.Lock()
        log = self.sd / CONSOLE_LOG
        if log.exists() and log.stat().st_size > MAX_LOG:
            os.replace(log, self.sd / "console.1.log")
        self.log = open(log, "a", encoding="utf-8", errors="replace")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]

    # ------------------------------------------------------------ state
    def save_state(self) -> None:
        _atomic_json(self.sd / STATE_FILE, {
            "runner_pid": os.getpid(), "pid": self.proc.pid if self.proc else None, "port": self.port,
            "token": self.token, "state": self.state, "started": self.started, "crashes": len(self.crashes),
            "updated": time.time()})

    def note(self, text: str) -> None:
        with self.write_lock:
            self.log.write(f"[BuildMCP {time.strftime('%H:%M:%S')}] {text}\n")
            self.log.flush()

    # ------------------------------------------------------------ server process
    def spawn(self) -> None:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self.note("starting: " + " ".join(self.cfg["cmd"]))
        self.proc = subprocess.Popen(self.cfg["cmd"], cwd=str(self.root), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
        self.started = time.time()
        self.state = "running"
        self.save_state()
        threading.Thread(target=self.pump, args=(self.proc,), daemon=True).start()

    def pump(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            with self.write_lock:
                self.log.write(line + "\n")
                self.log.flush()

    def send(self, line: str) -> None:
        p = self.proc
        if p is None or p.poll() is not None or p.stdin is None:
            raise RuntimeError("the server is not running")
        p.stdin.write((line.rstrip("\r\n") + "\n").encode("utf-8"))
        p.stdin.flush()

    # ------------------------------------------------------------ control socket
    def serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(10)
            buf = b""
            try:
                while not buf.endswith(b"\n") and len(buf) < 65536:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                req = json.loads(buf.decode("utf-8") or "{}")
            except (OSError, ValueError):
                return
            if not secrets.compare_digest(str(req.get("token", "")), self.token):
                resp = {"ok": False, "error": "bad token"}
            else:
                resp = self.op(req)
            try:
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
            except OSError:
                pass

    def op(self, req: dict) -> dict:
        what = req.get("op")
        try:
            if what == "status":
                return {"ok": True, "state": self.state, "pid": self.proc.pid if self.proc else None,
                        "uptime": round(time.time() - self.started, 1) if self.started else 0,
                        "crashes": len(self.crashes)}
            if what == "cmd":
                self.send(str(req.get("line", "")))
                return {"ok": True}
            if what == "stop":
                self.stopping = True
                self.state = "stopping"
                self.save_state()
                self.send(self.cfg.get("stop_command", "stop"))
                return {"ok": True}
            if what == "kill":
                self.stopping = True
                if self.proc is not None and self.proc.poll() is None:
                    self.proc.kill()
                return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": f"unknown op {what!r}"}

    # ------------------------------------------------------------ main loop
    def run(self) -> int:
        threading.Thread(target=self.serve, daemon=True).start()
        self.spawn()
        while True:
            assert self.proc is not None
            code = self.proc.wait()
            self.note(f"server exited with code {code}")
            if self.stopping or not self.cfg.get("restart_on_crash", True):
                self.state = "stopped"
                break
            now = time.time()
            self.crashes = [t for t in self.crashes if now - t < CRASH_WINDOW] + [now]
            if len(self.crashes) > MAX_CRASHES:
                self.note(f"crashed {len(self.crashes)} times in {int(CRASH_WINDOW / 60)} minutes: giving up")
                self.state = "crashed"
                break
            self.state = "restarting"
            self.save_state()
            time.sleep(5)
            if self.stopping:
                self.state = "stopped"
                break
            self.spawn()
        self.save_state()
        try:
            self.sock.close()
        except OSError:
            pass
        return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m buildmcp.admin.runner <server folder>", file=sys.stderr)
        return 2
    return Runner(Path(args[0]).resolve()).run()


if __name__ == "__main__":
    raise SystemExit(main())
