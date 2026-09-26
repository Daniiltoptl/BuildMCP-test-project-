"""Style themes: coordinated block palettes by role + defaults for generators.

    T = themes.get("fantasy_medieval")
    S.put(island.surface, T.grass)
    arch.house(S, box, theme=T)

Roles (all are blocks or palettes): grass, soil, rock, rock_deep, underside, sand, path, plaza,
wall, wall_base, plaster, frame, pillar, floor, window, glass, fence, railing, door, trapdoor,
trunk, leaves, bush, flowers, tall_flowers, ground_cover, lamp, lamp_hanging, light_hidden,
crystal, metal, water, liquid, accent. Material families (for stairs/slabs/walls): trim,
roof, roof_accent, stone_trim, wood_trim.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from ..paint.palette import gradient, mix, patches

THEMES: dict[str, "Theme"] = {}


@dataclass
class Theme:
    name: str
    title: str
    biome: str
    grass: Any
    soil: Any
    rock: Any
    rock_deep: Any
    underside: Any
    sand: Any
    path: Any
    plaza: Any
    wall: Any
    wall_base: Any
    plaster: Any
    frame: str
    pillar: Any
    floor: Any
    window: str
    glass: str
    fence: str
    railing: str
    door: str
    trapdoor: str
    trunk: str
    trunk_log: str
    leaves: Any
    bush: Any
    flowers: list
    tall_flowers: list
    ground_cover: dict
    lamp: str
    lamp_hanging: str
    light_hidden: str
    crystal: Any
    metal: str
    water: str
    liquid: str
    accent: Any
    trim: str  # material family base (stone trims: stairs/slabs/walls)
    wood_trim: str  # wood family base (planks)
    roof: str  # family base for roof stairs/slabs
    roof_accent: str
    trim_dark: str = ""  # contrasting stone/wood family for ribs, bands, frames (hero details)
    tree_kinds: list = field(default_factory=list)
    roof_style: str = "gable"
    lamp_style: str = "post"
    notes: str = ""

    def states(self) -> list[str]:
        """All block states referenced by this theme (for validation)."""
        from ..paint.palette import Palette

        out: list[str] = []
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, Palette):
                out.extend(v.states())
            elif isinstance(v, str) and f.name not in ("name", "title", "biome", "roof_style", "lamp_style", "notes"):
                out.append(v)
            elif isinstance(v, list) and f.name in ("flowers", "tall_flowers"):
                out.extend(v)
            elif isinstance(v, dict):
                out.extend(v.keys())
        return out

    def describe(self) -> str:
        from ..paint.palette import Palette

        lines = [f"{self.title} ({self.name}) — biome {self.biome}"]
        for f in fields(self):
            if f.name in ("name", "title", "notes"):
                continue
            v = getattr(self, f.name)
            if isinstance(v, Palette):
                v = ", ".join(s.removeprefix("minecraft:") for s in v.states())
            lines.append(f"  {f.name}: {v}")
        if self.notes:
            lines.append("  notes: " + self.notes)
        return "\n".join(lines)


def register(t: Theme) -> Theme:
    THEMES[t.name] = t
    return t


def get(name: str) -> Theme:
    key = name.lower().replace("-", "_").replace(" ", "_")
    aliases = {"fantasy": "fantasy_medieval", "medieval": "fantasy_medieval", "asian": "asian_sakura",
               "sakura": "asian_sakura", "japan": "asian_sakura", "dark": "dark_infernal", "hell": "dark_infernal",
               "nether": "dark_infernal", "winter": "winter_north", "north": "winter_north", "snow": "winter_north"}
    key = aliases.get(key, key)
    if key not in THEMES:
        raise KeyError(f"Unknown theme '{name}'. Themes: {', '.join(THEMES)}")
    return THEMES[key]


# ---------------------------------------------------------------- fantasy / medieval
register(Theme(
    name="fantasy_medieval", title="Фэнтези / средневековье", biome="forest",
    grass=patches({"moss_block": 2, "grass_block": 10, "podzol": 0.8, "coarse_dirt": 0.6}, size=7),
    soil=patches({"dirt": 5, "coarse_dirt": 2, "rooted_dirt": 1}, size=3),
    rock=patches({"stone": 5, "andesite": 3, "tuff": 1.5, "cobblestone": 1, "mossy_cobblestone": 0.8}, size=4),
    rock_deep=patches({"tuff": 3, "andesite": 2, "deepslate": 1.5, "stone": 1.5, "dripstone_block": 1}, size=4),
    underside=patches({"dripstone_block": 2.5, "tuff": 2, "andesite": 1.5, "calcite": 0.5, "deepslate": 0.8},
                      size=4),
    sand=patches({"sand": 5, "gravel": 1, "clay": 1}, size=3),
    path=patches({"dirt_path": 6, "coarse_dirt": 2, "gravel": 1.2, "packed_mud": 1}, size=3),
    plaza=patches({"stone_bricks": 5, "cracked_stone_bricks": 1, "mossy_stone_bricks": 1, "polished_andesite": 2,
                   "andesite": 1}, size=3),
    wall=patches({"stone_bricks": 6, "cracked_stone_bricks": 1.2, "mossy_stone_bricks": 1, "tuff_bricks": 0.8,
                  "andesite": 0.6}, size=2),
    wall_base=patches({"cobblestone": 3, "mossy_cobblestone": 2, "stone": 1, "andesite": 1}, size=2),
    plaster=patches({"calcite": 4, "white_terracotta": 1.5, "smooth_quartz": 1}, size=2),
    frame="dark_oak_log", pillar=patches({"stripped_spruce_log[axis=y]": 1}), floor="spruce_planks",
    window="glass_pane", glass="glass", fence="spruce_fence", railing="stone_brick_wall", door="spruce_door",
    trapdoor="spruce_trapdoor", trunk="oak_wood", trunk_log="oak_log",
    leaves=patches({"oak_leaves": 5, "azalea_leaves": 2, "flowering_azalea_leaves": 1, "dark_oak_leaves": 1.2}, size=3),
    bush=patches({"azalea_leaves": 3, "oak_leaves": 2, "flowering_azalea_leaves": 1}, size=2),
    flowers=["poppy", "dandelion", "cornflower", "oxeye_daisy", "allium", "azure_bluet", "lily_of_the_valley"],
    tall_flowers=["rose_bush", "lilac", "peony", "tall_grass", "large_fern"],
    ground_cover={"short_grass": 12, "fern": 3, "poppy": 0.8, "dandelion": 0.8, "cornflower": 0.6, "oxeye_daisy": 0.6,
                  "tall_grass": 1.2, "large_fern": 0.5},
    lamp="lantern", lamp_hanging="lantern[hanging=true]", light_hidden="shroomlight",
    crystal=patches({"amethyst_block": 3, "purple_stained_glass": 1, "budding_amethyst": 1}, size=2),
    metal="chain", water="water", liquid="water", accent=mix({"gold_block": 1}),
    trim="stone_bricks", wood_trim="spruce_planks", roof="deepslate_tiles", roof_accent="dark_oak_planks",
    trim_dark="polished_deepslate", tree_kinds=["oak_giant", "oak", "birch", "willow"], roof_style="gable", lamp_style="post",
    notes="Летающие острова, каменные башни с тёмными черепичными крышами, фахверк, светлый камень + тёмное дерево.",
))

# ---------------------------------------------------------------- asian / sakura
register(Theme(
    name="asian_sakura", title="Азия / сакура", biome="cherry_grove",
    grass=patches({"moss_block": 3, "grass_block": 9, "podzol": 0.5}, size=6),
    soil=patches({"dirt": 5, "coarse_dirt": 2, "rooted_dirt": 1}, size=3),
    rock=patches({"stone": 4, "andesite": 3, "tuff": 1, "mossy_cobblestone": 1}, size=3),
    rock_deep=patches({"tuff": 3, "andesite": 2, "stone": 2, "deepslate": 1}, size=4),
    underside=patches({"tuff": 2, "andesite": 2, "calcite": 1, "stone": 1, "deepslate": 0.6}, size=4),
    sand=patches({"sand": 4, "gravel": 2}, size=3),
    path=patches({"gravel": 6, "andesite": 1, "coarse_dirt": 1}, size=2),
    plaza=patches({"polished_andesite": 4, "stone_bricks": 2, "smooth_stone": 2, "andesite": 1}, size=3),
    wall=patches({"calcite": 4, "white_terracotta": 1, "smooth_quartz": 1}, size=2),
    wall_base=patches({"stone_bricks": 3, "mossy_stone_bricks": 1, "polished_andesite": 1}, size=2),
    plaster=patches({"calcite": 4, "smooth_quartz": 1}, size=2),
    frame="dark_oak_log", pillar="stripped_mangrove_log", floor="dark_oak_planks",
    window="white_stained_glass_pane", glass="white_stained_glass", fence="dark_oak_fence", railing="mangrove_fence",
    door="dark_oak_door", trapdoor="birch_trapdoor", trunk="cherry_wood", trunk_log="cherry_log",
    leaves=patches({"cherry_leaves": 9, "flowering_azalea_leaves": 1}, size=3),
    bush=patches({"azalea_leaves": 2, "flowering_azalea_leaves": 2}, size=2),
    flowers=["pink_tulip", "allium", "azure_bluet", "lily_of_the_valley", "white_tulip"],
    tall_flowers=["peony", "lilac", "tall_grass"],
    ground_cover={"short_grass": 8, "pink_petals[flower_amount=4]": 3, "pink_petals[flower_amount=2]": 2, "fern": 1},
    lamp="lantern", lamp_hanging="lantern[hanging=true]", light_hidden="shroomlight",
    crystal=patches({"pink_stained_glass": 2, "white_stained_glass": 1}, size=2),
    metal="chain", water="water", liquid="water", accent=mix({"red_terracotta": 1}),
    trim="polished_andesite", wood_trim="dark_oak_planks", roof="deepslate_tiles", roof_accent="mangrove_planks",
    trim_dark="dark_oak_planks",
    tree_kinds=["cherry", "cherry", "pine", "bush"], roof_style="asian", lamp_style="stone_lantern",
    notes="Сакура, пагоды с загнутыми краями крыш, красные колонны, белые стены, гравийные дорожки, пруды с кувшинками.",
))

# ---------------------------------------------------------------- dark / infernal
register(Theme(
    name="dark_infernal", title="Тёмный / адский", biome="crimson_forest",
    grass=patches({"crimson_nylium": 4, "netherrack": 1.5, "blackstone": 1.5, "soul_soil": 0.8, "warped_nylium": 0.12},
                  size=5),  # teal only as a rare accent: big teal/brown patches read as camouflage
    soil=patches({"netherrack": 4, "soul_soil": 2, "blackstone": 1}, size=3),
    rock=patches({"blackstone": 4, "basalt": 2, "deepslate": 2, "tuff": 1, "gilded_blackstone": 0.1}, size=3),
    rock_deep=patches({"deepslate": 3, "blackstone": 2, "basalt": 1, "magma_block": 0.2}, size=4),
    underside=patches({"blackstone": 3, "basalt": 2, "magma_block": 0.4, "netherrack": 1}, size=4),
    sand=patches({"soul_sand": 3, "soul_soil": 2}, size=3),
    path=patches({"soul_soil": 3, "blackstone": 2, "polished_blackstone": 2, "basalt": 1}, size=2),
    plaza=patches({"polished_blackstone_bricks": 5, "cracked_polished_blackstone_bricks": 2, "polished_blackstone": 2,
                   "gilded_blackstone": 0.15}, size=2),
    wall=patches({"polished_blackstone_bricks": 5, "cracked_polished_blackstone_bricks": 1.5, "nether_bricks": 2,
                  "deepslate_tiles": 1}, size=2),
    wall_base=patches({"blackstone": 3, "basalt": 1, "cobbled_deepslate": 1}, size=2),
    plaster=patches({"red_nether_bricks": 3, "nether_bricks": 1}, size=2),
    frame="polished_basalt", pillar="polished_basalt", floor="polished_blackstone_bricks",
    window="red_stained_glass_pane", glass="red_stained_glass", fence="nether_brick_fence",
    railing="polished_blackstone_wall", door="crimson_door", trapdoor="iron_trapdoor",
    trunk="crimson_hyphae", trunk_log="crimson_stem",
    leaves=patches({"nether_wart_block": 6, "shroomlight": 0.4, "red_nether_bricks": 0.3}, size=2),
    bush=patches({"nether_wart_block": 3, "crimson_hyphae": 0.3}, size=2),
    flowers=["crimson_roots", "crimson_fungus", "warped_roots"],
    tall_flowers=["crimson_roots"],
    ground_cover={"crimson_roots": 6, "crimson_fungus": 1.5, "warped_roots": 1, "nether_sprouts": 0.5},
    lamp="soul_lantern", lamp_hanging="soul_lantern[hanging=true]", light_hidden="shroomlight",
    crystal=patches({"crying_obsidian": 2, "obsidian": 3, "red_stained_glass": 1}, size=2),
    metal="chain", water="lava", liquid="lava", accent=mix({"gold_block": 1, "gilded_blackstone": 1}),
    trim="polished_blackstone", wood_trim="crimson_planks", roof="deepslate_tiles", roof_accent="nether_bricks",
    trim_dark="red_nether_bricks",
    tree_kinds=["fungus_giant", "dead", "fungus_giant"], roof_style="gothic", lamp_style="brazier",
    notes="Блэкстоун и базальт, готика, шипы, лавопады, огни душ, огромные грибы и мёртвые деревья, контраст красного и бирюзы.",
))

# ---------------------------------------------------------------- winter / north
register(Theme(
    name="winter_north", title="Зима / север", biome="snowy_taiga",
    grass=patches({"snow_block": 10, "grass_block": 1.5, "coarse_dirt": 0.4, "packed_ice": 0.2}, size=6),
    soil=patches({"dirt": 4, "coarse_dirt": 2, "gravel": 1}, size=3),
    rock=patches({"stone": 4, "andesite": 2, "calcite": 1.5, "diorite": 1, "cobblestone": 0.5}, size=4),
    rock_deep=patches({"deepslate": 3, "tuff": 1, "andesite": 1, "packed_ice": 0.3}, size=4),
    underside=patches({"packed_ice": 2, "blue_ice": 1, "deepslate": 2, "calcite": 1}, size=4),
    sand=patches({"gravel": 3, "snow_block": 2}, size=3),
    path=patches({"gravel": 3, "coarse_dirt": 2, "snow_block": 2, "spruce_planks": 0.5}, size=2),
    plaza=patches({"stone_bricks": 4, "polished_andesite": 2, "polished_diorite": 1, "cobblestone": 1}, size=3),
    wall=patches({"spruce_planks": 5, "stripped_spruce_wood": 1}, size=2),
    wall_base=patches({"cobblestone": 3, "stone_bricks": 2, "mossy_cobblestone": 0.5}, size=2),
    plaster=patches({"spruce_planks": 3, "stripped_spruce_wood": 1}, size=2),
    frame="spruce_log", pillar="stripped_spruce_log", floor="spruce_planks",
    window="orange_stained_glass_pane", glass="orange_stained_glass", fence="spruce_fence", railing="spruce_fence",
    door="spruce_door", trapdoor="spruce_trapdoor", trunk="spruce_wood", trunk_log="spruce_log",
    leaves=patches({"spruce_leaves": 1}, size=3),
    bush=patches({"spruce_leaves": 3, "azalea_leaves": 1}, size=2),
    flowers=["fern", "sweet_berry_bush[age=3]"],
    tall_flowers=["large_fern"],
    ground_cover={"snow[layers=1]": 14, "snow[layers=2]": 5, "snow[layers=3]": 1.5, "fern": 0.5,
                  "sweet_berry_bush[age=3]": 0.3},
    lamp="lantern", lamp_hanging="lantern[hanging=true]", light_hidden="glowstone",
    crystal=patches({"blue_ice": 3, "packed_ice": 2, "light_blue_stained_glass": 1}, size=2),
    metal="chain", water="water", liquid="water", accent=mix({"blue_ice": 1}),
    trim="stone_bricks", wood_trim="spruce_planks", roof="spruce_planks", roof_accent="dark_oak_planks",
    trim_dark="deepslate_bricks",
    tree_kinds=["pine", "pine", "birch"], roof_style="nordic", lamp_style="post",
    notes="Снег слоями, ели со снежными шапками, скандинавские дома из ели с крутыми крышами, лёд, тёплый свет в окнах.",
))


def names() -> list[str]:
    return list(THEMES)
