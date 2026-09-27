"""Start, stop and watch a server through its runner (see runner.py), read its logs."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from .registry import ServerEntry
from .runner import CONSOLE_LOG, RUN_FILE, STATE_FILE

# Aikar's flags for Paper (https://docs.papermc.io/paper/aikars-flags); big heaps get the 12G+ variant
AIKAR = ["-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions",
         "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch", "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
         "-XX:G1MixedGCLiveThresholdPercent=90", "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32",
         "-XX:+PerfDisableSharedMem", "-XX:MaxTenuringThreshold=1", "-Dusing.aikars.flags=https://mcflags.emc.gs",
         "-Daikars.new.flags=true"]
AIKAR_SMALL = ["-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
               "-XX:G1ReservePercent=20", "-XX:InitiatingHeapOccupancyPercent=15"]
AIKAR_BIG = ["-XX:G1NewSizePercent=40", "-XX:G1MaxNewSizePercent=50", "-XX:G1HeapRegionSize=16M",
             "-XX:G1ReservePercent=15", "-XX:InitiatingHeapOccupancyPercent=20"]
# Velocity's recommended flags (https://docs.papermc.io/velocity/tuning)
VELOCITY_FLAGS = ["-XX:+UseG1GC", "-XX:G1HeapRegionSize=4M", "-XX:+UnlockExperimentalVMOptions",
                  "-XX:+ParallelRefProcEnabled", "-XX:+AlwaysPreTouch", "-XX:MaxInlineLevel=15"]
# plain console (no JLine) and UTF-8 output, so the runner reads a clean log in any locale
CONSOLE_FLAGS = ["-Dterminal.jline=false", "-Dterminal.ansi=false", "-Dfile.encoding=UTF-8",
                 "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8"]

READY_RE = re.compile(r"\bDone \(\d+[.,]\d+s\)!")


class ProcessError(RuntimeError):
    pass


# ------------------------------------------------------------------ java
def java_executable(entry: ServerEntry | None = None) -> str:
    if entry is not None and entry.java:
        return entry.java
    home = os.environ.get("JAVA_HOME", "").strip()
    if home:
        exe = Path(home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if exe.exists():
            return str(exe)
    return shutil.which("java") or "java"


def java_major(java: str) -> int | None:
    """Major version of a java executable (8, 17, 21, 25...), None if it does not run."""
    try:
        r = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
    if not m:
        return None
    major = int(m.group(1))
    return int(m.group(2) or 0) if major == 1 else major


def memory_mb(mem: str) -> int:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([gGmM]?)\s*[bB]?\s*", mem or "")
    if not m:
        raise ValueError(f"bad memory '{mem}': use e.g. 4G or 2048M")
    v = float(m.group(1))
    return int(v * 1024) if m.group(2).lower() in ("g", "") else int(v)


def build_command(entry: ServerEntry) -> list[str]:
    if entry.command:
        return list(entry.command)
    if not entry.jar:
        raise ProcessError(f"{entry.name}: no server jar known (srv_setup downloads one)")
    mb = memory_mb(entry.memory)
    cmd = [java_executable(entry), f"-Xms{mb}M", f"-Xmx{mb}M"]
    if entry.is_proxy:
        cmd += VELOCITY_FLAGS
    else:
        cmd += AIKAR + (AIKAR_BIG if mb > 12 * 1024 else AIKAR_SMALL)
    cmd += CONSOLE_FLAGS + list(entry.jvm_args) + ["-jar", entry.jar]
    if not entry.is_proxy:
        cmd.append("--nogui")
    return cmd


def stop_command(entry: ServerEntry) -> str:
    return "shutdown" if entry.is_proxy else "stop"


# ------------------------------------------------------------------ runner state
def _state_file(entry: ServerEntry) -> Path:
    return entry.state_dir() / STATE_FILE


def console_log(entry: ServerEntry) -> Path:
    return entry.state_dir() / CONSOLE_LOG


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        import psutil

        p = psutil.Process(int(pid))
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except Exception:  # noqa: BLE001 - no such process / access denied
        return False


def runner_state(entry: ServerEntry) -> dict | None:
    try:
        st = json.loads(_state_file(entry).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    st["runner_alive"] = _alive(st.get("runner_pid"))
    st["server_alive"] = _alive(st.get("pid"))
    return st


def is_running(entry: ServerEntry) -> bool:
    st = runner_state(entry)
    if st and (st["server_alive"] or (st["runner_alive"] and st.get("state") in ("starting", "restarting"))):
        return True
    return _port_open(entry.port)


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def _runner_call(entry: ServerEntry, req: dict, timeout: float = 10.0) -> dict:
    st = runner_state(entry)
    if not st or not st.get("runner_alive"):
        raise ProcessError(f"{entry.name}: not started by BuildMCP (no runner). Use RCON or restart it with srv_power")
    req = dict(req, token=st["token"])
    with socket.create_connection(("127.0.0.1", int(st["port"])), timeout=timeout) as s:
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        s.settimeout(timeout)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    resp = json.loads(buf.decode("utf-8") or "{}")
    if not resp.get("ok"):
        raise ProcessError(resp.get("error") or "runner refused")
    return resp


# ------------------------------------------------------------------ start / stop
def _log_size(entry: ServerEntry) -> int:
    try:
        return console_log(entry).stat().st_size
    except OSError:
        return 0


def read_from(entry: ServerEntry, offset: int) -> list[str]:
    try:
        with open(console_log(entry), "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []


def start(entry: ServerEntry, wait: bool = True, timeout: float = 240.0) -> dict:
    if is_running(entry):
        return {"state": "already running", "status": status(entry)}
    if not entry.is_proxy and not _eula_ok(entry.path):
        raise ProcessError("eula.txt is not accepted: the owner has to agree to https://aka.ms/MinecraftEULA "
                           "(srv_setup(..., accept_eula=True) writes it)")
    if not entry.command:
        if not (entry.path / entry.jar).exists():
            raise ProcessError(f"{entry.path / entry.jar} is missing")
        java = java_executable(entry)
        have = java_major(java)
        from .software import java_required

        need = java_required(entry.software, entry.version)
        if have is None:
            raise ProcessError(f"Java not found ({java}). Install Temurin JDK {need}: https://adoptium.net")
        if have < need:
            raise ProcessError(f"{entry.software} {entry.version} needs Java {need}, found Java {have} ({java}). "
                               f"Install Temurin {need} and set it with srv_setup(..., java=path)")
    sd = entry.state_dir()
    (sd / RUN_FILE).write_text(json.dumps({"cmd": build_command(entry), "stop_command": stop_command(entry),
                                           "restart_on_crash": bool(entry.restart_on_crash)}, indent=1), "utf-8")
    try:
        _state_file(entry).unlink()
    except OSError:
        pass
    offset = _log_size(entry)
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                                   | subprocess.CREATE_NO_WINDOW)  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-m", "buildmcp.admin.runner", str(entry.path)], cwd=str(entry.path),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, **kwargs)
    if not wait:
        return {"state": "starting"}
    return wait_ready(entry, offset, timeout)


def wait_ready(entry: ServerEntry, offset: int, timeout: float) -> dict:
    t0 = time.time()
    lines: list[str] = []
    while time.time() - t0 < timeout:
        time.sleep(1.0)
        lines = read_from(entry, offset)
        if any(READY_RE.search(l) for l in lines):
            return {"state": "running", "seconds": round(time.time() - t0, 1), "problems": problems(lines),
                    "pid": (runner_state(entry) or {}).get("pid")}
        st = runner_state(entry)
        if st and st.get("state") in ("stopped", "crashed") and not st.get("server_alive"):
            return {"state": "failed", "problems": problems(lines) or ["the server exited during start"],
                    "tail": lines[-40:]}
        if st is None and time.time() - t0 > 20:
            return {"state": "failed", "problems": ["the runner did not start (see .buildmcp/console.log)"],
                    "tail": lines[-40:]}
    return {"state": "timeout", "seconds": round(time.time() - t0, 1), "problems": problems(lines), "tail": lines[-30:]}


def stop(entry: ServerEntry, timeout: float = 120.0) -> dict:
    st = runner_state(entry)
    t0 = time.time()
    if st and st.get("runner_alive"):
        _runner_call(entry, {"op": "stop"})
    elif _port_open(entry.port):
        _rcon_stop(entry)
    else:
        return {"state": "not running"}
    while time.time() - t0 < timeout:
        time.sleep(1.0)
        st = runner_state(entry)
        if (st is None or not st.get("server_alive")) and not _port_open(entry.port):
            return {"state": "stopped", "seconds": round(time.time() - t0, 1)}
    kill(entry)
    return {"state": "killed", "note": f"did not stop in {timeout:.0f} s"}


def kill(entry: ServerEntry) -> dict:
    st = runner_state(entry) or {}
    import psutil

    killed = []
    try:
        if st.get("runner_alive"):
            _runner_call(entry, {"op": "kill"})
    except Exception:  # noqa: BLE001
        pass
    for key in ("pid", "runner_pid"):
        pid = st.get(key)
        if _alive(pid):
            try:
                psutil.Process(int(pid)).kill()
                killed.append(pid)
            except Exception:  # noqa: BLE001
                pass
    return {"state": "killed", "pids": killed}


def restart(entry: ServerEntry, timeout: float = 240.0) -> dict:
    s = stop(entry, timeout=min(timeout, 120.0))
    time.sleep(1.0)
    r = start(entry, wait=True, timeout=timeout)
    r["stop"] = s
    return r


def status(entry: ServerEntry) -> dict:
    st = runner_state(entry)
    out = {"name": entry.name, "running": is_running(entry), "port_open": _port_open(entry.port)}
    if st:
        out.update({k: st.get(k) for k in ("state", "pid", "crashes")})
        if st.get("started"):
            out["uptime_min"] = round((time.time() - st["started"]) / 60, 1) if out["running"] else 0
    return out


def console(entry: ServerEntry, line: str, wait: float = 1.5) -> list[str]:
    """Type a command into the server console (through the runner); returns the log lines it printed."""
    offset = _log_size(entry)
    _runner_call(entry, {"op": "cmd", "line": line})
    time.sleep(wait)
    return read_from(entry, offset)


def _rcon_stop(entry: ServerEntry) -> None:
    from ..live.rcon import RconClient

    if not (entry.rcon_port and entry.rcon_password):
        raise ProcessError(f"{entry.name} runs outside BuildMCP and has no RCON: stop it in its console")
    c = RconClient("127.0.0.1", entry.rcon_port, entry.rcon_password, timeout=10)
    try:
        c.connect()
        c.command(stop_command(entry))
    finally:
        c.close()


def _eula_ok(path: Path) -> bool:
    try:
        return "eula=true" in (path / "eula.txt").read_text("utf-8").replace(" ", "").lower()
    except OSError:
        return False


# ------------------------------------------------------------------ logs
_PROBLEM_RES = [
    re.compile(p, re.I) for p in (
        r"Could not load '.*' in folder", r"Error occurred while enabling", r"Error occurred while disabling",
        r"Unsupported API version", r"UnknownDependencyException", r"InvalidDescriptionException",
        r"InvalidPluginException", r"Could not pass event", r"Exception", r"\bERROR\]", r"\[.*ERROR.*\]",
        r"FAILED TO BIND TO PORT", r"You need to agree to the EULA", r"UnsupportedClassVersionError",
        r"has been compiled by a more recent version of the Java Runtime", r"Encountered an unexpected exception",
        r"Server thread dump", r"Can't keep up!", r"Unable to access jarfile",
        r"Ambiguous plugin name", r"Plugin .* is not compatible",
    )
]


def problems(lines: list[str], limit: int = 25) -> list[str]:
    """Lines that look like errors: plugins that failed to load or enable, exceptions, bind errors."""
    out = []
    for l in lines:
        if any(r.search(l) for r in _PROBLEM_RES) and not l.lstrip().startswith("at "):
            out.append(l.strip()[:300])
            if len(out) >= limit:
                break
    return out


def log_lines(entry: ServerEntry, lines: int = 60, grep: str = "") -> list[str]:
    """Tail of the server log: logs/latest.log for Paper and Velocity, else the runner's console log."""
    candidates = [entry.path / "logs" / "latest.log", console_log(entry)]
    src = max((p for p in candidates if p.exists()), key=lambda p: p.stat().st_mtime, default=None)
    if src is None:
        return []
    with open(src, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 4 * 1024 * 1024))
        text = f.read().decode("utf-8", errors="replace").splitlines()
    if grep:
        rx = re.compile(grep, re.I)
        text = [l for l in text if rx.search(l)]
    return text[-lines:]
