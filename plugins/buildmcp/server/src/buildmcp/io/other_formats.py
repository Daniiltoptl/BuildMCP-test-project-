"""Vanilla structure files (.nbt) and Litematica (.litematic) — mostly for importing asset packs."""

from __future__ import annotations

from pathlib import Path

import nbtlib
import numpy as np

from ..blocks.registry import format_state, parse_state
from .nbtutil import block_entity_id, compound
from .structure_data import StructureData


def _state_to_compound(state: str) -> nbtlib.Compound:
    name, props, _ = parse_state(state)
    c = nbtlib.Compound({"Name": nbtlib.String("minecraft:" + name)})
    if props:
        c["Properties"] = nbtlib.Compound({k: nbtlib.String(v) for k, v in props.items()})
    return c


def _compound_to_state(c) -> str:
    name = str(c["Name"]).removeprefix("minecraft:")
    props = {str(k): str(v) for k, v in c.get("Properties", {}).items()}
    return format_state(name, props)


# ------------------------------------------------------------ vanilla structure
def read_structure(path: str | Path) -> StructureData:
    f = nbtlib.load(str(path))
    size = [int(v) for v in f["size"]]
    pals = f.get("palette")
    if pals is None and "palettes" in f:
        pals = f["palettes"][0]
    palette = ["minecraft:air"] + [_compound_to_state(c) for c in pals]
    data = np.zeros(size, dtype=np.uint32)  # 0 = untouched (air / structure void)
    bes = {}
    for b in f["blocks"]:
        x, y, z = (int(v) for v in b["pos"])
        idx = int(b["state"]) + 1
        data[x, y, z] = idx
        if "nbt" in b:
            nbt = nbtlib.Compound(b["nbt"])
            bid = str(nbt.pop("id", block_entity_id(palette[idx])))
            bes[(x, y, z)] = (bid, nbt)
    # structure_void means "leave the world as is" -> air in our model
    for i, s in enumerate(palette):
        if s.startswith("minecraft:structure_void"):
            data[data == i] = 0
    ents = []
    for e in f.get("entities", []):
        nbt = nbtlib.Compound(e["nbt"])
        eid = str(nbt.pop("id", "minecraft:marker"))
        ents.append((eid, tuple(float(v) for v in e["pos"]), nbt))
    return StructureData(palette=palette, data=data, min=(0, 0, 0), origin=(0, 0, 0), block_entities=bes,
                         entities=ents, data_version=int(f.get("DataVersion", 0)))


def write_structure(sd: StructureData, path: str | Path) -> Path:
    """Vanilla structure (for /place template or structure blocks). Air is written explicitly."""
    path = Path(path)
    blocks = []
    xs, ys, zs = np.nonzero(np.ones(sd.data.shape, bool))
    for x, y, z in zip(xs.tolist(), ys.tolist(), zs.tolist()):
        entry = nbtlib.Compound({
            "pos": nbtlib.List[nbtlib.Int]([nbtlib.Int(x), nbtlib.Int(y), nbtlib.Int(z)]),
            "state": nbtlib.Int(int(sd.data[x, y, z])),
        })
        be = sd.block_entities.get((x, y, z))
        if be is not None:
            nbt = nbtlib.Compound(compound(be[1]))
            nbt["id"] = nbtlib.String(be[0])
            entry["nbt"] = nbt
        blocks.append(entry)
    ents = []
    for eid, pos, nbt in sd.entities:
        n = nbtlib.Compound(compound(nbt))
        n["id"] = nbtlib.String(eid)
        ents.append(nbtlib.Compound({
            "pos": nbtlib.List[nbtlib.Double]([nbtlib.Double(v) for v in pos]),
            "blockPos": nbtlib.List[nbtlib.Int]([nbtlib.Int(int(np.floor(v))) for v in pos]),
            "nbt": n,
        }))
    root = nbtlib.Compound({
        "DataVersion": nbtlib.Int(sd.data_version),
        "size": nbtlib.List[nbtlib.Int]([nbtlib.Int(v) for v in sd.size]),
        "palette": nbtlib.List[nbtlib.Compound]([_state_to_compound(s) for s in sd.palette]),
        "blocks": nbtlib.List[nbtlib.Compound](blocks),
        "entities": nbtlib.List[nbtlib.Compound](ents),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    nbtlib.File(root, root_name="").save(path, gzipped=True)
    return path


# ------------------------------------------------------------------ litematica
def _unpack_litematic(longs: np.ndarray, bits: int, count: int) -> np.ndarray:
    """Litematica bit array: entries may span two longs."""
    words = np.asarray(longs, dtype=np.int64).view(np.uint64)
    idx = np.arange(count, dtype=np.uint64) * np.uint64(bits)
    start_word = (idx >> np.uint64(6)).astype(np.int64)
    start_bit = (idx & np.uint64(63))
    mask = np.uint64((1 << bits) - 1)
    lo = (words[start_word] >> start_bit) & mask
    end_word = ((idx + np.uint64(bits - 1)) >> np.uint64(6)).astype(np.int64)
    spans = end_word != start_word
    if spans.any():
        sb = start_bit[spans]
        hi_part = words[end_word[spans]] << (np.uint64(64) - sb)
        lo[spans] = (lo[spans] | hi_part) & mask
    return lo.astype(np.uint32)


def read_litematic(path: str | Path) -> StructureData:
    """First region of a .litematic (multi-region files: regions are merged into one box)."""
    f = nbtlib.load(str(path))
    regions = f["Regions"]
    parts = []
    for name, r in regions.items():
        pos = np.array([int(r["Position"][k]) for k in ("x", "y", "z")])
        size = np.array([int(r["Size"][k]) for k in ("x", "y", "z")])
        mn = pos + np.where(size < 0, size + 1, 0)
        ab = np.abs(size)
        palette = [_compound_to_state(c) for c in r["BlockStatePalette"]]
        bits = max(2, int(np.ceil(np.log2(max(len(palette), 2)))))
        count = int(ab.prod())
        flat = _unpack_litematic(np.asarray(r["BlockStates"]), bits, count)
        data = np.transpose(flat.reshape(ab[1], ab[2], ab[0]), (2, 0, 1))
        bes = {}
        for te in r.get("TileEntities", []):
            x, y, z = int(te["x"]), int(te["y"]), int(te["z"])
            nbt = nbtlib.Compound({k: v for k, v in te.items() if k not in ("x", "y", "z")})
            bid = str(nbt.pop("id", block_entity_id(palette[int(data[x, y, z])])))
            bes[(x, y, z)] = (bid, nbt)
        ents = []
        for e in r.get("Entities", []):
            nbt = nbtlib.Compound(e)
            eid = str(nbt.pop("id", "minecraft:marker"))
            p = [float(v) for v in nbt.pop("Pos", [0, 0, 0])]
            ents.append((eid, tuple(p), nbt))
        parts.append((mn, palette, data, bes, ents))
    if len(parts) == 1:
        mn, palette, data, bes, ents = parts[0]
        return StructureData(palette=palette, data=data, min=tuple(int(v) for v in mn), origin=None,
                             block_entities=bes, entities=ents, data_version=int(f.get("MinecraftDataVersion", 0)))
    # merge regions
    lo = np.min([p[0] for p in parts], axis=0)
    hi = np.max([p[0] + np.array(p[2].shape) for p in parts], axis=0)
    palette = ["minecraft:air"]
    index = {"minecraft:air": 0}
    data = np.zeros(tuple(hi - lo), dtype=np.uint32)
    bes = {}
    ents = []
    for mn, pal, d, b, e in parts:
        lut = np.array([index.setdefault(s, len(index)) for s in pal], dtype=np.uint32)
        for s in pal:
            if s not in palette:
                palette.append(s)
        o = mn - lo
        sub = data[o[0]:o[0] + d.shape[0], o[1]:o[1] + d.shape[1], o[2]:o[2] + d.shape[2]]
        vals = lut[d]
        sub[vals != 0] = vals[vals != 0]
        for k, v in b.items():
            bes[(k[0] + o[0], k[1] + o[1], k[2] + o[2])] = v
        ents.extend(e)
    palette = sorted(index, key=index.get)
    return StructureData(palette=palette, data=data, min=tuple(int(v) for v in lo), origin=None,
                         block_entities=bes, entities=ents, data_version=int(f.get("MinecraftDataVersion", 0)))


def read_any(path: str | Path) -> StructureData:
    """Pick the reader by extension: .schem/.schematic, .nbt, .litematic."""
    from .schem import read_schem

    ext = Path(path).suffix.lower()
    if ext in (".schem", ".schematic"):
        return read_schem(path)
    if ext == ".nbt":
        return read_structure(path)
    if ext == ".litematic":
        return read_litematic(path)
    raise ValueError(f"Unsupported structure format '{ext}' (use .schem, .nbt or .litematic)")
