"""Format-neutral structure data shared by all importers/exporters."""

from __future__ import annotations

from dataclasses import dataclass, field

import nbtlib
import numpy as np

from ..geo.box import Box


@dataclass
class StructureData:
    palette: list[str]  # block state strings (may come from other versions)
    data: np.ndarray  # (x, y, z) indices into palette
    min: tuple[int, int, int] = (0, 0, 0)  # world position of data[0, 0, 0]
    origin: tuple[int, int, int] | None = None  # WorldEdit origin / paste anchor
    block_entities: dict[tuple[int, int, int], tuple[str, nbtlib.Compound]] = field(default_factory=dict)  # rel pos
    entities: list[tuple[str, tuple[float, float, float], nbtlib.Compound]] = field(default_factory=list)  # rel pos
    biome_palette: list[str] | None = None
    biomes: np.ndarray | None = None  # (x, z) or (x, y, z) indices
    data_version: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def size(self) -> tuple[int, int, int]:
        return tuple(int(v) for v in self.data.shape)  # type: ignore[return-value]

    @property
    def box(self) -> Box:
        sx, sy, sz = self.size
        return Box(self.min[0], self.min[1], self.min[2], self.min[0] + sx - 1, self.min[1] + sy - 1, self.min[2] + sz - 1)


def from_scene(scene, where=None, anchor=None) -> StructureData:
    """Collect blocks, block entities, entities and biomes of a scene region."""
    from ..geo.mask import Mask, as_mask
    from .modernize import adapt_block_entity, adapt_entity
    from .nbtutil import block_entity_id

    if where is None:
        b = scene.bbox()
        for e in scene.entities:
            p = Box.of([int(np.floor(c)) for c in e.pos])
            b = p if b is None else b.union(p)
        if b is None:
            raise ValueError("scene is empty")
        m = Mask.box(b)
    else:
        m = as_mask(where)
        b = m.bbox
        if b is None:
            raise ValueError("region is empty")
    ids = scene.ids(b)
    ids[~m.to_box(b)] = 0
    used = np.unique(ids)
    if used[0] != 0:
        used = np.concatenate([[0], used])
    remap = np.zeros(len(scene.palette), dtype=np.uint32)
    remap[used] = np.arange(len(used), dtype=np.uint32)
    palette = [scene.palette[i] for i in used]
    data = remap[ids]
    bes = {}
    for (x, y, z), nbt in scene.block_entities.items():
        if b.contains((x, y, z)) and m.contains((x, y, z)):
            state = scene.get(x, y, z)
            if state == "minecraft:air":
                continue
            bid = block_entity_id(state)
            bes[(x - b.x1, y - b.y1, z - b.z1)] = (bid, adapt_block_entity(bid, _as_compound(nbt), scene.reg.data_version))
    ents = []
    for e in scene.entities:
        p = [int(np.floor(c)) for c in e.pos]
        if b.contains(p):
            ents.append((e.id, (e.pos[0] - b.x1, e.pos[1] - b.y1, e.pos[2] - b.z1),
                         adapt_entity(_as_compound(e.nbt), scene.reg.data_version)))
    # biomes (per column)
    bx0, bz0 = b.x1 - int(scene.origin[0]), b.z1 - int(scene.origin[2])
    bio = scene.biomes[bx0:bx0 + b.size[0], bz0:bz0 + b.size[2]].copy() if scene.biomes.size else None
    if anchor is None:
        anchor = default_anchor(scene, b)
    return StructureData(
        palette=palette, data=data, min=b.min, origin=tuple(int(v) for v in anchor), block_entities=bes,
        entities=ents, biome_palette=list(scene.biome_palette), biomes=bio, data_version=scene.reg.data_version,
    )


def default_anchor(scene, box: Box) -> tuple[int, int, int]:
    """Paste anchor: 'anchor' marker, else 'spawn' marker, else bottom center of the box."""
    for name in ("anchor", "spawn"):
        mk = scene.markers.get(name)
        if mk is not None:
            return tuple(int(np.floor(c)) for c in mk.pos)  # type: ignore[return-value]
    cx, _, cz = box.center
    return (int(np.floor(cx)), box.y1, int(np.floor(cz)))


def _as_compound(nbt) -> nbtlib.Compound:
    from .nbtutil import compound

    return compound(nbt)


def to_scene(sd: StructureData, scene, at=None, rotate: int = 0, mirror: str | None = None, air: bool = False,
             entities: bool = True) -> tuple[Box | None, list[str]]:
    """Paste structure data into a scene. ``at`` = where the min corner goes (default: stored world position)."""
    from ..scene import Clip, Entity
    from ..blocks.registry import BlockError

    warnings = list(sd.warnings)
    pal = []
    for s in sd.palette:
        try:
            pal.append(scene.reg.canonical(s.split("{", 1)[0]))
        except BlockError as e:
            warnings.append(f"{s}: {e} -> air")
            pal.append("minecraft:air")
    bes = {k: v[1] for k, v in sd.block_entities.items()}
    ents = [Entity(eid, pos, nbt) for eid, pos, nbt in sd.entities]
    clip = Clip(sd.data.astype(np.uint16), pal, sd.min, bes, ents)
    box = scene.paste(clip, at if at is not None else sd.min, rotate=rotate, mirror=mirror, air=air, entities=entities)
    if box is not None and sd.biomes is not None and sd.biome_palette:
        bio = sd.biomes if sd.biomes.ndim == 2 else sd.biomes[:, 0, :]
        if mirror == "x":
            bio = bio[::-1, :]
        elif mirror == "z":
            bio = bio[:, ::-1]
        for _ in range(rotate % 4):
            bio = np.transpose(bio)[::-1, :]
        lut = []
        for name in sd.biome_palette:
            if name not in scene.biome_palette:
                scene.biome_palette.append(name)
            lut.append(scene.biome_palette.index(name))
        lut = np.array(lut, dtype=np.uint8)
        x0, z0 = box.x1 - int(scene.origin[0]), box.z1 - int(scene.origin[2])
        scene.biomes[x0:x0 + bio.shape[0], z0:z0 + bio.shape[1]] = lut[bio]
    return box, warnings
