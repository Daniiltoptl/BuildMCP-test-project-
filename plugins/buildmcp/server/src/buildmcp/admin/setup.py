"""Create a server folder (core, eula, server.properties with RCON, start scripts) or adopt one."""

from __future__ import annotations

import secrets
import shlex
import socket
from pathlib import Path

from . import process, props, registry, software
from .registry import ServerEntry

EULA_TEXT = ("# The server owner accepted the Minecraft EULA (https://aka.ms/MinecraftEULA);\n"
             "# written by BuildMCP on their request.\neula=true\n")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def pick_port(start: int, taken: set[int]) -> int:
    p = start
    while p in taken or not _port_free(p):
        p += 1
        if p > start + 200:
            raise RuntimeError(f"no free port near {start}")
    return p


def _taken_ports() -> set[int]:
    used: set[int] = set()
    for e in registry.load_all().values():
        used.add(int(e.port))
        if e.rcon_port:
            used.add(int(e.rcon_port))
    return used


def write_start_scripts(entry: ServerEntry) -> list[str]:
    """start.sh / start.bat for starting the server by hand with the same flags as BuildMCP."""
    cmd = process.build_command(entry)
    # by hand the console is interactive, so keep JLine (BuildMCP turns it off for its runner)
    cmd = [c for c in cmd if not c.startswith(("-Dterminal.jline", "-Dterminal.ansi"))]
    java = entry.java or "java"
    rest = cmd[1:]
    sh = entry.path / "start.sh"
    sh.write_text("#!/usr/bin/env sh\n# started by hand; BuildMCP starts it with srv_power\ncd \"$(dirname \"$0\")\"\n"
                  f"exec {shlex.quote(java)} {' '.join(shlex.quote(a) for a in rest)}\n", "utf-8")
    try:
        sh.chmod(0o755)
    except OSError:
        pass
    bat = entry.path / "start.bat"
    jq = f'"{java}"' if " " in java else java
    bat.write_text("@echo off\r\nrem started by hand; BuildMCP starts it with srv_power\r\ncd /d \"%~dp0\"\r\n"
                   f"{jq} {' '.join(rest)}\r\npause\r\n", "utf-8")
    return [str(sh), str(bat)]


def create(name: str, dir: str, software_name: str = "paper", version: str = "latest", memory: str = "",
           port: int = 0, accept_eula: bool = False, motd: str = "", online_mode: bool | None = None,
           java: str = "", role: str = "", network: str = "", make_active: bool = True) -> dict:
    name = name.strip().lower()
    if name in registry.load_all():
        raise ValueError(f"server '{name}' already exists (srv_list); pick another name or remove it first")
    path = Path(dir).expanduser()
    if path.exists() and any(path.glob("*.jar")) and (path / "server.properties").exists():
        raise ValueError(f"{path} already has a server: adopt it with srv_setup(name, dir, adopt=True)")
    path.mkdir(parents=True, exist_ok=True)
    sw = software_name.lower()
    got = software.download(sw, version, path)
    is_proxy = sw in registry.PROXIES
    taken = _taken_ports()
    if not port:
        port = pick_port(25577 if is_proxy else 25565, taken)
    taken.add(port)
    e = ServerEntry(name=name, dir=str(path.resolve()), software=sw, version=got["version"], build=got["build"],
                    jar=got["name"], memory=memory or ("1G" if is_proxy else "4G"), java=java, port=int(port),
                    role=role or ("proxy" if is_proxy else ""), network=network)
    report: dict = {"server": name, "dir": e.dir, "core": f"{sw} {got['version']} build {got['build']}",
                    "channel": got.get("channel", "")}
    if got.get("channel") not in ("", "stable", "recommended", None):
        report["warning"] = f"the newest {sw} {got['version']} build is {got['channel']}: expect bugs"
    if not is_proxy:
        if accept_eula:
            (path / "eula.txt").write_text(EULA_TEXT, "utf-8")
        e.rcon_port = pick_port(25575, taken)
        e.rcon_password = secrets.token_urlsafe(24)
        values = {"server-port": e.port, "enable-rcon": True, "rcon.port": e.rcon_port,
                  "rcon.password": e.rcon_password, "broadcast-rcon-to-ops": False}
        if motd:
            values["motd"] = motd
        if online_mode is not None:
            values["online-mode"] = bool(online_mode)
        props.update(path / "server.properties", values)
        report["rcon"] = f"enabled on port {e.rcon_port} (password saved in BuildMCP)"
        if not accept_eula:
            report["eula"] = ("not accepted: the owner must agree to https://aka.ms/MinecraftEULA before the first "
                              "start (ask them, then srv_setup(name, dir, adopt=True, accept_eula=True))")
    report["scripts"] = write_start_scripts(e)
    registry.put(e, make_active=make_active and not is_proxy)
    report["next"] = "srv_power(name, 'start') for the first start: it generates the configs and the world"
    return report


def adopt(name: str, dir: str, accept_eula: bool = False, enable_rcon: bool = True, memory: str = "",
          java: str = "", role: str = "", network: str = "", make_active: bool = True) -> dict:
    name = name.strip().lower()
    e = registry.detect(Path(dir), name)
    if memory:
        e.memory = memory
    if java:
        e.java = java
    e.role, e.network = role or e.role, network or e.network
    report: dict = {"server": name, "dir": e.dir, "detected": f"{e.software} {e.version or '?'} ({e.jar or 'no jar'})"}
    if not e.jar:
        report["warning"] = "no server jar found: put one in the folder (or create a new server with srv_setup)"
    if not e.is_proxy:
        if accept_eula:
            (e.path / "eula.txt").write_text(EULA_TEXT, "utf-8")
        if enable_rcon and not e.rcon_password:
            taken = _taken_ports()
            e.rcon_port = pick_port(25575, taken)
            e.rcon_password = secrets.token_urlsafe(24)
            props.update(e.path / "server.properties", {"enable-rcon": True, "rcon.port": e.rcon_port,
                                                        "rcon.password": e.rcon_password,
                                                        "broadcast-rcon-to-ops": False})
            report["rcon"] = f"enabled on port {e.rcon_port}: takes effect after a restart"
        elif e.rcon_password:
            report["rcon"] = f"already enabled on port {e.rcon_port}"
    if e.jar:
        report["scripts"] = write_start_scripts(e)
    registry.put(e, make_active=make_active and not e.is_proxy)
    return report
