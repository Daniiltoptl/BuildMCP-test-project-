"""Terrain: floating islands, ground patches, ponds, waterfalls, ground cover.

    isl = terrain.island(S, center=(0, 80, 0), radius=40, theme="fantasy_medieval", seed=3)
    terrain.cover(S, isl.surface, theme, density=0.35)
    terrain.pond(S, (10, 80, -6), radius=6, theme=theme)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..geo.box import Box
from ..geo.mask import Mask, as_mask
from ..paint import palette as P
from ..paint.noise import fbm, hash01, ridged
from .. import themes as themes_mod


def _theme(theme):
    if theme is None:
        return themes_mod.get("fantasy_medieval")
    if isinstance(theme, str):
        return themes_mod.get(theme)
    return theme


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


@dataclass
class Terrain:
    body: Mask
    surface: Mask
    heights: np.ndarray  # top y per (x, z) column, -9999 where empty
    bottoms: np.ndarray
    x0: int
    z0: int
    center: tuple
    radius: tuple

    def height_at(self, x: int, z: int) -> int | None:
        i, k = int(x) - self.x0, int(z) - self.z0
        if 0 <= i < self.heights.shape[0] and 0 <= k < self.heights.shape[1] and self.heights[i, k] > -9999:
            return int(self.heights[i, k])
        return None

    def on_top(self, x: int, z: int) -> tuple[int, int, int] | None:
        """Position just above the ground at column (x, z)."""
        h = self.height_at(x, z)
        return None if h is None else (int(x), h + 1, int(z))

    @property
    def edge(self) -> Mask:
        """Top cells near the outer rim."""
        return self.surface & self.body.sides().dilate(1, horizontal=True)

    @property
    def underside(self) -> Mask:
        return self.body.bottom()


def _grid(center, rx, rz, pad=1.5):
    cx, cz = float(center[0]), float(center[2])
    x0 = int(math.floor(cx - rx * pad))
    z0 = int(math.floor(cz - rz * pad))
    xs = np.arange(x0, int(math.ceil(cx + rx * pad)) + 1)
    zs = np.arange(z0, int(math.ceil(cz + rz * pad)) + 1)
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    return X, Z, x0, z0


def _columns_to_mask(top: np.ndarray, bottom: np.ndarray, x0: int, z0: int) -> Mask:
    valid = top >= bottom
    if not valid.any():
        return Mask.empty()
    ylo = int(bottom[valid].min())
    yhi = int(top[valid].max())
    ys = np.arange(ylo, yhi + 1)
    arr = (ys[None, :, None] >= bottom[:, None, :]) & (ys[None, :, None] <= top[:, None, :]) & valid[:, None, :]
    return Mask((x0, ylo, z0), arr)


def island(scene, center, radius, *, top_y: int | None = None, hill: float = 3.0, roughness: float = 0.35,
           depth: float | None = None, spikes: int | None = None, flat_center: float = 0.35, rim: float = 4.0,
           soil_depth: int = 3, theme=None, seed: int = 0, paint: bool = True, strata: bool = True,
           decorate: bool = True) -> Terrain:
    """Floating island: natural top with a rounded rim, smooth bowl underside tapering into
    a few big hanging spikes.

    radius: number or (rx, rz). depth: underside depth below the rim (default 1.1 * radius).
    flat_center: fraction of the radius kept flat (plaza area). spikes: number of big hanging
    spikes (default by size). rim: how far (blocks) the top curves down at the edge.
    """
    T = _theme(theme)
    rx, rz = (float(radius), float(radius)) if np.isscalar(radius) else (float(radius[0]), float(radius[1]))
    R = max(rx, rz)
    cy = int(center[1]) if top_y is None else int(top_y)
    depth = 1.1 * R if depth is None else float(depth)
    rng = np.random.default_rng(seed + 101)
    X, Z, x0, z0 = _grid(center, rx, rz, pad=1.35)
    cx, cz = float(center[0]), float(center[2])
    d0 = np.sqrt(((X + 0.5 - cx) / rx) ** 2 + ((Z + 0.5 - cz) / rz) ** 2)
    d = d0 + roughness * 0.5 * fbm(X, Z, 0, scale=R * 0.6, octaves=3, seed=seed) \
        + roughness * 0.1 * fbm(X, Z, 0, scale=R * 0.18, octaves=2, seed=seed + 1)
    foot = d < 1.0
    # --- top surface: gentle hills, flat plaza in the middle, rounded rim
    flat_w = 1 - _smoothstep(flat_center * 0.7, flat_center + 0.15, d)
    hills = hill * fbm(X, Z, 0, scale=R * 0.6, octaves=4, seed=seed + 2)
    rim_t = _smoothstep(1.0 - min(0.5, 2.2 * rim / R), 1.0, d)
    top = cy + hills * (1 - flat_w) - rim * rim_t ** 1.8
    # --- underside: smooth bowl + a few big spikes + medium noise
    core = np.clip(1 - d, 0, 1)
    bowl = depth * (1 - np.clip(d, 0, 1) ** 1.7) ** 1.25
    bowl *= 1 + 0.18 * fbm(X, Z, 0, scale=R * 0.45, octaves=3, seed=seed + 3)
    n_spikes = spikes if spikes is not None else max(2, int(R / 7))
    centers = []
    for _ in range(n_spikes * 20):
        if len(centers) >= n_spikes:
            break
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 1)) * 0.62
        px, pz = cx + math.cos(a) * rr * rx, cz + math.sin(a) * rr * rz
        if all(math.hypot(px - qx, pz - qz) > R * 0.35 for qx, qz, _, _ in centers):
            centers.append((px, pz, rng.uniform(0.13, 0.24) * R, rng.uniform(0.35, 0.9) * depth))
    spike = np.zeros_like(bowl)
    for px, pz, rs, ls in centers:
        dist = np.sqrt((X + 0.5 - px) ** 2 + (Z + 0.5 - pz) ** 2) / rs
        wob = 1 + 0.25 * fbm(X, Z, 0, scale=rs * 0.8, seed=seed + 5)
        spike = np.maximum(spike, ls * np.clip(1 - dist * wob, 0, 1) ** 1.7)
    keel = depth * 0.5 * np.clip(1 - d0 / 0.35, 0, 1) ** 1.5  # the central keel goes deepest
    under = bowl + spike + keel + 1.8 * fbm(X, Z, 0, scale=5, octaves=2, seed=seed + 6) * core
    rim_thick = soil_depth + 1 + 2.0 * (1 - rim_t)
    top_i = np.where(foot, np.round(top), -10000).astype(int)
    bottom_i = np.where(foot, np.round(top - rim_thick - np.maximum(under, 0.0)), 10000).astype(int)
    body = _columns_to_mask(top_i, bottom_i, x0, z0)
    heights = np.where(foot, top_i, -9999)
    ter = Terrain(body=body, surface=body.top(), heights=heights, bottoms=np.where(foot, bottom_i, 9999),
                  x0=x0, z0=z0, center=(cx, cy, cz), radius=(rx, rz))
    if paint:
        paint_terrain(scene, ter, T, soil_depth=soil_depth, strata=strata, seed=seed)
        if decorate:
            decorate_underside(scene, ter, T, seed=seed)
    return ter


def ground(scene, box, *, base_y: int | None = None, hill: float = 4.0, scale: float = 40.0, theme=None,
           seed: int = 0, depth: int = 6, falloff: float = 0.0, paint: bool = True) -> Terrain:
    """Rolling ground over a rectangular area (box x/z extent), ``depth`` blocks thick.
    ``falloff`` > 0 lowers the edges (fraction of the half-size) for a soft border."""
    T = _theme(theme)
    b = Box.of(box)
    base = b.y1 if base_y is None else int(base_y)
    xs = np.arange(b.x1, b.x2 + 1)
    zs = np.arange(b.z1, b.z2 + 1)
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    h = base + hill * fbm(X, Z, 0, scale=scale, octaves=4, seed=seed)
    if falloff > 0:
        cx, cz = (b.x1 + b.x2) / 2, (b.z1 + b.z2) / 2
        hx, hz = (b.x2 - b.x1) / 2, (b.z2 - b.z1) / 2
        e = np.maximum(np.abs(X - cx) / max(hx, 1), np.abs(Z - cz) / max(hz, 1))
        h = h - hill * 2 * _smoothstep(1 - falloff, 1.0, e)
    top_i = np.round(h).astype(int)
    bottom_i = top_i - depth
    body = _columns_to_mask(top_i, bottom_i, b.x1, b.z1)
    ter = Terrain(body=body, surface=body.top(), heights=top_i, bottoms=bottom_i, x0=b.x1, z0=b.z1,
                  center=b.center, radius=((b.x2 - b.x1) / 2, (b.z2 - b.z1) / 2))
    if paint:
        paint_terrain(scene, ter, T, seed=seed)
    return ter


def paint_terrain(scene, ter: Terrain, theme, soil_depth: int = 3, strata: bool = True, seed: int = 0) -> None:
    """Layers by depth under the surface: top (grass), soil band, mossy transition, rock with a
    gradient to deep rock, underside palette at the bottom, optional strata bands."""
    T = _theme(theme)
    body = ter.body
    if not body:
        return
    xs, ys, zs = body.coords()
    top = ter.heights[xs - ter.x0, zs - ter.z0]
    bot = ter.bottoms[xs - ter.x0, zs - ter.z0]
    below = top - ys  # 0 at the surface
    total = np.maximum(top - bot, 1)
    frac = below / total  # 0 top .. 1 bottom
    # jitter the band limits so layers are not ruler-straight
    j = hash01(xs, ys, zs, seed + 41)
    wob = fbm(xs, ys, zs, scale=6, octaves=2, seed=seed + 42)
    soil_lim = soil_depth + np.round(wob * 1.2 + (j - 0.5) * 0.8)
    # where the column is exposed at the side (rim, cliffs) the dirt band is thin: 1-2 blocks
    side = body.sides()
    side_arr = side.to_box(body.extent)[xs - body.origin[0], ys - body.origin[1], zs - body.origin[2]]
    soil_lim = np.where(side_arr, np.minimum(soil_lim, 1 + (j > 0.55)), soil_lim)
    trans_lim = soil_lim + 2 + np.round(wob * 1.5)
    under_frac = 0.72 + 0.1 * wob
    sel_top = below == 0
    sel_soil = (below >= 1) & (below <= soil_lim)
    sel_trans = (below > soil_lim) & (below <= trans_lim)
    sel_under = (frac >= under_frac) & ~sel_top & ~sel_soil & ~sel_trans
    sel_rock = ~(sel_top | sel_soil | sel_trans | sel_under)
    moss = {"dark_infernal": P.patches({"netherrack": 2, "blackstone": 2, "crimson_nylium": 0.5}, size=2, seed=seed + 7),
            "winter_north": P.patches({"snow_block": 1, "stone": 2, "andesite": 1, "packed_ice": 0.5}, size=2, seed=seed + 7),
            }.get(T.name, P.patches({"moss_block": 2, "mossy_cobblestone": 2, "stone": 2, "andesite": 1},
                                    size=2, seed=seed + 7))
    rock_pal = P.Gradient([T.rock, T.rock, T.rock_deep], axis="y", start=float(ys.max()), end=float(ys.min()),
                          jitter=1.2, noise=3.0, noise_scale=10.0, seed=seed + 11)

    def put(sel, pal):
        if sel.any():
            scene.put(Mask.from_points(np.stack([xs[sel], ys[sel], zs[sel]], axis=1)), pal)

    put(sel_rock, rock_pal)
    put(sel_under, T.underside)
    put(sel_trans, moss)
    put(sel_soil, T.soil)
    put(sel_top, T.grass)
    if strata:
        band = sel_rock & (np.abs(np.sin((ys + 3.0 * fbm(xs, ys, zs, scale=16, seed=seed + 13)) * 0.8)) > 0.95)
        alt = P.patches({"basalt": 2, "blackstone": 1}, size=3, seed=seed + 14) if T.name == "dark_infernal" else \
            P.patches({"tuff": 2, "andesite": 1, "calcite": 0.5}, size=3, seed=seed + 14)
        put(band, alt)


def decorate_underside(scene, ter: Terrain, theme, density: float = 0.035, seed: int = 0) -> int:
    """Hanging roots, vines, glow berries, dripstone (or icicles / weeping vines by theme) under an island."""
    T = _theme(theme)
    under = ter.underside
    if not under:
        return 0
    rng = np.random.default_rng(seed + 21)
    spots = under.sample(density=density, min_dist=1.5, seed=seed + 22)
    placed = 0
    for (x, y, z) in spots:
        if scene.get(x, y - 1, z) != "minecraft:air":
            continue
        r = rng.random()
        n = int(rng.integers(1, 6))
        if T.name == "dark_infernal":
            col = "weeping_vines" if r < 0.7 else "pointed_dripstone[vertical_direction=down]"
        elif T.name == "winter_north":
            col = "pointed_dripstone[vertical_direction=down]" if r < 0.5 else "hanging_roots"
            n = min(n, 3)
        else:
            col = ("hanging_roots" if r < 0.35 else "cave_vines[berries=true]" if r < 0.55 else
                   "vine[north=true]" if r < 0.6 else "pointed_dripstone[vertical_direction=down]" if r < 0.8
                   else "glow_lichen[up=true]")
            if col.startswith("hanging_roots") or col.startswith("glow_lichen"):
                n = 1
        for k in range(1, n + 1):
            if scene.get(x, y - k, z) != "minecraft:air":
                break
            state = col
            if col.startswith("vine"):
                state = "vine[up=true]" if k == 1 else "vine[north=false,up=false,south=true]"
                if k > 1:
                    break
            scene.set(x, y - k, z, state)
            placed += 1
    return placed


def cover(scene, surface, theme=None, density: float = 0.3, avoid=None, seed: int = 0, items: dict | None = None) -> int:
    """Scatter ground cover (grass, ferns, flowers, snow layers...) on top of ``surface`` cells.
    ``items`` overrides the theme's ground_cover weights. ``avoid`` = mask/box kept clear (paths, plazas)."""
    T = _theme(theme)
    surf = as_mask(surface)
    if avoid is not None:
        av = as_mask(avoid)
        surf = surf - av - av.below(1)
    pts = surf.points()
    if len(pts) == 0:
        return 0
    weights = items or T.ground_cover
    names = list(weights)
    w = np.array([weights[n] for n in names], float)
    w = w / w.sum()
    r = hash01(pts[:, 0], pts[:, 1], pts[:, 2], seed + 31)
    keep = r < density
    pts = pts[keep]
    if len(pts) == 0:
        return 0
    # cluster choice with low-frequency noise so flowers come in drifts
    u = np.clip((fbm(pts[:, 0], pts[:, 1], pts[:, 2], scale=7, octaves=2, seed=seed + 32) + 0.6) / 1.2, 0, 0.9999)
    idx = np.searchsorted(np.cumsum(w), u)
    placed = 0
    for (x, y, z), i in zip(pts.tolist(), idx.tolist()):
        above = scene.get(x, y + 1, z)
        if above != "minecraft:air":
            continue
        ground_state = scene.get(x, y, z)
        name = names[min(i, len(names) - 1)]
        base = name.split("[", 1)[0]
        if base not in ("snow",) and not _plantable(ground_state, base):
            continue
        state = name
        if base in ("pink_petals", "wildflowers", "leaf_litter"):
            facing = ["north", "east", "south", "west"][int(hash01(x, y, z, seed + 33) * 4) % 4]
            state = name.replace("]", f",facing={facing}]") if "[" in name else f"{name}[facing={facing}]"
        scene.set(x, y + 1, z, state)
        placed += 1
    return placed


_SOIL = ("grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "moss_block", "mud", "mycelium",
         "farmland", "pale_moss_block")
_NETHER_SOIL = ("crimson_nylium", "warped_nylium", "soul_soil", "netherrack", "soul_sand")


def _plantable(ground_state: str, plant: str) -> bool:
    g = ground_state.removeprefix("minecraft:").split("[", 1)[0]
    if plant in ("crimson_roots", "warped_roots", "crimson_fungus", "warped_fungus", "nether_sprouts"):
        return g in _NETHER_SOIL or g in _SOIL
    if plant.startswith("snow"):
        return g not in ("ice", "packed_ice", "blue_ice", "air")
    return g in _SOIL


def pond(scene, center, radius: float, depth: int = 3, theme=None, seed: int = 0, lily: float = 0.08,
         shore: bool = True) -> Mask:
    """Carve a natural pond into the ground at ``center`` (x, surface_y, z) and fill it with the theme liquid."""
    T = _theme(theme)
    cx, cy, cz = (float(v) for v in center)
    R = float(radius)
    r_int = int(R) + 3
    xs = np.arange(int(cx) - r_int, int(cx) + r_int + 1)
    zs = np.arange(int(cz) - r_int, int(cz) + r_int + 1)
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    d = np.sqrt((X + 0.5 - cx) ** 2 + (Z + 0.5 - cz) ** 2) / R + 0.25 * fbm(X, Z, 0, scale=R * 0.7, seed=seed)
    inside = d < 1.0
    dep = np.where(inside, np.maximum(1, np.round(depth * (1 - d ** 2))), 0).astype(int)
    water_y = int(cy) - 1
    water_cells = []
    for (i, k) in zip(*np.nonzero(inside)):
        x, z = int(xs[i]), int(zs[k])
        for y in range(water_y - dep[i, k] + 1, int(cy) + 3):
            scene.set(x, y, z, "minecraft:air") if y > water_y else scene.set(x, y, z, T.liquid)
            if y <= water_y:
                water_cells.append((x, y, z))
        # basin floor
        floor_y = water_y - dep[i, k]
        if scene.get(x, floor_y, z) in ("minecraft:air",) or True:
            scene.put((x, floor_y, z), P.Mix({"gravel": 2, "clay": 1, "sand": 1, "dirt": 1}, cluster=2, seed=seed + 5)
                      if T.liquid == "water" else "magma_block")
    water = Mask.from_points(water_cells) if water_cells else Mask.empty()
    if shore:
        ring = (d >= 1.0) & (d < 1.25)
        for (i, k) in zip(*np.nonzero(ring)):
            x, z = int(xs[i]), int(zs[k])
            y = scene.top_y(x, z)
            if y is not None and abs(y - (cy - 1)) <= 2:
                scene.put((x, y, z), T.sand if hash01(x, y, z, seed + 6) < 0.6 else T.soil)
    if lily > 0 and T.liquid == "water":
        surf = [(x, y, z) for (x, y, z) in water_cells if y == water_y]
        for (x, y, z) in surf:
            if hash01(x, y, z, seed + 7) < lily:
                scene.set(x, y + 1, z, "lily_pad")
            elif hash01(x, y, z, seed + 8) < 0.15 and scene.get(x, y - 1, z) != "minecraft:water":
                pass
    return water


def waterfall(scene, top, direction: str = "south", width: int = 2, drop: int = 30, liquid: str = "water") -> Mask:
    """A falling column from an edge: source blocks at ``top`` spilling towards ``direction`` then falling ``drop``."""
    dx, dz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[direction]
    x, y, z = (int(v) for v in top)
    cells = []
    for w in range(width):
        ox, oz = (w * abs(dz), w * abs(dx))
        sx, sz = x + ox, z + oz
        scene.set(sx, y, sz, liquid)
        cells.append((sx, y, sz))
        fx, fz = sx + dx, sz + dz
        for k in range(0, drop + 1):
            if k > 0 and scene.get(fx, y - k, fz) not in ("minecraft:air",) and not scene.get(fx, y - k, fz).startswith(f"minecraft:{liquid}"):
                break
            scene.set(fx, y - k, fz, f"{liquid}[level=8]" if k > 0 else f"{liquid}[level=1]")
            cells.append((fx, y - k, fz))
    return Mask.from_points(cells)
