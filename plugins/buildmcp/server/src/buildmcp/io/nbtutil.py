"""Small helpers around nbtlib and the game's block-entity ids."""

from __future__ import annotations

from typing import Any

import nbtlib
import numpy as np


def varint_encode(values: np.ndarray) -> bytes:
    """LEB128 varints (as used by Sponge schematics) for non-negative ints < 2^21."""
    v = np.asarray(values, dtype=np.uint32).ravel()
    if v.size and int(v.max()) >= (1 << 21):
        raise ValueError("value too large for 3-byte varint")
    lengths = np.where(v < 0x80, 1, np.where(v < 0x4000, 2, 3)).astype(np.int64)
    out = np.empty(int(lengths.sum()), dtype=np.uint8)
    starts = np.cumsum(lengths) - lengths
    out[starts] = ((v & 0x7F) | np.where(lengths > 1, 0x80, 0)).astype(np.uint8)
    m2 = lengths >= 2
    out[starts[m2] + 1] = (((v[m2] >> 7) & 0x7F) | np.where(lengths[m2] > 2, 0x80, 0)).astype(np.uint8)
    m3 = lengths >= 3
    out[starts[m3] + 2] = ((v[m3] >> 14) & 0x7F).astype(np.uint8)
    return out.tobytes()


def varint_decode(buf: bytes | np.ndarray) -> np.ndarray:
    b = np.frombuffer(bytes(buf), dtype=np.uint8) if not isinstance(buf, np.ndarray) else buf.astype(np.uint8)
    if b.size == 0:
        return np.zeros(0, dtype=np.uint32)
    ends = np.nonzero(b < 0x80)[0]
    starts = np.concatenate([[0], ends[:-1] + 1])
    lengths = ends - starts + 1
    val = (b[starts] & 0x7F).astype(np.uint32)
    for k in range(1, 5):
        m = lengths > k
        if not m.any():
            break
        val[m] |= (b[starts[m] + k] & 0x7F).astype(np.uint32) << np.uint32(7 * k)
    return val


def to_nbt(v: Any):
    """python/nbtlib value -> nbtlib tag (dict -> Compound, list -> List, str -> parsed SNBT if it looks like one)."""
    if isinstance(v, nbtlib.tag.Base):
        return v
    if isinstance(v, dict):
        return nbtlib.Compound({k: to_nbt(x) for k, x in v.items()})
    if isinstance(v, (list, tuple)):
        items = [to_nbt(x) for x in v]
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


def compound(v: Any) -> nbtlib.Compound:
    if v is None:
        return nbtlib.Compound()
    if isinstance(v, str):
        tag = nbtlib.parse_nbt(v)
        return tag if isinstance(tag, nbtlib.Compound) else nbtlib.Compound()
    t = to_nbt(v)
    return t if isinstance(t, nbtlib.Compound) else nbtlib.Compound()


def block_entity_id(block_name: str) -> str:
    """Block-entity type for a block (e.g. oak_wall_sign -> minecraft:sign)."""
    n = block_name.removeprefix("minecraft:").split("[", 1)[0]
    if n.endswith("hanging_sign"):
        return "minecraft:hanging_sign"
    if n.endswith("_sign"):
        return "minecraft:sign"
    if n.endswith("_banner"):
        return "minecraft:banner"
    if n.endswith(("_head", "_skull")):
        return "minecraft:skull"
    if n.endswith("shulker_box"):
        return "minecraft:shulker_box"
    if n.endswith("_bed"):
        return "minecraft:bed"
    if n.endswith("copper_chest"):
        return "minecraft:chest"
    if n.endswith("_shelf"):
        return "minecraft:shelf"
    if n.endswith("copper_golem_statue"):
        return "minecraft:copper_golem_statue"
    special = {
        "spawner": "minecraft:mob_spawner", "campfire": "minecraft:campfire", "soul_campfire": "minecraft:campfire",
        "bee_nest": "minecraft:beehive", "suspicious_sand": "minecraft:brushable_block",
        "suspicious_gravel": "minecraft:brushable_block", "chain_command_block": "minecraft:command_block",
        "repeating_command_block": "minecraft:command_block", "moving_piston": "minecraft:piston",
    }
    return special.get(n, "minecraft:" + n)


# Blocks that always carry a block entity (so paste tools keep their data consistent).
_BE_SUFFIXES = ("_sign", "_banner", "_head", "_skull", "shulker_box", "_bed", "_shelf")
_BE_NAMES = {
    "chest", "trapped_chest", "ender_chest", "barrel", "beacon", "bell", "blast_furnace", "brewing_stand",
    "campfire", "soul_campfire", "chiseled_bookshelf", "command_block", "chain_command_block",
    "repeating_command_block", "comparator", "conduit", "crafter", "creaking_heart", "daylight_detector",
    "decorated_pot", "dispenser", "dropper", "enchanting_table", "end_gateway", "end_portal", "furnace", "hopper",
    "jigsaw", "jukebox", "lectern", "spawner", "sculk_sensor", "calibrated_sculk_sensor", "sculk_shrieker",
    "sculk_catalyst", "smoker", "structure_block", "suspicious_sand", "suspicious_gravel", "trial_spawner", "vault",
    "beehive", "bee_nest",
}


def has_block_entity(block_name: str) -> bool:
    n = block_name.removeprefix("minecraft:").split("[", 1)[0]
    return n in _BE_NAMES or n.endswith(_BE_SUFFIXES) or n.endswith("copper_chest") or n.endswith("copper_golem_statue")
