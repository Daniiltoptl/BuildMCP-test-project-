"""Server cores: Paper, Folia and Velocity from the PaperMC Fill API (v3), Purpur from its own API.
Every download is checked against the published checksum."""

from __future__ import annotations

import re
from pathlib import Path

from . import net

FILL = "https://fill.papermc.io/v3/projects"
PURPUR = "https://api.purpurmc.org/v2/purpur"
FILL_PROJECTS = ("paper", "folia", "velocity")


def vkey(v: str) -> tuple:
    """Order Minecraft-style versions: 1.21.11 > 1.21.4, 26.1 > 1.21.11, 3.4.0-SNAPSHOT < 3.4.0."""
    parts = re.split(r"[.\-+]", v)
    out = []
    for p in parts:
        out.append((0, int(p)) if p.isdigit() else (-1, p))
    out.append((0, 0))  # a release ends here; a "-SNAPSHOT" suffix sorts below it
    return tuple(out)


def _is_release(software: str, v: str) -> bool:
    if software == "velocity":
        return bool(re.fullmatch(r"\d+(\.\d+)*(-SNAPSHOT)?", v))
    return bool(re.fullmatch(r"\d+(\.\d+)+", v))


def versions(software: str) -> list[str]:
    """Known versions of a core, newest first (releases only for Minecraft cores)."""
    software = software.lower()
    if software in FILL_PROJECTS:
        data = net.get_json(f"{FILL}/{software}")
        vs = [v for group in (data.get("versions") or {}).values() for v in group]
    elif software == "purpur":
        vs = list(net.get_json(PURPUR).get("versions") or [])
    else:
        raise ValueError(f"unknown server software '{software}': paper | purpur | folia | velocity")
    vs = [v for v in vs if _is_release(software, v)]
    return sorted(set(vs), key=vkey, reverse=True)


def pick_version(software: str, version: str = "latest") -> str:
    """'latest', an exact version, or a line like '1.21' (its newest release)."""
    version = (version or "latest").strip().lower()
    all_v = versions(software)
    if not all_v:
        raise ValueError(f"no versions of {software} available")
    if version in ("latest", "newest", ""):
        if software == "velocity":  # prefer a non-snapshot line if there is one
            rel = [v for v in all_v if "snapshot" not in v.lower()]
            return (rel or all_v)[0]
        return all_v[0]
    if version in all_v:
        return version
    line = [v for v in all_v if v.startswith(version + ".") or v.startswith(version + "-")]
    if line:
        return line[0]
    raise ValueError(f"{software} has no version '{version}'. Newest: {', '.join(all_v[:8])}")


def resolve(software: str, version: str = "latest") -> dict:
    """Where to download a core: {software, version, build, name, url, sha256 | md5, channel}."""
    software = software.lower()
    v = pick_version(software, version)
    if software in FILL_PROJECTS:
        b = net.get_json(f"{FILL}/{software}/versions/{v}/builds/latest")
        d = (b.get("downloads") or {}).get("server:default")
        if not d:
            raise ValueError(f"{software} {v}: no server download in the latest build")
        return {"software": software, "version": v, "build": str(b.get("id", "")), "name": d["name"],
                "url": d["url"], "sha256": (d.get("checksums") or {}).get("sha256"),
                "channel": str(b.get("channel", "")).lower()}
    info = net.get_json(f"{PURPUR}/{v}")
    build = str((info.get("builds") or {}).get("latest") or "")
    if not build:
        raise ValueError(f"purpur {v}: no builds")
    meta = net.get_json(f"{PURPUR}/{v}/{build}")
    return {"software": "purpur", "version": v, "build": build, "name": f"purpur-{v}-{build}.jar",
            "url": f"{PURPUR}/{v}/{build}/download", "md5": meta.get("md5"), "channel": "stable"}


def download(software: str, version: str, dest_dir: Path) -> dict:
    """Download the core into dest_dir (checked); returns resolve() plus path/size."""
    r = resolve(software, version)
    dest = Path(dest_dir) / r["name"]
    got = net.download(r["url"], dest, sha256=r.get("sha256"), md5=r.get("md5"))
    r.update(path=got["path"], size=got["size"])
    return r


def java_required(software: str, version: str) -> int:
    """Minimum Java major version for a core."""
    if software == "velocity":
        return 21
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", version or "")
    if not m:
        return 21
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if major >= 26:
        return 25
    if major == 1 and (minor > 20 or (minor == 20 and patch >= 5)):
        return 21
    if major == 1 and minor >= 18:
        return 17
    if major == 1 and minor == 17:
        return 16
    return 8
