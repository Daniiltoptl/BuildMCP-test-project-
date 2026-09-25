"""Biome colors (grass, foliage, water) used to tint block textures like the game does."""

from __future__ import annotations

import numpy as np

# name: (temperature, downfall, grass_override, foliage_override, water_color, grass_modifier)
BIOMES: dict[str, tuple] = {
    "plains": (0.8, 0.4, None, None, 0x3F76E4, None),
    "sunflower_plains": (0.8, 0.4, None, None, 0x3F76E4, None),
    "meadow": (0.5, 0.8, None, None, 0x0E4ECF, None),
    "forest": (0.7, 0.8, None, None, 0x3F76E4, None),
    "flower_forest": (0.7, 0.8, None, None, 0x3F76E4, None),
    "birch_forest": (0.6, 0.6, None, None, 0x3F76E4, None),
    "old_growth_birch_forest": (0.6, 0.6, None, None, 0x3F76E4, None),
    "dark_forest": (0.7, 0.8, None, None, 0x3F76E4, "dark_forest"),
    "pale_garden": (0.7, 0.8, 0x778272, 0x878D76, 0x76889D, None),
    "taiga": (0.25, 0.8, None, None, 0x3F76E4, None),
    "old_growth_pine_taiga": (0.3, 0.8, None, None, 0x3F76E4, None),
    "old_growth_spruce_taiga": (0.25, 0.8, None, None, 0x3F76E4, None),
    "snowy_taiga": (-0.5, 0.4, None, None, 0x3D57D6, None),
    "snowy_plains": (0.0, 0.5, None, None, 0x3F76E4, None),
    "ice_spikes": (0.0, 0.5, None, None, 0x3F76E4, None),
    "grove": (-0.2, 0.8, None, None, 0x3F76E4, None),
    "snowy_slopes": (-0.3, 0.9, None, None, 0x3F76E4, None),
    "frozen_peaks": (-0.7, 0.9, None, None, 0x3F76E4, None),
    "jagged_peaks": (-0.7, 0.9, None, None, 0x3F76E4, None),
    "frozen_river": (0.0, 0.5, None, None, 0x3938C9, None),
    "snowy_beach": (0.05, 0.3, None, None, 0x3D57D6, None),
    "cherry_grove": (0.5, 0.8, 0xB6DB61, 0xB6DB61, 0x5DB7EF, None),
    "swamp": (0.8, 0.9, 0x6A7039, 0x6A7039, 0x617B64, None),
    "mangrove_swamp": (0.8, 0.9, 0x6A7039, 0x8DB127, 0x3A7A6A, None),
    "jungle": (0.95, 0.9, None, None, 0x3F76E4, None),
    "sparse_jungle": (0.95, 0.8, None, None, 0x3F76E4, None),
    "bamboo_jungle": (0.95, 0.9, None, None, 0x3F76E4, None),
    "savanna": (2.0, 0.0, None, None, 0x3F76E4, None),
    "savanna_plateau": (2.0, 0.0, None, None, 0x3F76E4, None),
    "desert": (2.0, 0.0, None, None, 0x3F76E4, None),
    "badlands": (2.0, 0.0, 0x90814D, 0x9E814D, 0x3F76E4, None),
    "wooded_badlands": (2.0, 0.0, 0x90814D, 0x9E814D, 0x3F76E4, None),
    "beach": (0.8, 0.4, None, None, 0x3F76E4, None),
    "river": (0.5, 0.5, None, None, 0x3F76E4, None),
    "ocean": (0.5, 0.5, None, None, 0x3F76E4, None),
    "warm_ocean": (0.5, 0.5, None, None, 0x43D5EE, None),
    "lukewarm_ocean": (0.5, 0.5, None, None, 0x45ADF2, None),
    "cold_ocean": (0.5, 0.5, None, None, 0x3D57D6, None),
    "mushroom_fields": (0.9, 1.0, None, None, 0x3F76E4, None),
    "windswept_hills": (0.2, 0.3, None, None, 0x3F76E4, None),
    "stony_shore": (0.2, 0.3, None, None, 0x3F76E4, None),
    "lush_caves": (0.5, 0.5, None, None, 0x3F76E4, None),
    "nether_wastes": (2.0, 0.0, None, None, 0x3F76E4, None),
    "crimson_forest": (2.0, 0.0, None, None, 0x3F76E4, None),
    "warped_forest": (2.0, 0.0, None, None, 0x3F76E4, None),
    "soul_sand_valley": (2.0, 0.0, None, None, 0x3F76E4, None),
    "basalt_deltas": (2.0, 0.0, None, None, 0x3F76E4, None),
    "the_end": (0.5, 0.5, None, None, 0x3F76E4, None),
}

FALLBACK_GRASS = 0x91BD59
FALLBACK_FOLIAGE = 0x77AB2F


def _rgb(c: int) -> tuple[float, float, float]:
    return (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)


def _from_colormap(cmap: np.ndarray | None, temp: float, down: float, fallback: int) -> int:
    if cmap is None:
        return fallback
    t = min(max(temp, 0.0), 1.0)
    d = min(max(down, 0.0), 1.0) * t
    i = int((1.0 - t) * 255.0)
    j = int((1.0 - d) * 255.0)
    if j >= cmap.shape[0] or i >= cmap.shape[1]:
        return fallback
    r, g, b = (int(v) for v in cmap[j, i, :3])
    return (r << 16) | (g << 8) | b


def biome_colors(name: str, grass_map: np.ndarray | None, foliage_map: np.ndarray | None) -> np.ndarray:
    """(3, 3) float array: rows grass, foliage, water (RGB 0..1)."""
    key = name.removeprefix("minecraft:")
    temp, down, g_over, f_over, water, modifier = BIOMES.get(key, BIOMES["plains"])
    grass = g_over if g_over is not None else _from_colormap(grass_map, temp, down, FALLBACK_GRASS)
    if modifier == "dark_forest":
        grass = ((grass & 0xFEFEFE) + 0x28340A) >> 1
    foliage = f_over if f_over is not None else _from_colormap(foliage_map, temp, down, FALLBACK_FOLIAGE)
    return np.array([_rgb(grass), _rgb(foliage), _rgb(water)], dtype=np.float32)


# Blocks tinted with the biome grass color / foliage color / water color.
GRASS_TINTED = {
    "grass_block", "short_grass", "tall_grass", "fern", "large_fern", "potted_fern", "sugar_cane", "bush",
}
FOLIAGE_TINTED = {
    "oak_leaves", "jungle_leaves", "acacia_leaves", "dark_oak_leaves", "mangrove_leaves", "vine", "leaf_litter",
}
WATER_TINTED = {"water", "water_cauldron", "bubble_column"}
FIXED_TINTS = {
    "birch_leaves": 0x80A755, "spruce_leaves": 0x619961, "lily_pad": 0x208030, "attached_melon_stem": 0xE0C71C,
    "attached_pumpkin_stem": 0xE0C71C, "melon_stem": 0x9CB42B, "pumpkin_stem": 0x9CB42B, "redstone_wire": 0xC81C00,
}
