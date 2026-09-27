"""What a plugin jar says about itself: plugin.yml (Bukkit/Spigot/Paper), paper-plugin.yml (Paper
plugins) or velocity-plugin.json (Velocity). One jar can carry several (ViaVersion runs on both)."""

from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

_DESCRIPTORS = {"plugin.yml": "bukkit", "paper-plugin.yml": "paper", "velocity-plugin.json": "velocity",
                "bungee.yml": "bungee"}


@dataclass
class PluginInfo:
    name: str
    version: str = ""
    kind: str = "bukkit"            # the descriptor that was read: bukkit | paper | velocity | bungee
    platforms: list[str] = field(default_factory=list)  # every descriptor in the jar
    id: str = ""                    # Velocity plugin id (dependencies use it); the name elsewhere
    main: str = ""
    api_version: str = ""
    depend: list[str] = field(default_factory=list)       # hard dependencies (plugin names / velocity ids)
    softdepend: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)     # FastAsyncWorldEdit provides WorldEdit
    description: str = ""
    authors: list[str] = field(default_factory=list)
    folia_supported: bool = False
    file: str = ""
    java: int = 0                   # Java version the main class was compiled for (0 = unknown)

    @property
    def names(self) -> set[str]:
        """Lower-case names other plugins can depend on to mean this one (with what it provides)."""
        return {n.lower() for n in (self.name, self.id, *self.provides) if n}

    @property
    def own_names(self) -> set[str]:
        """Lower-case names of this plugin itself (FastAsyncWorldEdit is not WorldEdit here)."""
        return {n.lower() for n in (self.name, self.id) if n}

    def to_dict(self) -> dict:
        return asdict(self)


class NotAPlugin(ValueError):
    pass


def _yaml(text: str) -> dict:
    from ruamel.yaml import YAML

    data = YAML(typ="safe", pure=True).load(text)
    return data if isinstance(data, dict) else {}


def _list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None]
    return [str(v)]


def _paper_deps(d: dict) -> tuple[list[str], list[str]]:
    """paper-plugin.yml dependencies: {server: {Name: {required, load}}} (1.20+) or a list (1.19.4)."""
    deps = d.get("dependencies")
    if isinstance(deps, list):
        hard = [str(x["name"]) for x in deps if isinstance(x, dict) and x.get("name") and x.get("required", True)]
        soft = [str(x["name"]) for x in deps if isinstance(x, dict) and x.get("name") and not x.get("required", True)]
        return hard, soft
    server = (deps or {}).get("server") if isinstance(deps, dict) else None
    if not isinstance(server, dict):
        return [], []
    hard = [str(n) for n, o in server.items() if not isinstance(o, dict) or o.get("required", True)]
    soft = [str(n) for n, o in server.items() if isinstance(o, dict) and not o.get("required", True)]
    return hard, soft


def read(path: Path, platform: str = "") -> PluginInfo:
    """Read the descriptor of a plugin jar, the one ``platform`` (paper | folia | velocity) would use.
    Raises NotAPlugin for anything that is not a plugin."""
    path = Path(path)
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise NotAPlugin(f"{path.name}: not a jar ({e})") from e
    with z:
        names = set(z.namelist())
        present = [kind for fname, kind in _DESCRIPTORS.items() if fname in names]
        if not present:
            raise NotAPlugin(f"{path.name}: no plugin.yml, paper-plugin.yml or velocity-plugin.json inside")
        if platform == "velocity" and "velocity" in present:
            which = "velocity"
        elif "paper" in present:
            which = "paper"
        elif "bukkit" in present:
            which = "bukkit"
        else:
            which = present[0]
        fname = next(f for f, k in _DESCRIPTORS.items() if k == which)
        text = z.read(fname).decode("utf-8", errors="replace")
        try:
            if which == "velocity":
                d = json.loads(text)
                if not isinstance(d, dict):
                    raise ValueError("not an object")
            else:
                d = _yaml(text)
        except Exception as e:  # noqa: BLE001 - broken descriptor
            raise NotAPlugin(f"{path.name}: {fname} is broken ({e})") from e
        main = str(d.get("main", ""))
        # the Java it needs: the main class's header (8 bytes), else the newest of a few classes
        own = main.replace(".", "/") + ".class" if main else ""
        probe = [own] if own in names else sorted(n for n in names if n.endswith(".class"))[:40]
        heads = {}
        for n in probe:
            try:
                with z.open(n) as f:
                    heads[n] = f.read(8)
            except (KeyError, zipfile.BadZipFile, OSError, RuntimeError):
                pass
    info = PluginInfo(name="", kind=which, platforms=present, file=path.name, version=str(d.get("version", "")),
                      main=main, description=str(d.get("description", "") or ""),
                      authors=_list(d.get("authors") or d.get("author")))
    info.java = _java_of(heads, info.main)
    if which == "velocity":
        deps = d.get("dependencies") or []
        info.id = str(d.get("id", ""))
        info.name = str(d.get("name") or info.id or path.stem)
        info.depend = [str(x["id"]) for x in deps if isinstance(x, dict) and x.get("id") and not x.get("optional")]
        info.softdepend = [str(x["id"]) for x in deps if isinstance(x, dict) and x.get("id") and x.get("optional")]
        return info
    info.name = info.id = str(d.get("name") or path.stem)
    info.api_version = str(d.get("api-version", "") or "")
    info.provides = _list(d.get("provides"))
    info.folia_supported = bool(d.get("folia-supported", False))
    if which == "paper":
        info.depend, info.softdepend = _paper_deps(d)
    else:
        info.depend, info.softdepend = _list(d.get("depend")), _list(d.get("softdepend"))
    return info


def _java_of(heads: dict[str, bytes], main: str) -> int:
    """Java the plugin needs: its main class's class file version, else the newest of its classes."""
    def ver(h: bytes) -> int:
        return int.from_bytes(h[6:8], "big") - 44 if len(h) >= 8 and h[:4] == b"\xca\xfe\xba\xbe" else 0

    own = heads.get(main.replace(".", "/") + ".class") if main else None
    if own:
        return ver(own)
    return max((ver(h) for h in heads.values()), default=0)


def fits(info: PluginInfo, platform: str) -> str | None:
    """None if the plugin can run on the platform (paper | folia | velocity), else the reason."""
    if platform == "velocity":
        if "velocity" in info.platforms:
            return None
        return f"{info.name} is a {'/'.join(info.platforms)} plugin, not a Velocity one: install it on the backends"
    if not {"bukkit", "paper"} & set(info.platforms):
        if "velocity" in info.platforms:
            return f"{info.name} is a Velocity plugin: install it on the proxy"
        return f"{info.name} is a {'/'.join(info.platforms)} plugin, not for Paper"
    if platform == "folia" and not info.folia_supported:
        return f"{info.name} does not declare folia-supported: true (it would not load on Folia)"
    return None
