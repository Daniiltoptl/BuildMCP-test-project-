"""Placing a project in a real world: where it goes, what gets sent, what was placed last time.

World position = scene position + offset. The offset is chosen once (at the player, at given
coordinates, or scene coordinates as-is) and remembered per server, so later pastes of the same
project land in the same place and can clear blocks that were removed from the build.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import nbtlib
import numpy as np

from ..blocks.registry import BlockError, format_state, get_registry, parse_state
from ..io.nbtutil import compound
from ..io.structure_data import default_anchor, from_scene
from .bundle import BIOME_KEEP, SKIP, Bundle

BASE_TAG = "buildmcp"
DEFAULT_BIOME = "minecraft:plains"


def translate_state(state: str, reg) -> str | None:
    """Canonical form of ``state`` for another game version (renamed blocks, dropped properties)."""
    try:
        return reg.canonical(state.split("{", 1)[0])
    except BlockError:
        pass
    try:
        name, props, _ = parse_state(state)
        info = reg.info(name)
    except (BlockError, KeyError):
        return None
    full = info.default_props()
    for k, v in props.items():
        if k in full and v in info.values(k):
            full[k] = v
    return format_state(info.name, full, info.prop_names)


def entity_tag_for(slug: str) -> str:
    return f"{BASE_TAG}.{re.sub(r'[^A-Za-z0-9_.+-]', '_', slug)}"[:64]


@dataclass
class Snapshot:
    """What a paste put into the world (cells index ``palette``; 0 = nothing placed there)."""

    world: str | None
    min: tuple[int, int, int]
    cells: np.ndarray  # (w, h, l) uint16
    palette: list[str]

    @property
    def max(self) -> tuple[int, int, int]:
        return tuple(int(self.min[i] + self.cells.shape[i] - 1) for i in range(3))  # type: ignore[return-value]

    def save(self, path: Path) -> None:
        np.savez_compressed(path, cells=self.cells, min=np.array(self.min),
                            meta=np.array(json.dumps({"world": self.world, "palette": self.palette})))

    @classmethod
    def load(cls, path: Path) -> "Snapshot | None":
        if not path.exists():
            return None
        with np.load(path) as z:
            meta = json.loads(str(z["meta"]))
            return cls(meta["world"], tuple(int(v) for v in z["min"]), z["cells"].astype(np.uint16), meta["palette"])


def build_bundle(scene, offset, version: str, *, world: str | None = None, label: str = "",
                 entity_tag: str | None = None, backup: bool = True, region=None,
                 previous: Snapshot | None = None, biomes: str | bool = "auto") -> tuple[Bundle, Snapshot, dict]:
    """Bundle for pasting ``scene`` (or ``region`` of it) at ``offset`` on a server running ``version``.

    previous: the last paste of this project on this server; cells it filled that are now air get
    cleared (so deleted parts of the build disappear from the world too).
    """
    reg = get_registry(version)
    ox, oy, oz = (int(v) for v in offset)
    sd = from_scene(scene, region, data_version=reg.data_version)
    warnings: list[str] = []

    # palette -> server states
    bpal = [SKIP]
    index: dict[str, int] = {}
    lut = np.zeros(len(sd.palette), dtype=np.uint16)
    renamed = []
    for i, s in enumerate(sd.palette):
        if i == 0 or s == "minecraft:air":
            continue
        t = translate_state(s, reg)
        if t is None:
            warnings.append(f"{s} does not exist in Minecraft {reg.version}: skipped")
            continue
        if parse_state(t)[0] != parse_state(s)[0]:
            renamed.append(f"{parse_state(s)[0]} -> {parse_state(t)[0]}")
        if t not in index:
            index[t] = len(bpal)
            bpal.append(t)
        lut[i] = index[t]
    if renamed:
        warnings.append("renamed for this version: " + ", ".join(sorted(set(renamed))))
    new_cells = lut[sd.data]
    new_min = (sd.min[0] + ox, sd.min[1] + oy, sd.min[2] + oz)
    size = new_cells.shape

    # union with the previous paste so removed blocks get cleared
    lo, hi = np.array(new_min), np.array(new_min) + np.array(size) - 1
    prev = previous if previous is not None and previous.world == world else None
    if prev is not None:
        lo = np.minimum(lo, prev.min)
        hi = np.maximum(hi, prev.max)
    usize = tuple(int(v) for v in hi - lo + 1)
    cells = np.zeros(usize, dtype=np.uint16)
    d = np.array(new_min) - lo
    cells[d[0]:d[0] + size[0], d[1]:d[1] + size[1], d[2]:d[2] + size[2]] = new_cells
    cleared = 0
    if prev is not None:
        pd = np.array(prev.min) - lo
        was = np.zeros(usize, dtype=bool)
        ps = prev.cells.shape
        was[pd[0]:pd[0] + ps[0], pd[1]:pd[1] + ps[1], pd[2]:pd[2] + ps[2]] = prev.cells != 0
        clear = was & (cells == 0)
        cleared = int(clear.sum())
        if cleared:
            air = "minecraft:air"
            if air not in index:
                index[air] = len(bpal)
                bpal.append(air)
            cells[clear] = index[air]

    tiles = []
    for (x, y, z), (_bid, nbt) in sorted(sd.block_entities.items()):
        c = nbtlib.Compound(compound(nbt))
        for k in ("x", "y", "z", "id"):
            c.pop(k, None)
        if not c or not cells[x + d[0], y + d[1], z + d[2]]:
            continue
        tiles.append((int(x + d[0]), int(y + d[1]), int(z + d[2]), nbtlib.serialize_tag(c)))

    ents = []
    for eid, (x, y, z), nbt in sd.entities:
        c = nbtlib.Compound(compound(nbt))
        for k in ("id", "Pos", "UUID"):
            c.pop(k, None)
        tags = [str(t) for t in c.get("Tags", [])]
        for t in (BASE_TAG, entity_tag):
            if t and t not in tags:
                tags.append(t)
        c["Tags"] = nbtlib.List[nbtlib.String]([nbtlib.String(t) for t in tags])
        if "Rotation" not in c:
            c["Rotation"] = nbtlib.List[nbtlib.Float]([nbtlib.Float(0), nbtlib.Float(0)])
        ents.append((float(x + d[0]), float(y + d[1]), float(z + d[2]), eid, nbtlib.serialize_tag(c)))

    bio_pal = bio = None
    if biomes and sd.biomes is not None and sd.biome_palette:
        used = sorted(set(np.unique(sd.biomes).tolist()))
        names = [sd.biome_palette[i] for i in used]
        if biomes is True or any(n != DEFAULT_BIOME for n in names):
            bio_pal = names
            remap = np.full(max(used) + 1, BIOME_KEEP, dtype=np.uint8)
            remap[used] = np.arange(len(used), dtype=np.uint8)
            bio = np.full((usize[0], usize[2]), BIOME_KEEP, dtype=np.uint8)
            bio[d[0]:d[0] + size[0], d[2]:d[2] + size[2]] = remap[sd.biomes]

    header = {"world": world, "label": label or "BuildMCP", "backup": bool(backup), "compare": True,
              "data_version": reg.data_version, "source": "BuildMCP"}
    if entity_tag:
        header["entity_tag"] = entity_tag
    bundle = Bundle(palette=bpal, cells=cells, min=tuple(int(v) for v in lo), tiles=tiles, entities=ents,
                    biome_palette=bio_pal, biomes=bio, header=header)
    snap = Snapshot(world, new_min, np.where(new_cells != 0, new_cells, 0).astype(np.uint16), list(bpal))
    info = {"world_min": [int(v) for v in lo], "world_max": [int(v) for v in hi], "size": list(usize),
            "blocks": int((new_cells != 0).sum()), "cleared": cleared, "block_entities": len(tiles),
            "entities": len(ents), "biomes": bio_pal or [], "warnings": warnings}
    return bundle, snap, info


# ------------------------------------------------------------------ records
def _deploy_dir(project) -> Path:
    d = Path(project.root) / "deploy"
    d.mkdir(exist_ok=True)
    return d


def server_key(desc: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", desc).strip("_")[:80] or "server"


def load_record(project, key: str) -> dict | None:
    p = _deploy_dir(project) / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_snapshot(project, key: str) -> Snapshot | None:
    return Snapshot.load(_deploy_dir(project) / f"{key}.npz")


def save_record(project, key: str, record: dict, snapshot: Snapshot | None) -> None:
    record = dict(record, time=time.time())
    (_deploy_dir(project) / f"{key}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), "utf-8")
    if snapshot is not None:
        snapshot.save(_deploy_dir(project) / f"{key}.npz")


def scene_anchor(scene) -> tuple[int, int, int]:
    b = scene.bbox()
    if b is None:
        raise ValueError("the scene is empty")
    return default_anchor(scene, b)


def to_world(pos, offset) -> tuple[float, float, float]:
    return tuple(float(pos[i]) + offset[i] for i in range(3))  # type: ignore[return-value]


def to_scene(pos, offset) -> tuple[float, float, float]:
    return tuple(float(pos[i]) - offset[i] for i in range(3))  # type: ignore[return-value]
