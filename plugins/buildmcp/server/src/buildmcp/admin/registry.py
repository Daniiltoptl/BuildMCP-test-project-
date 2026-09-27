"""Named Minecraft servers that BuildMCP manages on this PC (``servers.json`` in the data folder).

A network is several entries: a proxy (Velocity) and backends (lobby, anarchy...) that point to it
with ``network``. One server is *active*: its connection (RCON, bridge) is what the building tools
(server_paste, server_cmd...) use, exactly like the single server of the older settings, which is
adopted as ``default`` the first time.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

PROXIES = ("velocity",)
SOFTWARE = ("paper", "purpur", "folia", "velocity")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass
class ServerEntry:
    name: str
    dir: str
    software: str = "paper"          # paper | purpur | folia | velocity | unknown
    version: str = ""                # Minecraft version (a proxy: its own version)
    build: str = ""
    jar: str = ""                    # file name of the core inside dir
    memory: str = "4G"
    java: str = ""                   # java executable; "" = JAVA_HOME / PATH
    jvm_args: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)  # custom start command; empty = java + flags + jar
    port: int = 25565
    rcon_port: int = 0
    rcon_password: str = ""
    bridge_url: str = ""
    bridge_token: str = ""
    role: str = ""                   # lobby | game | proxy | ... (free text)
    network: str = ""                # name of the proxy this backend sits behind
    restart_on_crash: bool = True
    created: float = 0.0

    @property
    def path(self) -> Path:
        return Path(self.dir).expanduser()

    @property
    def is_proxy(self) -> bool:
        return self.software in PROXIES

    def state_dir(self) -> Path:
        d = self.path / ".buildmcp"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def public(self) -> dict:
        d = asdict(self)
        d["rcon_password"] = "set" if self.rcon_password else ""
        d["bridge_token"] = "set" if self.bridge_token else ""
        return d


class RegistryError(RuntimeError):
    pass


def _file() -> Path:
    from ..render.assets import data_dir

    return data_dir() / "servers.json"


def _read() -> dict:
    try:
        return json.loads(_file().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), "utf-8")
    tmp.replace(f)


def _entry(d: dict) -> ServerEntry:
    known = {f.name for f in fields(ServerEntry)}
    return ServerEntry(**{k: v for k, v in d.items() if k in known})


def load_all() -> dict[str, ServerEntry]:
    data = _read()
    out = {n: _entry(d) for n, d in (data.get("servers") or {}).items()}
    if not out:
        legacy = _legacy_default()
        if legacy is not None:
            out[legacy.name] = legacy
    return out


def active_name() -> str:
    data = _read()
    act = data.get("active") or ""
    servers = load_all()
    if act in servers:
        return act
    return next(iter(servers), "")


def get(name: str = "") -> ServerEntry:
    servers = load_all()
    if not servers:
        raise RegistryError("no servers yet: create one with srv_setup(name, dir) or adopt an existing folder "
                            "with srv_setup(name, dir, adopt=True)")
    key = (name or active_name()).strip().lower()
    if key not in servers:
        raise RegistryError(f"no server '{name}'. Known: {', '.join(servers)}")
    return servers[key]


def put(entry: ServerEntry, make_active: bool = False) -> ServerEntry:
    if not NAME_RE.match(entry.name):
        raise RegistryError(f"bad server name '{entry.name}': use a-z, 0-9, '-' and '_' (up to 32)")
    data = _read()
    servers = data.get("servers") or {}
    if not servers:  # keep an adopted legacy server when the registry is first written
        legacy = _legacy_default()
        if legacy is not None and legacy.name != entry.name and legacy.dir != entry.dir:
            servers[legacy.name] = asdict(legacy)
    if not entry.created:
        entry.created = time.time()
    servers[entry.name] = asdict(entry)
    data["servers"] = servers
    if make_active or not data.get("active"):
        data["active"] = entry.name
    _write(data)
    if data["active"] == entry.name:
        _push_connection(entry)
    return entry


def remove(name: str) -> None:
    data = _read()
    servers = data.get("servers") or {}
    if name not in servers:
        raise RegistryError(f"no server '{name}'")
    del servers[name]
    data["servers"] = servers
    if data.get("active") == name:
        data["active"] = next(iter(servers), "")
    _write(data)


def use(name: str) -> ServerEntry:
    """Make ``name`` the active server: the building tools connect to it from now on."""
    e = get(name)
    data = _read()
    data.setdefault("servers", {})[e.name] = asdict(e)
    data["active"] = e.name
    _write(data)
    _push_connection(e)
    return e


def _push_connection(e: ServerEntry) -> None:
    """Mirror the active server into connection.json (what live.connector reads)."""
    from ..live.connector import forget, save_settings

    values = {"server_dir": str(e.path)}
    if e.rcon_password and e.rcon_port:
        values.update(rcon_host="127.0.0.1", rcon_port=int(e.rcon_port), rcon_password=e.rcon_password)
    if e.bridge_token:
        values.update(bridge_url=e.bridge_url or "http://127.0.0.1:8765", bridge_token=e.bridge_token)
    if e.version and not e.is_proxy:
        values["mc_version"] = e.version
    save_settings(**values)
    forget()


def _legacy_default() -> ServerEntry | None:
    """The single server of the older settings (server_dir + RCON/bridge), as an entry named default."""
    try:
        from ..live.connector import load_settings

        s = load_settings()
    except Exception:  # noqa: BLE001
        return None
    if not s.server_dir or not Path(s.server_dir).expanduser().is_dir():
        return None
    e = detect(Path(s.server_dir).expanduser(), "default")
    if s.rcon_password:
        e.rcon_port, e.rcon_password = int(s.rcon_port), s.rcon_password
    if s.bridge_token:
        e.bridge_url, e.bridge_token = s.bridge_url, s.bridge_token
    return e


# ------------------------------------------------------------------ detection
_JAR_RE = re.compile(r"^(paper|purpur|folia|velocity)-(\d[\w.\-+]*?)(?:-(\d+))?\.jar$", re.I)


def detect(path: Path, name: str) -> ServerEntry:
    """Guess software, version, jar and ports of an existing server folder."""
    from . import props

    path = Path(path).expanduser()
    if not path.is_dir():
        raise RegistryError(f"{path} is not a folder")
    e = ServerEntry(name=name, dir=str(path.resolve()), software="unknown")
    jars = sorted(p.name for p in path.glob("*.jar"))
    for j in jars:
        m = _JAR_RE.match(j)
        if m:
            e.software, e.version, e.build, e.jar = m.group(1).lower(), m.group(2), m.group(3) or "", j
            break
    if not e.jar and jars:
        e.jar = next((j for j in jars if j.lower() in ("server.jar", "paper.jar", "purpur.jar", "velocity.jar")),
                     jars[0])
        low = e.jar.lower()
        e.software = next((s for s in SOFTWARE if s in low), "unknown")
    if (path / "velocity.toml").exists():
        e.software = "velocity"
    if e.software == "unknown" and (path / "server.properties").exists():
        e.software = "paper"  # a Bukkit-family server; the exact fork does not change how it is run
    if not e.version:
        e.version = _version_from_history(path) or ""
    if e.is_proxy:
        e.memory = "1G"
        e.port = _velocity_port(path) or 25577
    else:
        p = props.read(path / "server.properties")
        e.port = int(p.get("server-port", "25565") or 25565)
        if p.get("enable-rcon") == "true" and p.get("rcon.password"):
            e.rcon_port = int(p.get("rcon.port", "25575") or 25575)
            e.rcon_password = p["rcon.password"]
    cfg = path / "plugins" / "BuildBridge" / "config.yml"
    if cfg.exists():
        vals = {}
        for line in cfg.read_text("utf-8", errors="replace").splitlines():
            s = line.split("#", 1)[0].strip()
            for key in ("bind", "port", "token"):
                if s.startswith(key + ":"):
                    vals[key] = s.split(":", 1)[1].strip().strip('"').strip("'")
        if vals.get("token"):
            host = vals.get("bind", "127.0.0.1")
            host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
            e.bridge_url, e.bridge_token = f"http://{host}:{vals.get('port', '8765')}", vals["token"]
    return e


def _version_from_history(path: Path) -> str | None:
    """Paper keeps "currentVersion": "... (MC: 1.21.4)" in version_history.json after the first start."""
    try:
        cur = json.loads((path / "version_history.json").read_text("utf-8")).get("currentVersion", "")
    except (OSError, ValueError):
        return None
    m = re.search(r"MC:\s*([0-9][\w.\-]*)", cur)
    return m.group(1) if m else None


def _velocity_port(path: Path) -> int | None:
    try:
        text = (path / "velocity.toml").read_text("utf-8")
    except OSError:
        return None
    m = re.search(r'^\s*bind\s*=\s*"[^"]*:(\d+)"', text, re.M)
    return int(m.group(1)) if m else None
