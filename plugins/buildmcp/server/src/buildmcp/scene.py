"""The Scene: a growable voxel world with block states, block entities, entities, biomes
and markers. All coordinates are world coordinates (x east, y up, z south).
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import nbtlib
import numpy as np

from .blocks import families as F
from .blocks.pattern import compile_pattern
from .blocks.registry import BlockRegistry, get_registry, parse_state
from .blocks.transforms import mirror_state, mirror_yaw, rotate_state, rotate_xz, rotate_yaw
from .geo.box import Box
from .geo.mask import Mask, as_mask
from .paint.palette import Blocklike, resolve_ids

AIR = "minecraft:air"
CHUNK = 16
DEFAULT_MAX = (1024, 384, 1024)


@dataclass
class Entity:
    """A non-block object: display entities, armor stands, item frames, paintings..."""

    id: str
    pos: tuple[float, float, float]
    nbt: dict = field(default_factory=dict)  # SNBT-compatible python structure or nbtlib Compound

    def to_json(self) -> dict:
        return {"id": self.id, "pos": list(self.pos), "snbt": _to_snbt(self.nbt)}


@dataclass
class Marker:
    """Named point of interest: spawn point, NPC spot, portal, hologram, viewpoint, region corner."""

    name: str
    pos: tuple[float, float, float]
    kind: str = "point"
    yaw: float = 0.0  # 0 = south, 90 = west, 180 = north, 270 = east
    pitch: float = 0.0
    data: dict = field(default_factory=dict)


def _to_snbt(nbt: Any) -> str:
    if isinstance(nbt, str):
        return nbt
    if isinstance(nbt, nbtlib.tag.Base):
        return nbtlib.serialize_tag(nbt)
    return nbtlib.serialize_tag(_py_to_nbt(nbt))


def _py_to_nbt(v: Any):
    """Best-effort python -> nbtlib conversion (dict->Compound, list->List, int->Int, float->Double, str->String)."""
    if isinstance(v, nbtlib.tag.Base):
        return v
    if isinstance(v, dict):
        return nbtlib.Compound({k: _py_to_nbt(x) for k, x in v.items()})
    if isinstance(v, (list, tuple)):
        items = [_py_to_nbt(x) for x in v]
        if not items:
            return nbtlib.List[nbtlib.String]([])
        return nbtlib.List[type(items[0])](items)
    if isinstance(v, bool):
        return nbtlib.Byte(1 if v else 0)
    if isinstance(v, int):
        return nbtlib.Int(v)
    if isinstance(v, float):
        return nbtlib.Double(v)
    if isinstance(v, str):
        return nbtlib.String(v)
    raise TypeError(f"cannot convert {v!r} to NBT")


def parse_snbt(s: str) -> nbtlib.Compound:
    tag = nbtlib.parse_nbt(s)
    if not isinstance(tag, nbtlib.Compound):
        raise ValueError(f"block entity NBT must be a compound: {s}")
    return tag


class Clip:
    """A copied piece of a scene (blocks + block entities + entities), relative to ``anchor``."""

    def __init__(self, data: np.ndarray, palette: list[str], origin: Sequence[int],
                 block_entities: dict | None = None, entities: list[Entity] | None = None):
        self.data = data
        self.palette = palette
        self.origin = np.asarray(origin, np.int64)  # world position of data[0,0,0] when copied
        self.block_entities = block_entities or {}  # relative (dx,dy,dz) -> nbt
        self.entities = entities or []  # positions relative to origin

    @property
    def size(self) -> tuple[int, int, int]:
        return self.data.shape  # type: ignore[return-value]

    def transformed(self, rotate: int = 0, mirror: str | None = None) -> "Clip":
        """Rotated (quarter turns clockwise) and/or mirrored copy; states are transformed too."""
        data = self.data
        pal = list(self.palette)
        bes = dict(self.block_entities)
        ents = list(self.entities)
        sx, sy, sz = data.shape
        if mirror in ("x", "z"):
            axis = 0 if mirror == "x" else 2
            data = np.flip(data, axis=axis)
            pal = [mirror_state(s, mirror) for s in pal]
            size_a = data.shape[axis]
            bes = {((size_a - 1 - k[0]) if axis == 0 else k[0], k[1], (size_a - 1 - k[2]) if axis == 2 else k[2]): v
                   for k, v in bes.items()}
            new_ents = []
            for e in ents:
                p = list(e.pos)
                p[axis] = size_a - p[axis]
                nbt = dict(e.nbt) if isinstance(e.nbt, dict) else e.nbt
                if isinstance(nbt, dict) and "Rotation" in nbt:
                    yaw, pitch = nbt["Rotation"]
                    nbt["Rotation"] = [mirror_yaw(float(yaw), mirror), float(pitch)]
                new_ents.append(Entity(e.id, tuple(p), nbt))
            ents = new_ents
        turns = rotate % 4
        for _ in range(turns):
            # (x, z) -> (-z, x): new array indexed [sz - 1 - z, y, x]
            sx, sy, sz = data.shape
            data = np.transpose(data, (2, 1, 0))[::-1, :, :]
            pal = [rotate_state(s, 1) for s in pal]
            bes = {(sz - 1 - k[2], k[1], k[0]): v for k, v in bes.items()}
            new_ents = []
            for e in ents:
                x, y, z = e.pos
                nbt = dict(e.nbt) if isinstance(e.nbt, dict) else e.nbt
                if isinstance(nbt, dict) and "Rotation" in nbt:
                    yaw, pitch = nbt["Rotation"]
                    nbt["Rotation"] = [rotate_yaw(float(yaw), 1), float(pitch)]
                new_ents.append(Entity(e.id, (sz - z, y, x), nbt))
            ents = new_ents
        return Clip(np.ascontiguousarray(data), pal, self.origin, bes, ents)


class Scene:
    """Voxel world. Create with ``Scene(version="1.21.4")``."""

    def __init__(self, version: str | None = None, registry: BlockRegistry | None = None,
                 max_size: Sequence[int] = DEFAULT_MAX):
        self.reg = registry or get_registry(version)
        self.palette: list[str] = [AIR]
        self._ids: dict[str, int] = {AIR: 0}
        self.data = np.zeros((0, 0, 0), dtype=np.uint16)
        self.origin = np.zeros(3, dtype=np.int64)
        self.block_entities: dict[tuple[int, int, int], Any] = {}
        self.entities: list[Entity] = []
        self.markers: dict[str, Marker] = {}
        self.biome_palette: list[str] = ["minecraft:plains"]
        self.biomes = np.zeros((0, 0), dtype=np.uint8)
        self.max_size = tuple(int(v) for v in max_size)
        self._lut_cache: dict[str, np.ndarray] = {}
        self.dirty_version = 0

    # ------------------------------------------------------------------ basics
    @property
    def version(self) -> str:
        return self.reg.version

    def id_of(self, state: str) -> int:
        """Palette index of a block state (validated and canonicalized; NBT is ignored)."""
        hit = self._ids.get(state)
        if hit is not None:
            return hit
        canon = self.reg.canonical(state)
        if "{" in canon:
            canon = canon[: canon.index("{")]
        hit = self._ids.get(canon)
        if hit is None:
            if len(self.palette) >= 65535:
                raise RuntimeError("too many distinct block states in one scene (65535)")
            hit = len(self.palette)
            self.palette.append(canon)
            self._ids[canon] = hit
        self._ids[state] = hit
        return hit

    def state_of(self, idx: int) -> str:
        return self.palette[int(idx)]

    @property
    def extent(self) -> Box | None:
        """Allocated area (not necessarily filled)."""
        if self.data.size == 0:
            return None
        return Box(*self.origin, *(self.origin + np.array(self.data.shape) - 1))

    def bbox(self) -> Box | None:
        """Tight box around all non-air blocks."""
        if self.data.size == 0:
            return None
        return Mask(self.origin, self.data != 0).bbox

    # --------------------------------------------------------------- allocation
    def ensure(self, box) -> None:
        """Grow the allocated volume so that ``box`` fits."""
        b = Box.of(box)
        ext = self.extent
        if ext is not None and ext.contains_box(b):
            return
        want = b if ext is None else ext.union(b)
        lo = np.array(want.min)
        hi = np.array(want.max) + 1
        # pad to chunk multiples horizontally, 8 vertically (fewer reallocations)
        lo[[0, 2]] = (lo[[0, 2]] // CHUNK) * CHUNK
        hi[[0, 2]] = -(-hi[[0, 2]] // CHUNK) * CHUNK
        lo[1] = (lo[1] // 8) * 8
        hi[1] = -(-hi[1] // 8) * 8
        size = hi - lo
        if np.any(size > np.array(self.max_size)):
            raise ValueError(
                f"Scene would grow to {tuple(int(s) for s in size)} blocks, over the limit {self.max_size}. "
                "Build big areas as several projects or raise max_size."
            )
        new = np.zeros(tuple(size), dtype=np.uint16)
        new_bio = np.zeros((size[0], size[2]), dtype=np.uint8)
        if ext is not None:
            off = self.origin - lo
            sx, sy, sz = self.data.shape
            new[off[0]:off[0] + sx, off[1]:off[1] + sy, off[2]:off[2] + sz] = self.data
            new_bio[off[0]:off[0] + sx, off[2]:off[2] + sz] = self.biomes
        self.data = new
        self.biomes = new_bio
        self.origin = lo

    def _local(self, xs, ys, zs):
        return xs - self.origin[0], ys - self.origin[1], zs - self.origin[2]

    # -------------------------------------------------------------------- read
    def get_id(self, x: int, y: int, z: int) -> int:
        lx, ly, lz = int(x) - self.origin[0], int(y) - self.origin[1], int(z) - self.origin[2]
        sx, sy, sz = self.data.shape
        if 0 <= lx < sx and 0 <= ly < sy and 0 <= lz < sz:
            return int(self.data[lx, ly, lz])
        return 0

    def get(self, x: int, y: int, z: int) -> str:
        """Full block state at a position (air outside the scene)."""
        return self.palette[self.get_id(x, y, z)]

    def ids(self, box) -> np.ndarray:
        """Copy of the id array for ``box`` (air outside the allocated area)."""
        b = Box.of(box)
        out = np.zeros(b.size, dtype=np.uint16)
        ext = self.extent
        if ext is None:
            return out
        inter = ext.intersect(b)
        if inter is None:
            return out
        s = tuple(slice(inter.min[i] - self.origin[i], inter.max[i] - self.origin[i] + 1) for i in range(3))
        d = tuple(slice(inter.min[i] - b.min[i], inter.max[i] - b.min[i] + 1) for i in range(3))
        out[d] = self.data[s]
        return out

    def ids_at(self, xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> np.ndarray:
        """Ids at arbitrary coordinate arrays (air outside)."""
        lx, ly, lz = self._local(np.asarray(xs), np.asarray(ys), np.asarray(zs))
        sx, sy, sz = self.data.shape
        inside = (lx >= 0) & (lx < sx) & (ly >= 0) & (ly < sy) & (lz >= 0) & (lz < sz)
        out = np.zeros(np.shape(lx), dtype=np.uint16)
        out[inside] = self.data[lx[inside], ly[inside], lz[inside]]
        return out

    # ------------------------------------------------------------ pattern LUTs
    def lut(self, pattern) -> np.ndarray:
        """Boolean lookup table over the palette for a block pattern."""
        key = pattern if isinstance(pattern, str) or pattern is None else "|".join(pattern)
        key = key or "*"
        lut = self._lut_cache.get(key)
        n = len(self.palette)
        if lut is not None and len(lut) == n:
            return lut
        match = compile_pattern(self.reg, pattern)
        start = 0 if lut is None else len(lut)
        ext = np.array([match(s) for s in self.palette[start:]], dtype=bool)
        lut = ext if lut is None else np.concatenate([lut, ext])
        self._lut_cache[key] = lut
        return lut

    def kind_lut(self) -> np.ndarray:
        """Block kind code (see blocks.families) for every palette entry."""
        cached = self._lut_cache.get("__kind__")
        if cached is not None and len(cached) == len(self.palette):
            return cached
        arr = np.array([F.kind_of(self.reg, s) for s in self.palette], dtype=np.int16)
        self._lut_cache["__kind__"] = arr
        return arr

    # ------------------------------------------------------------------- write
    def put(self, where, block: Blocklike, *, only=None, keep: bool = False) -> int:
        """Place ``block`` (state/palette/function) on every cell of ``where``.

        where: Mask, Box, (x1,y1,z1,x2,y2,z2) or a point.
        only:  pattern of blocks allowed to be replaced (e.g. "#air|#plants").
        keep:  shorthand for only="#air" (never overwrite existing blocks).
        Returns the number of cells written.
        """
        m = as_mask(where)
        if not m:
            return 0
        xs, ys, zs = m.coords()
        b = m.bbox
        self.ensure(b)
        lx, ly, lz = self._local(xs, ys, zs)
        if keep and only is None:
            only = "#air"
        if only is not None:
            cur = self.data[lx, ly, lz]
            ok = self.lut(only)[cur]
            xs, ys, zs, lx, ly, lz = xs[ok], ys[ok], zs[ok], lx[ok], ly[ok], lz[ok]
            if len(xs) == 0:
                return 0
        nbt = None
        if isinstance(block, str) and "{" in block:
            _, _, snbt = parse_state(block)
            nbt = parse_snbt(snbt) if snbt else None
        ids = resolve_ids(self, block, xs, ys, zs)
        self.data[lx, ly, lz] = ids
        if self.block_entities:
            self._drop_block_entities(xs, ys, zs)
        if nbt is not None:
            for p in zip(xs.tolist(), ys.tolist(), zs.tolist()):
                self.block_entities[p] = nbtlib.Compound(nbt) if len(xs) > 1 else nbt
        self.dirty_version += 1
        return int(len(xs))

    def _drop_block_entities(self, xs, ys, zs) -> None:
        if len(self.block_entities) < len(xs):
            written = set(zip(xs.tolist(), ys.tolist(), zs.tolist()))
            for p in [p for p in self.block_entities if p in written]:
                del self.block_entities[p]
        else:
            for p in zip(xs.tolist(), ys.tolist(), zs.tolist()):
                self.block_entities.pop(p, None)

    def set(self, x: int, y: int, z: int, block: str) -> None:
        """Set one block (state string, may include block-entity SNBT)."""
        self.put(Box(x, y, z, x, y, z), block)

    def set_many(self, cells: Iterable[tuple[int, int, int, str]]) -> int:
        """Set many single blocks: [(x, y, z, state), ...]."""
        n = 0
        for x, y, z, s in cells:
            self.set(x, y, z, s)
            n += 1
        return n

    def fill(self, box, block: Blocklike, *, hollow: bool = False, walls: bool = False, outline: bool = False,
             only=None, keep: bool = False) -> int:
        """Fill a box. ``hollow``: shell only, inside cleared; ``walls``: 4 side walls only;
        ``outline``: the 12 edges only."""
        b = Box.of(box)
        m = Mask.box(b)
        if hollow or walls or outline:
            sx, sy, sz = b.size
            arr = np.zeros(b.size, bool)
            if hollow:
                arr[:] = True
                if sx > 2 and sy > 2 and sz > 2:
                    arr[1:-1, 1:-1, 1:-1] = False
                    self.put(Mask(np.array(b.min) + 1, np.ones((sx - 2, sy - 2, sz - 2), bool)), AIR, only=only)
            elif walls:
                arr[[0, -1], :, :] = True
                arr[:, :, [0, -1]] = True
            else:
                for ax in range(3):
                    sl = [slice(None)] * 3
                    others = [a for a in range(3) if a != ax]
                    for i in (0, -1):
                        for j in (0, -1):
                            sl2 = list(sl)
                            sl2[others[0]] = i
                            sl2[others[1]] = j
                            arr[tuple(sl2)] = True
            m = Mask(b.min, arr)
        return self.put(m, block, only=only, keep=keep)

    def clear(self, where=None, only=None) -> int:
        """Set cells to air (whole scene if ``where`` is None)."""
        if where is None:
            ext = self.extent
            if ext is None:
                return 0
            n = int((self.data != 0).sum()) if only is None else int(self.lut(only)[self.data].sum())
            if only is None:
                self.data[:] = 0
                self.block_entities.clear()
            else:
                self.data[self.lut(only)[self.data]] = 0
            self.dirty_version += 1
            return n
        return self.put(where, AIR, only=only if only is not None else "#non_air")

    def replace(self, pattern, block: Blocklike, where=None) -> int:
        """Replace blocks matching ``pattern`` with ``block`` (inside ``where`` or everywhere)."""
        m = self.mask(pattern, where)
        return self.put(m, block)

    # -------------------------------------------------------------------- query
    def mask(self, pattern=None, where=None) -> Mask:
        """Cells whose block matches ``pattern`` (default: any non-air), optionally inside ``where``."""
        ext = self.extent
        if ext is None:
            return Mask.empty()
        if where is None:
            return Mask(self.origin, self.lut(pattern)[self.data])
        w = as_mask(where)
        wb = w.extent
        if wb is None:
            return Mask.empty()
        ids = self.ids(wb)
        return Mask(wb.min, self.lut(pattern)[ids] & w.to_box(wb))

    def solid(self, where=None) -> Mask:
        """Non-air, non-liquid, non-plant cells (things you can stand on or that block light)."""
        return self.mask("!#air|!#liquid|!#plants|!#carpets|!#replaceable", where)

    def surface(self, where=None, pattern=None, clearance: int = 1) -> Mask:
        """Top surface: cells matching ``pattern`` (default: solid ground) with ``clearance``
        replaceable cells (air, grass, flowers...) above them."""
        base = self.solid(where) if pattern is None else self.mask(pattern, where)
        if not base:
            return base
        ext = base.extent
        above = self.ids(Box(ext.x1, ext.y1 + 1, ext.z1, ext.x2, ext.y2 + clearance, ext.z2))
        free = self.lut("#replaceable")[above]
        sy = base.arr.shape[1]
        ok = np.ones(base.arr.shape, bool)
        for d in range(1, clearance + 1):
            ok &= free[:, d - 1:d - 1 + sy, :]
        return Mask(base.origin, base.arr & ok)

    def count(self, pattern=None, where=None) -> int:
        return self.mask(pattern, where).count

    def heightmap(self, where=None, pattern=None) -> tuple[np.ndarray, int, int]:
        """(top y per (x, z) of matching blocks, x0, z0); -1 where there is none."""
        m = self.solid(where) if pattern is None else self.mask(pattern, where)
        return m.heightmap()

    def top_y(self, x: int, z: int, pattern=None) -> int | None:
        """Highest matching (default: solid) block y in a column, or None."""
        ext = self.extent
        if ext is None:
            return None
        col = self.ids(Box(x, ext.y1, z, x, ext.y2, z))[0, :, 0]
        match = self.lut("!#air|!#liquid|!#plants|!#carpets|!#replaceable" if pattern is None else pattern)
        ys = np.nonzero(match[col])[0]
        if len(ys) == 0:
            return None
        return int(ext.y1 + ys[-1])

    def stats(self, where=None, top: int = 25) -> dict:
        """Block counts (top N), total non-air blocks, bounding box."""
        m = self.mask(None, where)
        if not m:
            return {"blocks": 0, "bbox": None, "top": []}
        b = m.extent
        ids = self.ids(b)[m.arr]
        counts = np.bincount(ids, minlength=len(self.palette))
        order = np.argsort(-counts)
        names: dict[str, int] = {}
        for i in order:
            if counts[i] == 0:
                break
            n = self.palette[i].removeprefix("minecraft:").split("[", 1)[0]
            names[n] = names.get(n, 0) + int(counts[i])
        top_list = sorted(names.items(), key=lambda kv: -kv[1])[:top]
        return {
            "blocks": int(m.count),
            "bbox": m.bbox.as_tuple() if m.bbox else None,
            "size": m.bbox.size if m.bbox else None,
            "distinct_blocks": len(names),
            "distinct_states": int((counts > 0).sum()),
            "top": top_list,
            "block_entities": len(self.block_entities),
            "entities": len(self.entities),
        }

    # ---------------------------------------------------------- block entities
    def set_nbt(self, x: int, y: int, z: int, nbt: Any) -> None:
        """Attach block-entity NBT (SNBT string, dict or nbtlib Compound) to a position."""
        if isinstance(nbt, str):
            nbt = parse_snbt(nbt)
        self.block_entities[(int(x), int(y), int(z))] = nbt

    def nbt(self, x: int, y: int, z: int):
        return self.block_entities.get((int(x), int(y), int(z)))

    # ------------------------------------------------------------------ entities
    def add_entity(self, entity_id: str, pos: Sequence[float], nbt: Any = None) -> Entity:
        """Add an entity (e.g. 'text_display') at a world position."""
        eid = entity_id if ":" in entity_id else "minecraft:" + entity_id
        if isinstance(nbt, str):
            nbt = parse_snbt(nbt)
        e = Entity(eid, (float(pos[0]), float(pos[1]), float(pos[2])), nbt or {})
        self.entities.append(e)
        self.dirty_version += 1
        return e

    def remove_entities(self, where=None, entity_id: str | None = None) -> int:
        before = len(self.entities)
        m = None if where is None else as_mask(where)

        def keep(e: Entity) -> bool:
            if entity_id and e.id.removeprefix("minecraft:") != entity_id.removeprefix("minecraft:"):
                return True
            if m is None:
                return False
            return not m.contains([int(np.floor(c)) for c in e.pos])

        self.entities = [e for e in self.entities if keep(e)]
        return before - len(self.entities)

    # ------------------------------------------------------------------ markers
    def mark(self, name: str, pos: Sequence[float], kind: str = "point", yaw: float = 0.0, pitch: float = 0.0,
             **data) -> Marker:
        """Name a point: kind in spawn|npc|portal|hologram|viewpoint|warp|point|region."""
        mk = Marker(name, (float(pos[0]), float(pos[1]), float(pos[2])), kind, float(yaw), float(pitch), dict(data))
        self.markers[name] = mk
        return mk

    # ------------------------------------------------------------------- biomes
    def set_biome(self, where, biome: str) -> None:
        """Set the biome of the columns covered by ``where`` (affects grass/leaf/water colors in game)."""
        b = biome if ":" in biome else "minecraft:" + biome
        if b not in self.biome_palette:
            self.biome_palette.append(b)
        idx = self.biome_palette.index(b)
        m = as_mask(where)
        if not m:
            return
        self.ensure(m.bbox)
        xs, _, zs = m.coords()
        self.biomes[xs - self.origin[0], zs - self.origin[2]] = idx

    def biome_at(self, x: int, z: int) -> str:
        lx, lz = int(x) - self.origin[0], int(z) - self.origin[2]
        if 0 <= lx < self.biomes.shape[0] and 0 <= lz < self.biomes.shape[1]:
            return self.biome_palette[int(self.biomes[lx, lz])]
        return self.biome_palette[0]

    # -------------------------------------------------------------- copy/paste
    def copy(self, where=None) -> Clip:
        """Copy blocks (and block entities/entities) inside ``where`` (default: everything)."""
        if where is None:
            b = self.bbox()
            if b is None:
                return Clip(np.zeros((0, 0, 0), np.uint16), [AIR], (0, 0, 0))
            m = Mask.box(b)
        else:
            m = as_mask(where)
        b = m.bbox
        ids = self.ids(b)
        ids[~m.to_box(b)] = 0
        used = np.unique(ids)
        remap = np.zeros(len(self.palette), dtype=np.uint16)
        remap[used] = np.arange(len(used), dtype=np.uint16)
        pal = [self.palette[i] for i in used]
        if pal[0] != AIR:
            pal = [AIR] + pal
            remap[used] += 1
        data = remap[ids]
        bes = {(p[0] - b.x1, p[1] - b.y1, p[2] - b.z1): v for p, v in self.block_entities.items() if m.contains(p)}
        ents = [Entity(e.id, (e.pos[0] - b.x1, e.pos[1] - b.y1, e.pos[2] - b.z1), e.nbt) for e in self.entities
                if m.contains([int(np.floor(c)) for c in e.pos])]
        return Clip(data, pal, b.min, bes, ents)

    def paste(self, clip: Clip, at: Sequence[int] | None = None, *, rotate: int = 0, mirror: str | None = None,
              air: bool = False, only=None, entities: bool = True) -> Box | None:
        """Paste a clip with its min corner at ``at`` (default: where it was copied from).
        ``air=True`` also pastes air (clears); ``rotate`` quarter turns clockwise; ``mirror`` 'x'/'z'."""
        if clip.data.size == 0:
            return None
        c = clip.transformed(rotate, mirror) if (rotate % 4 or mirror) else clip
        at = np.asarray(c.origin if at is None else at, np.int64)
        sx, sy, sz = c.data.shape
        box = Box(*at, *(at + np.array([sx, sy, sz]) - 1))
        self.ensure(box)
        lut = np.array([self.id_of(s) for s in c.palette], dtype=np.uint16)
        src = c.data
        ids = lut[src]
        write = np.ones(src.shape, bool) if air else (src != 0)
        if only is not None:
            cur = self.ids(box)
            write &= self.lut(only)[cur]
        lo = at - self.origin
        view = self.data[lo[0]:lo[0] + sx, lo[1]:lo[1] + sy, lo[2]:lo[2] + sz]
        view[write] = ids[write]
        if self.block_entities:
            xs, ys, zs = np.nonzero(write)
            self._drop_block_entities(xs + at[0], ys + at[1], zs + at[2])
        for (dx, dy, dz), v in c.block_entities.items():
            self.block_entities[(int(at[0] + dx), int(at[1] + dy), int(at[2] + dz))] = v
        if entities:
            for e in c.entities:
                self.entities.append(Entity(e.id, (at[0] + e.pos[0], at[1] + e.pos[1], at[2] + e.pos[2]), e.nbt))
        self.dirty_version += 1
        return box

    def transform(self, where, rotate: int = 0, mirror: str | None = None, center: Sequence[float] | None = None) -> Box | None:
        """Rotate/mirror a region in place around ``center`` (default: the region's center)."""
        m = as_mask(where)
        b = m.bbox
        if b is None:
            return None
        clip = self.copy(m)
        self.clear(m)
        self.remove_entities(m)
        cx, cy, cz = b.center if center is None else center
        c = clip.transformed(rotate, mirror)
        sx, sy, sz = c.data.shape
        # keep the region centered on (cx, cz)
        at = (int(round(cx - (sx - 1) / 2)), b.y1, int(round(cz - (sz - 1) / 2)))
        return self.paste(c, at)

    def move(self, where, dx: int, dy: int = 0, dz: int = 0) -> Box | None:
        m = as_mask(where)
        if not m:
            return None
        clip = self.copy(m)
        self.clear(m)
        self.remove_entities(m)
        return self.paste(clip, np.array(clip.origin) + np.array([dx, dy, dz]))

    def stack(self, where, dx: int, dy: int = 0, dz: int = 0, count: int = 1, air: bool = False) -> None:
        """Repeat a region ``count`` times with offset (dx, dy, dz) per copy."""
        clip = self.copy(where)
        for i in range(1, count + 1):
            self.paste(clip, np.array(clip.origin) + i * np.array([dx, dy, dz]), air=air)

    # ------------------------------------------------------------ maintenance
    def compact(self) -> None:
        """Shrink storage to the used area and drop unused palette entries."""
        b = self.bbox()
        if b is None:
            self.__init__(registry=self.reg, max_size=self.max_size)  # type: ignore[misc]
            return
        ids = self.ids(b)
        bio = self.biomes[b.x1 - self.origin[0]:b.x2 - self.origin[0] + 1, b.z1 - self.origin[2]:b.z2 - self.origin[2] + 1].copy()
        used = np.unique(ids)
        if used[0] != 0:
            used = np.concatenate([[0], used])
        remap = np.zeros(len(self.palette), dtype=np.uint16)
        remap[used] = np.arange(len(used), dtype=np.uint16)
        self.palette = [self.palette[i] for i in used]
        self._ids = {s: i for i, s in enumerate(self.palette)}
        self.data = remap[ids]
        self.biomes = bio
        self.origin = np.array(b.min, dtype=np.int64)
        self._lut_cache.clear()
        self.dirty_version += 1

    # ----------------------------------------------------------- persistence
    def to_bytes(self) -> bytes:
        """Serialize (compressed) — used for saving and undo snapshots."""
        meta = {
            "version": self.version,
            "palette": self.palette,
            "origin": [int(v) for v in self.origin],
            "biome_palette": self.biome_palette,
            "block_entities": [[list(k), _to_snbt(v)] for k, v in self.block_entities.items()],
            "entities": [e.to_json() for e in self.entities],
            "markers": [asdict(m) for m in self.markers.values()],
        }
        buf = io.BytesIO()
        np.savez_compressed(buf, data=self.data, biomes=self.biomes,
                            meta=np.frombuffer(json.dumps(meta).encode("utf-8"), dtype=np.uint8))
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, blob: bytes) -> "Scene":
        z = np.load(io.BytesIO(blob))
        meta = json.loads(bytes(z["meta"]).decode("utf-8"))
        s = cls(version=meta["version"])
        s.palette = list(meta["palette"])
        s._ids = {st: i for i, st in enumerate(s.palette)}
        s.data = z["data"].astype(np.uint16)
        s.biomes = z["biomes"].astype(np.uint8)
        s.origin = np.array(meta["origin"], dtype=np.int64)
        s.biome_palette = list(meta["biome_palette"])
        s.block_entities = {tuple(k): parse_snbt(v) for k, v in meta["block_entities"]}
        s.entities = [Entity(e["id"], tuple(e["pos"]), parse_snbt(e["snbt"]) if e["snbt"] else {})
                      for e in meta["entities"]]
        s.markers = {m["name"]: Marker(**{**m, "pos": tuple(m["pos"])}) for m in meta["markers"]}
        return s

    def restore(self, blob: bytes) -> None:
        other = Scene.from_bytes(blob)
        version = self.dirty_version  # keep counting up: caches (renders) key on it
        self.__dict__.update({k: v for k, v in other.__dict__.items() if k != "_lut_cache"})
        self._lut_cache = {}
        self.dirty_version = version + 1

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    @classmethod
    def load(cls, path: str | Path) -> "Scene":
        return cls.from_bytes(Path(path).read_bytes())

    def __repr__(self) -> str:
        b = self.bbox()
        return f"Scene({self.version}, bbox={b}, palette={len(self.palette)})"
