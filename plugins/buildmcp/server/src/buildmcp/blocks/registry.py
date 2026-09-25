"""Version-aware block registry: validation and canonical block-state strings.

A *state string* looks like ``minecraft:oak_stairs[facing=east,half=bottom]`` and may
carry block-entity SNBT after the properties: ``oak_sign[rotation=4]{front_text:{...}}``.
The canonical form always has the namespace and every property (defaults filled in),
in the game's alphabetical property order.
"""

from __future__ import annotations

import difflib
import functools
import gzip
import json
import os
import re
from dataclasses import dataclass
from importlib import resources

DEFAULT_VERSION = "1.21.4"
NS = "minecraft:"

# Blocks renamed between versions (old/new -> other name). Resolved in both directions.
RENAMES = {
    "chain": "iron_chain",  # 1.21.9
    "grass": "short_grass",  # 1.20.3
}

_STATE_RE = re.compile(
    r"^\s*(?:(?P<ns>[a-z0-9_.\-]+):)?(?P<name>[a-z0-9_/.\-]+)\s*"
    r"(?:\[(?P<props>[^\]]*)\])?\s*(?P<nbt>\{.*\})?\s*$",
    re.S,
)


class BlockError(ValueError):
    """Invalid block name, property or value."""


@dataclass(frozen=True)
class BlockInfo:
    name: str
    props: tuple[tuple[str, tuple[str, ...]], ...]
    default: tuple[str, ...]
    transparent: bool
    light: int
    filter_light: int
    has_collision: bool
    material: str
    since: str
    collision: int | tuple[int, ...] = 1

    @property
    def prop_names(self) -> tuple[str, ...]:
        return tuple(p for p, _ in self.props)

    def values(self, prop: str) -> tuple[str, ...]:
        for p, vals in self.props:
            if p == prop:
                return vals
        raise KeyError(prop)

    def default_props(self) -> dict[str, str]:
        return {p: d for (p, _), d in zip(self.props, self.default)}


@functools.lru_cache(maxsize=1)
def _index() -> dict:
    with resources.files("buildmcp.data.blocks").joinpath("index.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def supported_versions() -> list[str]:
    return list(_index()["releases"].keys())


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def resolve_version(version: str | None) -> str:
    """Map user input ('1.21.4', '1.21', 'auto', None, '1.21.x') to a supported release."""
    releases = _index()["releases"]
    v = (version or "").strip().lower()
    if v in ("", "auto", "none", "default"):
        v = os.environ.get("BUILDMCP_MC_VERSION", "").strip().lower()
        if v in ("", "auto") or v.startswith("${"):
            return DEFAULT_VERSION
    if v.endswith(".x"):
        prefix = v[:-2]
        cands = [r for r in releases if r == prefix or r.startswith(prefix + ".")]
        if cands:
            return max(cands, key=_vkey)
    if v in releases:
        return v
    try:
        want = _vkey(v)
    except ValueError as e:
        raise BlockError(f"Unknown Minecraft version '{version}'. Supported: {', '.join(releases)}") from e
    older = [r for r in releases if _vkey(r) <= want]
    if not older:
        raise BlockError(f"Minecraft {version} is older than the oldest supported release (1.21).")
    return max(older, key=_vkey)


def data_version(version: str) -> int:
    return int(_index()["releases"][resolve_version(version)]["dataVersion"])


def parse_state(state: str) -> tuple[str, dict[str, str], str | None]:
    """Split a state string into (name without namespace, props, nbt-snbt-or-None)."""
    m = _STATE_RE.match(state)
    if not m:
        raise BlockError(f"Cannot parse block state '{state}'")
    ns = m.group("ns")
    if ns and ns != "minecraft":
        raise BlockError(f"Only vanilla blocks are supported, got namespace '{ns}' in '{state}'")
    props: dict[str, str] = {}
    raw = m.group("props")
    if raw and raw.strip():
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise BlockError(f"Bad property '{part}' in '{state}' (expected key=value)")
            k, v = part.split("=", 1)
            props[k.strip()] = v.strip().lower()
    return m.group("name"), props, m.group("nbt")


def format_state(name: str, props: dict[str, str] | None = None, order: tuple[str, ...] | None = None) -> str:
    props = props or {}
    if not props:
        return NS + name
    keys = order if order is not None else tuple(sorted(props))
    return NS + name + "[" + ",".join(f"{k}={props[k]}" for k in keys if k in props) + "]"


class BlockRegistry:
    """All blocks of one Minecraft version."""

    def __init__(self, version: str | None = None):
        self.version = resolve_version(version)
        rel = _index()["releases"][self.version]
        self.data_version = int(rel["dataVersion"])
        with resources.files("buildmcp.data.blocks").joinpath(f"{rel['blocks']}.json.gz").open("rb") as f:
            raw = json.loads(gzip.decompress(f.read()).decode("utf-8"))
        since = _index()["since"]
        self._shapes: dict[int, tuple[tuple[float, ...], ...]] = {
            int(k): tuple(tuple(float(c) for c in box) for box in v) for k, v in raw["shapes"].items()
        }
        self._blocks: dict[str, BlockInfo] = {}
        for name, b in raw["blocks"].items():
            self._blocks[name] = BlockInfo(
                name=name,
                props=tuple((p, tuple(vals)) for p, vals in b["p"]),
                default=tuple(b["d"]),
                transparent=bool(b["t"]),
                light=int(b["l"]),
                filter_light=int(b["f"]),
                has_collision=bool(b["b"]),
                material=b["m"],
                since=since.get(name, "1.21"),
                collision=tuple(b["c"]) if isinstance(b["c"], list) else int(b["c"]),
            )
        self._names = sorted(self._blocks)
        self._canon_cache: dict[str, str] = {}
        self._sturdy_cache: dict[tuple, bool] = {}

    # ------------------------------------------------------------------ lookup
    def __contains__(self, name: str) -> bool:
        return self._resolve_name(name, raise_error=False) is not None

    def names(self) -> list[str]:
        return list(self._names)

    def _resolve_name(self, name: str, raise_error: bool = True) -> str | None:
        n = name.removeprefix(NS)
        if n in self._blocks:
            return n
        alt = RENAMES.get(n) or next((old for old, new in RENAMES.items() if new == n), None)
        if alt and alt in self._blocks:
            return alt
        if not raise_error:
            return None
        raise BlockError(self._unknown_message(n))

    def _unknown_message(self, n: str) -> str:
        close = difflib.get_close_matches(n, self._names, n=6, cutoff=0.55)
        sub = [x for x in self._names if n in x][:6]
        sugg = list(dict.fromkeys(close + sub))[:8]
        msg = f"Unknown block '{n}' for Minecraft {self.version}."
        since = _index()["since"].get(n)
        if since:
            msg += f" It exists since {since}."
        if sugg:
            msg += " Did you mean: " + ", ".join(sugg) + "?"
        return msg

    def info(self, name: str) -> BlockInfo:
        return self._blocks[self._resolve_name(name)]

    # --------------------------------------------------------------- canonical
    def canonical(self, state: str) -> str:
        """Validate a state string and return its canonical form (block-entity NBT is kept)."""
        hit = self._canon_cache.get(state)
        if hit is not None:
            return hit
        name, props, nbt = parse_state(state)
        info = self.info(name)
        full = info.default_props()
        for k, v in props.items():
            if k not in full:
                allowed = ", ".join(info.prop_names) or "none"
                raise BlockError(f"Block '{info.name}' has no property '{k}' (properties: {allowed})")
            vals = info.values(k)
            if v not in vals:
                raise BlockError(f"Invalid value {k}={v} for '{info.name}' (allowed: {', '.join(vals)})")
            full[k] = v
        out = format_state(info.name, full, info.prop_names)
        if nbt:
            out += nbt
        if len(self._canon_cache) < 200_000:
            self._canon_cache[state] = out
        return out

    def state(self, name: str, **props: object) -> str:
        """Build a canonical state: ``reg.state('oak_stairs', facing='east')``."""
        norm = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in props.items()}
        return self.canonical(format_state(name.removeprefix(NS), norm))

    def props_of(self, state: str) -> tuple[str, dict[str, str]]:
        """(name, full property dict) of a canonical or partial state string."""
        name, props, _ = parse_state(self.canonical(state))
        return name, props

    def with_props(self, state: str, **props: object) -> str:
        """Return ``state`` with some properties changed (keeps NBT)."""
        name, cur, nbt = parse_state(self.canonical(state))
        cur.update({k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in props.items()})
        return self.canonical(format_state(name, cur) + (nbt or ""))

    # --------------------------------------------------------------- geometry
    def state_index(self, state: str) -> int:
        """Index of a state among its block's states (last property varies fastest)."""
        name, props, _ = parse_state(self.canonical(state))
        info = self._blocks[name]
        idx = 0
        for p, vals in info.props:
            idx = idx * len(vals) + vals.index(props[p])
        return idx

    def collision(self, state: str) -> tuple[tuple[float, ...], ...]:
        """Collision boxes [(x1,y1,z1,x2,y2,z2), ...] in block units (0..1, fences reach 1.5)."""
        name, _, _ = parse_state(state)
        info = self.info(name)
        c = info.collision
        sid = c[self.state_index(state)] if isinstance(c, tuple) else c
        return self._shapes.get(sid, ())

    _FACE_SPEC = {
        # face: (normal axis, plane at 0 or 1, in-plane axis u, in-plane axis v)
        "west": (0, 0.0, 1, 2), "east": (0, 1.0, 1, 2),
        "down": (1, 0.0, 0, 2), "up": (1, 1.0, 0, 2),
        "north": (2, 0.0, 0, 1), "south": (2, 1.0, 0, 1),
    }

    def face_covers(self, state: str, face: str, rect: tuple[float, float, float, float] = (0, 0, 16, 16)) -> bool:
        """Does the union of collision boxes touching ``face`` cover ``rect`` (u1, v1, u2, v2 in 0..16)?

        u/v are the two in-plane axes in x, y, z order (e.g. for 'down': u = x, v = z).
        """
        key = (state, face, rect)
        hit = self._sturdy_cache.get(key)
        if hit is not None:
            return hit
        eps = 1e-6
        axis, plane, a, b = self._FACE_SPEC[face]
        u1, v1, u2, v2 = (r / 16.0 for r in rect)
        boxes = []
        for box in self.collision(state):
            lo, hi = box[:3], box[3:]
            touches = lo[axis] <= eps if plane == 0.0 else hi[axis] >= 1 - eps
            if touches:
                boxes.append((lo[a], lo[b], hi[a], hi[b]))
        n = 16
        result = True
        for i in range(n):
            cu = u1 + (u2 - u1) * (i + 0.5) / n
            for j in range(n):
                cv = v1 + (v2 - v1) * (j + 0.5) / n
                if not any(bx[0] - eps <= cu <= bx[2] + eps and bx[1] - eps <= cv <= bx[3] + eps for bx in boxes):
                    result = False
                    break
            if not result:
                break
        self._sturdy_cache[key] = result
        return result

    def face_sturdy(self, state: str, face: str) -> bool:
        """True if the union of collision boxes fully covers a face (north/south/east/west/up/down)."""
        return self.face_covers(state, face, (0, 0, 16, 16))

    def center_support(self, state: str, face: str) -> bool:
        """Can this block hold something hanging from/standing on the center of ``face``?"""
        return self.face_covers(state, face, (7, 7, 9, 9))

    def is_full_cube(self, state: str) -> bool:
        boxes = self.collision(state)
        return len(boxes) == 1 and boxes[0] == (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)

    # ------------------------------------------------------------------ search
    def search(self, query: str, limit: int = 40) -> list[BlockInfo]:
        """Blocks whose name contains every word of ``query`` (fallback: fuzzy match)."""
        words = [w for w in re.split(r"[\s,]+", query.lower().removeprefix(NS)) if w]
        if not words:
            return []
        hits = [n for n in self._names if all(w in n for w in words)]
        if not hits:
            hits = difflib.get_close_matches("_".join(words), self._names, n=limit, cutoff=0.5)
        hits.sort(key=lambda n: (len(n), n))
        return [self._blocks[n] for n in hits[:limit]]


@functools.lru_cache(maxsize=8)
def get_registry(version: str | None = None) -> BlockRegistry:
    return BlockRegistry(resolve_version(version))
