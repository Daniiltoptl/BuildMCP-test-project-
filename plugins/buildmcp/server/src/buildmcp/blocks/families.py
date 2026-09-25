"""Block classification and material families (block -> stairs/slab/wall/fence variants)."""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

from .registry import BlockRegistry

# ----------------------------------------------------------------------------- kinds
AIR = 0
FULL = 1  # full collision cube (stone, planks, glass, leaves...)
STAIRS = 2
SLAB = 3
WALL = 4
FENCE = 5
FENCE_GATE = 6
PANE = 7  # glass panes, iron/copper bars
LEAVES = 8
DOOR = 9
TRAPDOOR = 10
BED = 11
DOUBLE_PLANT = 12
LIQUID = 13
PLANT = 14  # flowers, grass, saplings, crops (no collision, needs soil)
CARPET = 15
TORCH = 16
WALL_TORCH = 17
LANTERN = 18
SIGN = 19
WALL_SIGN = 20
HANGING_SIGN = 21
BANNER = 22
WALL_BANNER = 23
HEAD = 24
WALL_HEAD = 25
BUTTON = 26
PRESSURE_PLATE = 27
SNOW_LAYER = 28
VINE = 29
CHAIN = 30
LOG = 31  # axis-oriented pillars
MUSHROOM_BLOCK = 32
DRIPSTONE = 33
HANGING_PLANT = 34  # weeping/twisting/cave vines, kelp columns
OTHER = 35

KIND_NAMES = {v: k.lower() for k, v in dict(globals()).items() if isinstance(v, int) and k.isupper() and k != "KIND_NAMES"}

GRAVITY_BLOCKS = {
    "sand", "red_sand", "gravel", "suspicious_sand", "suspicious_gravel", "anvil", "chipped_anvil",
    "damaged_anvil", "dragon_egg", "pointed_dripstone", "scaffolding",
} | {f"{c}_concrete_powder" for c in (
    "white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray",
    "cyan", "purple", "blue", "brown", "green", "red", "black")}

# Blocks fences/walls/panes never connect to even though their face is sturdy.
CONNECT_EXCEPTIONS_SUFFIX = ("_leaves", "shulker_box")
CONNECT_EXCEPTIONS = {"barrier", "carved_pumpkin", "jack_o_lantern", "melon", "pumpkin"}

HANGING_PLANT_HEADS = {
    # body block -> head block (the end of the column)
    "weeping_vines_plant": "weeping_vines",
    "twisting_vines_plant": "twisting_vines",
    "cave_vines_plant": "cave_vines",
    "kelp_plant": "kelp",
}
HANGING_PLANT_BODY = {v: k for k, v in HANGING_PLANT_HEADS.items()}
# Direction in which each column grows (towards the head).
HANGING_PLANT_DIR = {"weeping_vines": -1, "cave_vines": -1, "twisting_vines": 1, "kelp": 1}


@functools.lru_cache(maxsize=4096)
def _kind_cached(reg_id: int, name: str) -> int:
    reg = _REGS[reg_id]
    return _classify(reg, name)


_REGS: dict[int, BlockRegistry] = {}


def kind_of(reg: BlockRegistry, name: str) -> int:
    """Classify a block by name (namespace optional)."""
    _REGS[id(reg)] = reg
    return _kind_cached(id(reg), name.removeprefix("minecraft:").split("[", 1)[0])


def _classify(reg: BlockRegistry, n: str) -> int:
    if n in ("air", "cave_air", "void_air"):
        return AIR
    if n in ("water", "lava", "bubble_column"):
        return LIQUID
    info = reg.info(n)
    props = set(info.prop_names)
    if n.endswith("_stairs"):
        return STAIRS
    if n.endswith("_slab"):
        return SLAB
    if n.endswith("_wall") and "up" in props:
        return WALL
    if n.endswith("_fence_gate"):
        return FENCE_GATE
    if n.endswith("_fence"):
        return FENCE
    if n.endswith("_pane") or n.endswith("_bars"):
        return PANE
    if n.endswith("_leaves"):
        return LEAVES
    if n.endswith("_trapdoor"):
        return TRAPDOOR
    if n.endswith("_door"):
        return DOOR
    if n.endswith("_bed"):
        return BED
    if n.endswith("_wall_hanging_sign") or n.endswith("_hanging_sign"):
        return HANGING_SIGN
    if n.endswith("_wall_sign"):
        return WALL_SIGN
    if n.endswith("_sign"):
        return SIGN
    if n.endswith("_wall_banner"):
        return WALL_BANNER
    if n.endswith("_banner"):
        return BANNER
    if n.endswith("_wall_head") or n.endswith("_wall_skull"):
        return WALL_HEAD
    if n.endswith("_head") or n.endswith("_skull"):
        return HEAD
    if n.endswith("wall_torch"):
        return WALL_TORCH
    if n.endswith("torch"):
        return TORCH
    if n.endswith("lantern") and "hanging" in props:
        return LANTERN
    if n.endswith("_button"):
        return BUTTON
    if n.endswith("_pressure_plate"):
        return PRESSURE_PLATE
    if n.endswith("_carpet") or n in ("moss_carpet", "pale_moss_carpet"):
        return CARPET
    if n == "snow":
        return SNOW_LAYER
    if n in ("vine", "glow_lichen", "sculk_vein", "resin_clump"):
        return VINE
    if n.endswith("chain") and "axis" in props:
        return CHAIN
    if n in ("brown_mushroom_block", "red_mushroom_block", "mushroom_stem"):
        return MUSHROOM_BLOCK
    if n == "pointed_dripstone":
        return DRIPSTONE
    if n in HANGING_PLANT_HEADS or n in HANGING_PLANT_BODY:
        return HANGING_PLANT
    if "half" in props and set(info.values("half")) == {"upper", "lower"}:
        return DOUBLE_PLANT
    if "axis" in props and reg.is_full_cube(n):
        return LOG
    if reg.is_full_cube(n):
        return FULL
    if not info.has_collision and info.collision == 0 and _is_plant_name(n):
        return PLANT
    return OTHER


_PLANT_WORDS = (
    "sapling", "flower", "tulip", "orchid", "allium", "bluet", "daisy", "dandelion", "poppy",
    "cornflower", "lily_of_the_valley", "wither_rose", "fern", "short_grass", "dead_bush", "roots",
    "fungus", "mushroom", "sprouts", "torchflower", "pink_petals", "wildflowers", "leaf_litter",
    "bush", "dry_grass", "eyeblossom", "seagrass", "coral", "wheat", "carrots", "potatoes",
    "beetroots", "sweet_berry_bush", "nether_wart", "lily_pad", "hanging_moss", "spore_blossom",
)


def _is_plant_name(n: str) -> bool:
    return any(w in n for w in _PLANT_WORDS)


def connects_as_solid(reg: BlockRegistry, state: str, face: str) -> bool:
    """Would a fence/wall/pane connect to ``state`` through its ``face``?"""
    name = state.removeprefix("minecraft:").split("[", 1)[0]
    if name in CONNECT_EXCEPTIONS or name.endswith(CONNECT_EXCEPTIONS_SUFFIX):
        return False
    return reg.face_sturdy(state, face)


# --------------------------------------------------------------------------- families
@dataclass
class Family:
    """A material and its shaped variants. Any field may be None."""

    base: str
    stairs: str | None = None
    slab: str | None = None
    wall: str | None = None
    fence: str | None = None
    fence_gate: str | None = None
    door: str | None = None
    trapdoor: str | None = None
    button: str | None = None
    pressure_plate: str | None = None
    sign: str | None = None
    hanging_sign: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def get(self, shape: str) -> str | None:
        if shape in ("full", "block", "base"):
            return self.base
        return getattr(self, shape, None) or self.extra.get(shape)


_SHAPE_SUFFIXES = [
    ("fence_gate", "_fence_gate"), ("hanging_sign", "_hanging_sign"), ("pressure_plate", "_pressure_plate"),
    ("stairs", "_stairs"), ("slab", "_slab"), ("wall", "_wall"), ("fence", "_fence"), ("door", "_door"),
    ("trapdoor", "_trapdoor"), ("button", "_button"), ("sign", "_sign"),
]
_MANUAL_BASE = {
    "quartz": "quartz_block", "purpur": "purpur_block", "smooth_quartz": "smooth_quartz",
    "petrified_oak": "oak_planks", "bamboo_mosaic": "bamboo_mosaic", "stone": "stone",
    "nether_brick": "nether_bricks", "red_nether_brick": "red_nether_bricks",
}
# Blocks without their own shaped variants that should borrow another family's.
_BORROW = {
    "cracked_stone_bricks": "stone_bricks", "chiseled_stone_bricks": "stone_bricks",
    "cracked_deepslate_bricks": "deepslate_bricks", "cracked_deepslate_tiles": "deepslate_tiles",
    "chiseled_deepslate": "polished_deepslate", "cracked_nether_bricks": "nether_bricks",
    "chiseled_nether_bricks": "nether_bricks", "cracked_polished_blackstone_bricks": "polished_blackstone_bricks",
    "chiseled_polished_blackstone": "polished_blackstone", "gilded_blackstone": "blackstone",
    "chiseled_sandstone": "sandstone", "cut_sandstone": "sandstone", "chiseled_red_sandstone": "red_sandstone",
    "cut_red_sandstone": "red_sandstone", "chiseled_quartz_block": "quartz_block", "quartz_pillar": "quartz_block",
    "quartz_bricks": "quartz_block", "chiseled_tuff": "tuff", "chiseled_tuff_bricks": "tuff_bricks",
    "chiseled_resin_bricks": "resin_bricks", "packed_mud": "mud_bricks", "smooth_basalt": "polished_blackstone",
    "basalt": "blackstone", "polished_basalt": "polished_blackstone", "infested_stone": "stone",
    "dirt": "mud_bricks", "coarse_dirt": "mud_bricks", "calcite": "diorite", "dripstone_block": "granite",
    "obsidian": "blackstone", "crying_obsidian": "blackstone", "magma_block": "nether_bricks",
    "netherrack": "nether_bricks", "soul_soil": "blackstone", "soul_sand": "blackstone",
    "snow_block": "diorite", "packed_ice": "diorite", "blue_ice": "prismarine", "clay": "diorite",
    "moss_block": "mossy_cobblestone", "grass_block": "mossy_cobblestone", "podzol": "spruce_planks",
    "rooted_dirt": "mud_bricks", "mud": "mud_bricks", "terracotta": "granite", "bone_block": "smooth_quartz",
    "end_stone": "end_stone_bricks", "amethyst_block": "purpur_block", "sea_lantern": "prismarine_bricks",
    "glowstone": "sandstone", "shroomlight": "cut_copper", "gravel": "cobblestone", "sand": "sandstone",
    "red_sand": "red_sandstone",
}
_WOOD_BLOCK_TO_PLANKS = ("_log", "_wood", "_stem", "_hyphae")


@functools.lru_cache(maxsize=8)
def _family_index(version: str) -> dict[str, Family]:
    from .registry import get_registry

    reg = get_registry(version)
    names = set(reg.names())
    fams: dict[str, Family] = {}
    for n in sorted(names):
        for shape, suf in _SHAPE_SUFFIXES:
            if not n.endswith(suf):
                continue
            if shape == "wall" and "up" not in reg.info(n).prop_names:
                continue
            if shape == "sign" and (n.endswith("_wall_sign") or n.endswith("_hanging_sign")):
                continue
            if shape == "hanging_sign" and n.endswith("_wall_hanging_sign"):
                continue
            stem = n[: -len(suf)]
            base = _MANUAL_BASE.get(stem)
            if base is None:
                for cand in (stem, stem + "s", stem + "_planks", stem + "_block"):
                    if cand in names:
                        base = cand
                        break
            if base is None or base not in names:
                continue
            fam = fams.setdefault(base, Family(base=base))
            if getattr(fam, shape) is None:
                setattr(fam, shape, n)
            break
    return fams


def family(reg: BlockRegistry, block: str) -> Family:
    """Family for any member (base or variant) of a material. Falls back to borrowed families
    (e.g. cracked_stone_bricks -> stone brick stairs) and wood logs -> planks."""
    name = block.removeprefix("minecraft:").split("[", 1)[0]
    fams = _family_index(reg.version)
    if name in fams:
        return fams[name]
    for fam in fams.values():
        for shape, _ in _SHAPE_SUFFIXES:
            if getattr(fam, shape) == name:
                return fam
    borrow = _BORROW.get(name)
    if borrow is None:
        for suf in _WOOD_BLOCK_TO_PLANKS:
            if name.endswith(suf):
                wood = name.removeprefix("stripped_")[: -len(suf)]
                if f"{wood}_planks" in fams:
                    borrow = f"{wood}_planks"
                break
    if borrow and borrow in fams:
        src = fams[borrow]
        return Family(base=name, **{s: getattr(src, s) for s, _ in _SHAPE_SUFFIXES})
    return Family(base=name)


def families(reg: BlockRegistry) -> dict[str, Family]:
    return dict(_family_index(reg.version))
