"""Builds and runs the BuildBridge plugin inside the fake Paper server (bridge/testkit) for tests."""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[2] / "bridge"
JARS = [
    ("net.kyori", "adventure-api", "4.17.0"),
    ("net.kyori", "adventure-key", "4.17.0"),
    ("net.kyori", "examination-api", "1.3.0"),
    ("net.kyori", "examination-string", "1.3.0"),
    ("net.kyori", "adventure-text-serializer-plain", "4.17.0"),
    ("com.google.code.gson", "gson", "2.11.0"),
    ("org.yaml", "snakeyaml", "2.2"),  # parses plugin.yml like Bukkit
]
CENTRAL = "https://repo1.maven.org/maven2"


class Unavailable(RuntimeError):
    """Java or the library jars are not available: tests using the fake server are skipped."""


def cache_dir() -> Path:
    d = Path(os.environ.get("BUILDMCP_TESTKIT_DIR") or Path.home() / ".cache" / "buildmcp-testkit")
    d.mkdir(parents=True, exist_ok=True)
    return d


def jars() -> list[Path]:
    out = []
    for g, a, v in JARS:
        p = cache_dir() / f"{a}-{v}.jar"
        if not p.exists() or p.stat().st_size < 1000:
            url = f"{CENTRAL}/{g.replace('.', '/')}/{a}/{v}/{a}-{v}.jar"
            last = None
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(url, timeout=60) as r, open(p, "wb") as f:
                        shutil.copyfileobj(r, f)
                    if p.stat().st_size > 1000:
                        break
                except OSError as e:
                    last = e
                time.sleep(2 * (attempt + 1))
            else:
                p.unlink(missing_ok=True)
                raise Unavailable(f"cannot download {url}: {last}")
        out.append(p)
    return out


def build() -> tuple[Path, list[Path]]:
    """Compile stubs + fake server + plugin; cached by source hash. Returns (classes dir, jars)."""
    javac = shutil.which("javac")
    if not javac or not shutil.which("java"):
        raise Unavailable("no JDK (javac/java) on PATH")
    libs = jars()
    sources = sorted(p for d in ("testkit/api-stubs", "testkit/fake-server", "src/main/java")
                     for p in (BRIDGE / d).rglob("*.java"))
    h = hashlib.sha256()
    for p in sources + sorted((BRIDGE / "src/main/resources").iterdir()):
        h.update(p.read_bytes())
    out = cache_dir() / f"classes-{h.hexdigest()[:16]}"
    if not (out / ".ok").exists():
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        cp = os.pathsep.join(str(j) for j in libs)
        r = subprocess.run([javac, "--release", "21", "-nowarn", "-d", str(out), "-cp", cp, *map(str, sources)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("javac failed:\n" + r.stdout + r.stderr)
        for res in (BRIDGE / "src/main/resources").iterdir():
            shutil.copy2(res, out / res.name)
        (out / ".ok").write_text("ok")
    return out, libs


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeServer:
    def __init__(self, data_dir: Path, token: str = "test-token"):
        classes, libs = build()
        self.port = free_port()
        self.token = token
        self.url = f"http://127.0.0.1:{self.port}"
        cp = os.pathsep.join([str(classes), *map(str, libs)])
        env = dict(os.environ)
        env.pop("JAVA_TOOL_OPTIONS", None)
        self.proc = subprocess.Popen(
            ["java", "-Xmx512m", "-cp", cp, "dev.buildmcp.fakeserver.FakeServer", "--port", str(self.port),
             "--data", str(data_dir), "--token", token],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        self.log: list[str] = []
        deadline = time.time() + 60
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            self.log.append(line.rstrip())
            if line.startswith("READY"):
                threading.Thread(target=self._drain, daemon=True).start()
                return
        self.stop()
        raise RuntimeError("fake server did not start:\n" + "\n".join(self.log[-40:]))

    def _drain(self) -> None:
        for line in self.proc.stdout:
            self.log.append(line.rstrip())

    def stop(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
