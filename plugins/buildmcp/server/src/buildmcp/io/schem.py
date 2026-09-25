"""Sponge schematic (.schem) v1/v2/v3 — the format WorldEdit and FAWE load with //schem load.

v3 layout (WorldEdit 7.3+, FAWE 2.9+): root "" -> "Schematic" {Version=3, DataVersion, Width,
Height, Length, Offset, Metadata{WorldEdit{Origin}}, Blocks{Palette, Data, BlockEntities},
Biomes{Palette, Data}, Entities}. Block data index = x + z*Width + y*Width*Length (varints).
Region min in the world = Origin + Offset; //paste puts Origin at the player.
"""

from __future__ import annotations

import time
from pathlib import Path

import nbtlib
import numpy as np

from .nbtutil import compound, varint_decode, varint_encode
from .structure_data import StructureData


def _flat_order(arr: np.ndarray) -> np.ndarray:
    """(x, y, z) array -> flat in Sponge order (x fastest, then z, then y)."""
    return np.ascontiguousarray(np.transpose(arr, (1, 2, 0))).ravel()


def _unflat(flat: np.ndarray, w: int, h: int, l: int) -> np.ndarray:
    return np.transpose(flat.reshape(h, l, w), (2, 0, 1))


def _palette_tag(palette: list[str]) -> nbtlib.Compound:
    return nbtlib.Compound({s: nbtlib.Int(i) for i, s in enumerate(palette)})


def _pos_list(p) -> nbtlib.List:
    return nbtlib.List[nbtlib.Double]([nbtlib.Double(float(v)) for v in p])


def write_schem(sd: StructureData, path: str | Path, version: int = 3, name: str | None = None,
                author: str = "BuildMCP") -> Path:
    """Write a .schem file. ``sd.origin`` becomes the paste anchor."""
    path = Path(path)
    w, h, l = sd.size
    if max(w, h, l) > 65535:
        raise ValueError("schematic dimension over 65535")
    origin = np.array(sd.origin if sd.origin is not None else sd.min)
    mn = np.array(sd.min)
    offset = mn - origin
    blocks_flat = _flat_order(sd.data)
    if version == 3:
        schem = nbtlib.Compound()
        schem["Version"] = nbtlib.Int(3)
        schem["DataVersion"] = nbtlib.Int(sd.data_version)
        meta = nbtlib.Compound({
            "Date": nbtlib.Long(int(time.time() * 1000)),
            "Name": nbtlib.String(name or path.stem),
            "Author": nbtlib.String(author),
            "WorldEdit": nbtlib.Compound({
                "Origin": nbtlib.IntArray([int(v) for v in origin]),
                "Version": nbtlib.String("BuildMCP"),
            }),
        })
        schem["Metadata"] = meta
        schem["Width"] = nbtlib.Short(_short(w))
        schem["Height"] = nbtlib.Short(_short(h))
        schem["Length"] = nbtlib.Short(_short(l))
        schem["Offset"] = nbtlib.IntArray([int(v) for v in offset])
        bes = []
        for (x, y, z), (bid, nbt) in sorted(sd.block_entities.items()):
            data = nbtlib.Compound(compound(nbt))
            for k in ("x", "y", "z", "id", "Pos", "Id"):
                data.pop(k, None)
            bes.append(nbtlib.Compound({
                "Id": nbtlib.String(bid),
                "Pos": nbtlib.IntArray([int(x), int(y), int(z)]),
                "Data": data,
            }))
        schem["Blocks"] = nbtlib.Compound({
            "Palette": _palette_tag(sd.palette),
            "Data": nbtlib.ByteArray(np.frombuffer(varint_encode(blocks_flat), dtype=np.int8)),
            "BlockEntities": nbtlib.List[nbtlib.Compound](bes),
        })
        if sd.biomes is not None and sd.biome_palette:
            bio = sd.biomes
            if bio.ndim == 2:
                bio = np.broadcast_to(bio[:, None, :], (w, h, l))
            used = np.unique(bio)
            remap = np.zeros(int(used.max()) + 1, dtype=np.uint32)
            remap[used] = np.arange(len(used), dtype=np.uint32)
            schem["Biomes"] = nbtlib.Compound({
                "Palette": _palette_tag([sd.biome_palette[i] for i in used]),
                "Data": nbtlib.ByteArray(np.frombuffer(varint_encode(_flat_order(remap[bio])), dtype=np.int8)),
            })
        if sd.entities:
            ents = []
            for eid, pos, nbt in sd.entities:
                data = nbtlib.Compound(compound(nbt))
                for k in ("id", "Pos", "UUID"):
                    data.pop(k, None)
                if "Rotation" not in data:
                    data["Rotation"] = nbtlib.List[nbtlib.Float]([nbtlib.Float(0), nbtlib.Float(0)])
                ents.append(nbtlib.Compound({"Id": nbtlib.String(eid), "Pos": _pos_list(pos), "Data": data}))
            schem["Entities"] = nbtlib.List[nbtlib.Compound](ents)
        f = nbtlib.File({"Schematic": schem}, root_name="")
    elif version == 2:
        schem = nbtlib.Compound()
        schem["Version"] = nbtlib.Int(2)
        schem["DataVersion"] = nbtlib.Int(sd.data_version)
        schem["Metadata"] = nbtlib.Compound({
            "WEOffsetX": nbtlib.Int(int(offset[0])), "WEOffsetY": nbtlib.Int(int(offset[1])),
            "WEOffsetZ": nbtlib.Int(int(offset[2])), "Name": nbtlib.String(name or path.stem),
            "Author": nbtlib.String(author),
        })
        schem["Width"] = nbtlib.Short(_short(w))
        schem["Height"] = nbtlib.Short(_short(h))
        schem["Length"] = nbtlib.Short(_short(l))
        schem["Offset"] = nbtlib.IntArray([int(v) for v in mn])
        schem["PaletteMax"] = nbtlib.Int(len(sd.palette))
        schem["Palette"] = _palette_tag(sd.palette)
        schem["BlockData"] = nbtlib.ByteArray(np.frombuffer(varint_encode(blocks_flat), dtype=np.int8))
        bes = []
        for (x, y, z), (bid, nbt) in sorted(sd.block_entities.items()):
            data = nbtlib.Compound(compound(nbt))
            for k in ("x", "y", "z", "id"):
                data.pop(k, None)
            data["Id"] = nbtlib.String(bid)
            data["Pos"] = nbtlib.IntArray([int(x), int(y), int(z)])
            bes.append(data)
        schem["BlockEntities"] = nbtlib.List[nbtlib.Compound](bes)
        if sd.entities:
            ents = []
            for eid, pos, nbt in sd.entities:
                data = nbtlib.Compound(compound(nbt))
                data.pop("UUID", None)
                data["Id"] = nbtlib.String(eid)
                data["Pos"] = _pos_list(np.array(pos) + mn)  # v2: absolute (clipboard space)
                if "Rotation" not in data:
                    data["Rotation"] = nbtlib.List[nbtlib.Float]([nbtlib.Float(0), nbtlib.Float(0)])
                ents.append(data)
            schem["Entities"] = nbtlib.List[nbtlib.Compound](ents)
        if sd.biomes is not None and sd.biome_palette:
            bio = sd.biomes if sd.biomes.ndim == 2 else sd.biomes[:, 0, :]
            used = np.unique(bio)
            remap = np.zeros(int(used.max()) + 1, dtype=np.uint32)
            remap[used] = np.arange(len(used), dtype=np.uint32)
            flat = np.ascontiguousarray(remap[bio].T).ravel()  # index x + z*Width
            schem["BiomePaletteMax"] = nbtlib.Int(len(used))
            schem["BiomePalette"] = _palette_tag([sd.biome_palette[i] for i in used])
            schem["BiomeData"] = nbtlib.ByteArray(np.frombuffer(varint_encode(flat), dtype=np.int8))
        f = nbtlib.File(schem, root_name="Schematic")
    else:
        raise ValueError("schematic version must be 2 or 3")
    path.parent.mkdir(parents=True, exist_ok=True)
    f.save(path, gzipped=True)
    return path


def _short(v: int) -> int:
    return v - 65536 if v > 32767 else v


def _u16(v) -> int:
    return int(v) & 0xFFFF


def _palette_list(tag: nbtlib.Compound) -> list[str]:
    inv = {int(v): str(k) for k, v in tag.items()}
    n = max(inv) + 1 if inv else 0
    return [inv.get(i, "minecraft:air") for i in range(n)]


def read_schem(path: str | Path) -> StructureData:
    """Read Sponge v1/v2/v3 (.schem). Positions are returned in the stored world frame."""
    f = nbtlib.load(str(path))
    root = f
    if "Schematic" in root and isinstance(root["Schematic"], nbtlib.Compound):
        root = root["Schematic"]
    version = int(root.get("Version", 1))
    w, h, l = _u16(root["Width"]), _u16(root["Height"]), _u16(root["Length"])
    dv = int(root.get("DataVersion", 0))
    offset = np.array([int(v) for v in root.get("Offset", [0, 0, 0])])
    warnings: list[str] = []
    if version >= 3:
        meta = root.get("Metadata", nbtlib.Compound())
        we = meta.get("WorldEdit", nbtlib.Compound()) if isinstance(meta, nbtlib.Compound) else nbtlib.Compound()
        origin = np.array([int(v) for v in we.get("Origin", [0, 0, 0])])
        mn = origin + offset
        blocks = root.get("Blocks")
        palette = _palette_list(blocks["Palette"]) if blocks is not None else ["minecraft:air"]
        raw = bytes(np.asarray(blocks["Data"], dtype=np.int8).view(np.uint8)) if blocks is not None else b""
        be_list = blocks.get("BlockEntities", []) if blocks is not None else []
        nested = True
        ent_list = root.get("Entities", [])
        ents_relative = True
    else:
        meta = root.get("Metadata", nbtlib.Compound())
        mn = offset
        if isinstance(meta, nbtlib.Compound) and "WEOffsetX" in meta:
            we_off = np.array([int(meta["WEOffsetX"]), int(meta["WEOffsetY"]), int(meta["WEOffsetZ"])])
            origin = mn - we_off
        else:
            origin = mn
        palette = _palette_list(root["Palette"])
        raw = bytes(np.asarray(root["BlockData"], dtype=np.int8).view(np.uint8))
        be_list = root.get("BlockEntities", root.get("TileEntities", []))
        nested = False
        ent_list = root.get("Entities", [])
        ents_relative = False
    flat = varint_decode(raw)
    if flat.size != w * h * l:
        raise ValueError(f"block data has {flat.size} entries, expected {w * h * l}")
    data = _unflat(flat, w, h, l)
    bes = {}
    for be in be_list:
        pos = tuple(int(v) for v in be["Pos"])
        bid = str(be.get("Id", be.get("id", "")))
        if nested:
            nbt = be.get("Data", nbtlib.Compound())
        else:
            nbt = nbtlib.Compound({k: v for k, v in be.items() if k not in ("Pos", "Id", "id")})
        bes[pos] = (bid, nbtlib.Compound(nbt))
    ents = []
    for e in ent_list:
        eid = str(e.get("Id", e.get("id", "")))
        pos = np.array([float(v) for v in e["Pos"]])
        if not ents_relative:
            pos = pos - mn
        nbt = e.get("Data", nbtlib.Compound()) if nested else nbtlib.Compound(
            {k: v for k, v in e.items() if k not in ("Pos", "Id", "id")})
        ents.append((eid, tuple(float(v) for v in pos), nbtlib.Compound(nbt)))
    bio_pal = None
    bio = None
    if version >= 3 and "Biomes" in root:
        bio_pal = _palette_list(root["Biomes"]["Palette"])
        bflat = varint_decode(bytes(np.asarray(root["Biomes"]["Data"], dtype=np.int8).view(np.uint8)))
        if bflat.size == w * h * l:
            bio = _unflat(bflat, w, h, l)[:, 0, :].astype(np.uint8)
    elif "BiomePalette" in root:
        bio_pal = _palette_list(root["BiomePalette"])
        bflat = varint_decode(bytes(np.asarray(root["BiomeData"], dtype=np.int8).view(np.uint8)))
        if bflat.size == w * l:
            bio = bflat.reshape(l, w).T.astype(np.uint8)
    return StructureData(
        palette=palette, data=data.astype(np.uint32), min=tuple(int(v) for v in mn),
        origin=tuple(int(v) for v in origin), block_entities=bes, entities=ents, biome_palette=bio_pal,
        biomes=bio, data_version=dv, warnings=warnings,
    )
