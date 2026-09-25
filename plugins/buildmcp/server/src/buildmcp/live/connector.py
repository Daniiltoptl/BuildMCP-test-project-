"""Connection to the Minecraft server: BuildBridge (best quality) or RCON (fallback).

Settings come from the plugin configuration (environment) and from connection.json in the BuildMCP
data folder (written by bridge_install when it finds the token in the server folder).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass

from ..blocks.registry import DEFAULT_VERSION, resolve_version
from .bridge import BridgeClient, BridgeError
from .bundle import Bundle
from .rcon import RconClient, RconError

STRICT_PROBE = "execute if block 0 -64 0 minecraft:bedrock run setblock 0 -64 0 minecraft:bedrock strict"


def _env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    return "" if v.startswith("${") else v


@dataclass
class Settings:
    bridge_url: str = "http://127.0.0.1:8765"
    bridge_token: str = ""
    rcon_host: str = "127.0.0.1"
    rcon_port: int = 25575
    rcon_password: str = ""
    server_dir: str = ""
    mc_version: str = "auto"

    def public(self) -> dict:
        d = asdict(self)
        d["bridge_token"] = "set" if self.bridge_token else ""
        d["rcon_password"] = "set" if self.rcon_password else ""
        return d


def _connection_file():
    from ..render.assets import data_dir

    return data_dir() / "connection.json"


def load_settings() -> Settings:
    s = Settings()
    try:
        saved = json.loads(_connection_file().read_text("utf-8"))
    except (OSError, ValueError):
        saved = {}
    for k in asdict(s):
        if saved.get(k) not in (None, ""):
            setattr(s, k, type(getattr(s, k))(saved[k]))
    env = {"bridge_url": "BUILDMCP_BRIDGE_URL", "bridge_token": "BUILDMCP_BRIDGE_TOKEN", "rcon_host": "BUILDMCP_RCON_HOST",
           "rcon_port": "BUILDMCP_RCON_PORT", "rcon_password": "BUILDMCP_RCON_PASSWORD",
           "server_dir": "BUILDMCP_SERVER_DIR", "mc_version": "BUILDMCP_MC_VERSION"}
    for k, var in env.items():
        v = _env(var)
        if v:
            try:
                setattr(s, k, type(getattr(s, k))(float(v)) if k == "rcon_port" else v)
            except ValueError:
                pass
    return s


def save_settings(**values) -> None:
    f = _connection_file()
    try:
        cur = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        cur = {}
    cur.update({k: v for k, v in values.items() if v not in (None, "")})
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cur, indent=1), "utf-8")


class NotConnected(RuntimeError):
    pass


SETUP_HINT = (
    "How to connect: install the BuildBridge plugin (bridge_install, or copy BuildBridge.jar into plugins/ and restart), "
    "then put the token from plugins/BuildBridge/config.yml into the BuildMCP plugin settings (bridge_token). "
    "Fallback without a plugin: enable-rcon=true, rcon.password=... in server.properties and set rcon_password."
)


# ======================================================================= base
class Connection:
    kind = ""
    features: tuple[str, ...] = ()

    def describe(self) -> str:
        raise NotImplementedError

    @property
    def key(self) -> str:
        from .deploy import server_key

        return server_key(self.describe())

    def status(self) -> dict:
        raise NotImplementedError

    def version(self) -> str:
        raise NotImplementedError

    def command(self, cmd: str, world: str | None = None) -> list[str]:
        raise NotImplementedError

    def player(self, name: str = "") -> dict:
        raise NotImplementedError

    def teleport(self, player: str, pos, yaw=None, pitch=None, world: str | None = None) -> dict:
        raise NotImplementedError

    def paste(self, bundle: Bundle, wait: bool = True, timeout: float = 1200.0, on_progress=None) -> dict:
        raise NotImplementedError

    def need(self, feature: str) -> None:
        if feature not in self.features:
            raise NotConnected(f"'{feature}' needs the BuildBridge plugin (connected via {self.kind}). {SETUP_HINT}")

    def close(self) -> None:
        pass


# ===================================================================== bridge
class BridgeConnection(Connection):
    kind = "bridge"
    features = ("paste", "undo", "backups", "jobs", "read", "heightmap", "player", "teleport", "command")

    def __init__(self, client: BridgeClient):
        self.client = client
        self._status: dict | None = None

    def describe(self) -> str:
        return "bridge " + re.sub(r"^https?://", "", self.client.url)

    def status(self) -> dict:
        self._status = self.client.status()
        return self._status

    def version(self) -> str:
        st = self._status or self.status()
        return resolve_version(st.get("minecraft") or DEFAULT_VERSION)

    def data_version(self) -> int:
        st = self._status or self.status()
        return int(st.get("data_version", 0))

    def command(self, cmd: str, world: str | None = None) -> list[str]:
        return self.client.command(cmd, world)["output"]

    def player(self, name: str = "") -> dict:
        return self.client.player(name)

    def teleport(self, player: str, pos, yaw=None, pitch=None, world: str | None = None) -> dict:
        return self.client.teleport(player, pos, yaw, pitch, world)

    def paste(self, bundle: Bundle, wait: bool = True, timeout: float = 1200.0, on_progress=None) -> dict:
        job = self.client.paste(bundle)
        if not wait:
            return job
        return self.client.wait(job["id"], timeout=timeout, on_progress=on_progress)

    def close(self) -> None:
        self.client.close()


# ======================================================================= rcon
class RconConnection(Connection):
    kind = "rcon"
    features = ("paste", "player", "teleport", "command")

    def __init__(self, client: RconClient, version_hint: str | None = None):
        self.client = client
        self._version = version_hint
        self._strict: bool | None = None

    def describe(self) -> str:
        return f"rcon {self.client.host}:{self.client.port}"

    def strict_supported(self) -> bool:
        if self._strict is None:
            out = self.client.command(STRICT_PROBE).lower()
            self._strict = not ("incorrect" in out or "unknown" in out or "expected" in out)
        return self._strict

    def version(self) -> str:
        if self._version:
            return resolve_version(self._version)
        return resolve_version("1.21.5" if self.strict_supported() else DEFAULT_VERSION)

    def status(self) -> dict:
        out = self.client.command("list")
        m = re.search(r":\s*(.*)$", out.strip())
        players = [p.strip() for p in (m.group(1) if m else "").split(",") if p.strip()]
        return {"method": "rcon", "players_online": players, "list": out.strip(),
                "strict_placement": self.strict_supported(), "version_used": self.version()}

    def command(self, cmd: str, world: str | None = None) -> list[str]:
        pre = f"execute in {world} run " if world and ":" in world else ""
        return [self.client.command(pre + cmd)]

    def _online(self) -> list[str]:
        return self.status()["players_online"]

    def player(self, name: str = "") -> dict:
        if not name:
            online = self._online()
            if not online:
                raise NotConnected("nobody is online")
            name = online[0]
        pos = _nums(self.client.command(f"data get entity {name} Pos"))
        rot = _nums(self.client.command(f"data get entity {name} Rotation"))
        dim = re.search(r'"([a-z0-9_.-]+:[a-z0-9_/.-]+)"', self.client.command(f"data get entity {name} Dimension"))
        if len(pos) < 3:
            raise NotConnected(f"player '{name}' is not online")
        return {"name": name, "pos": pos[:3], "block": [int(v // 1) for v in pos[:3]],
                "yaw": rot[0] if rot else 0.0, "pitch": rot[1] if len(rot) > 1 else 0.0,
                "world": dim.group(1) if dim else "minecraft:overworld"}

    def teleport(self, player: str, pos, yaw=None, pitch=None, world: str | None = None) -> dict:
        who = player or (self._online() or [""])[0]
        if not who:
            raise NotConnected("nobody is online")
        rot = f" {float(yaw or 0):.1f} {float(pitch or 0):.1f}" if yaw is not None or pitch is not None else ""
        pre = f"execute in {world} run " if world and ":" in world else ""
        out = self.client.command(f"{pre}tp {who} {pos[0]:.3f} {pos[1]:.3f} {pos[2]:.3f}{rot}")
        return {"name": who, "output": out}

    def paste(self, bundle: Bundle, wait: bool = True, timeout: float = 1200.0, on_progress=None) -> dict:
        from .placer import plan_commands, run_plan

        world = bundle.header.get("world")
        plan = plan_commands(bundle, self.version(), dimension=world if world and ":" in world else None,
                             entity_tag=bundle.header.get("entity_tag"), strict=self.strict_supported())
        res = run_plan(self.client, plan, on_progress=(lambda ph, d, t: on_progress(
            {"phase": ph, "done": d, "total": t})) if on_progress else None)
        res.update({"phase": "done", "method": "rcon", "placed": bundle.changed_cells()})
        return res

    def close(self) -> None:
        self.client.close()


def _nums(text: str) -> list[float]:
    body = text.split(":", 1)[-1]
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?(?=[dfDF]?\b)", body)]


# ================================================================== connect
_CACHE: dict = {"conn": None, "method": None, "time": 0.0}


def connect(method: str = "auto", version_hint: str | None = None, fresh: bool = False) -> Connection:
    """Bridge if configured and reachable, else RCON. Cached for a minute."""
    if not fresh and _CACHE["conn"] is not None and _CACHE["method"] == method and time.time() - _CACHE["time"] < 60:
        return _CACHE["conn"]
    s = load_settings()
    errors = []
    conn: Connection | None = None
    if method in ("auto", "bridge"):
        if s.bridge_token:
            client = BridgeClient(s.bridge_url, s.bridge_token)
            try:
                client.status()
                conn = BridgeConnection(client)
            except BridgeError as e:
                client.close()
                errors.append(str(e))
        else:
            errors.append("bridge: no bridge_token configured")
    if conn is None and method in ("auto", "rcon"):
        if s.rcon_password:
            client = RconClient(s.rcon_host, s.rcon_port, s.rcon_password)
            try:
                client.connect()
                hint = s.mc_version if s.mc_version not in ("", "auto") else version_hint
                conn = RconConnection(client, hint)
            except RconError as e:
                errors.append(str(e))
        else:
            errors.append("rcon: no rcon_password configured")
    if conn is None:
        raise NotConnected("No server connection. " + " | ".join(errors) + "\n" + SETUP_HINT)
    old = _CACHE["conn"]
    if old is not None and old is not conn:
        try:
            old.close()
        except Exception:  # noqa: BLE001
            pass
    _CACHE.update(conn=conn, method=method, time=time.time())
    return conn


def forget() -> None:
    if _CACHE["conn"] is not None:
        try:
            _CACHE["conn"].close()
        except Exception:  # noqa: BLE001
            pass
    _CACHE.update(conn=None, method=None, time=0.0)
