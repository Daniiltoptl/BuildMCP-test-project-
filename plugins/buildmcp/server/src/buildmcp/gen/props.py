"""Props: lamps, benches, fountains, wells, market stalls, portal frames, banners, braziers,
stone lanterns, planters. Each takes a ground position ``at`` (the block they stand on)."""

from __future__ import annotations

import math

import numpy as np

from ..blocks import families as F
from ..geo import sdf, shapes
from ..geo.mask import Mask
from ..paint import palette as P
from .. import themes as themes_mod

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}


def _theme(theme):
    if theme is None:
        return themes_mod.get("fantasy_medieval")
    return themes_mod.get(theme) if isinstance(theme, str) else theme


def _fam(scene, base):
    return F.family(scene.reg, base)


def lamp_post(scene, at, *, theme=None, height: int = 4, style: str | None = None, facing: str = "south") -> None:
    """Street lamp. style: post (wood/iron post + arm + hanging lantern) | pillar (stone pillar + lantern on top)
    | stone_lantern (tōrō) | brazier | double (two hanging lanterns)."""
    T = _theme(theme)
    style = style or T.lamp_style
    x, y, z = (int(v) for v in at)
    y += 1
    trim = _fam(scene, T.trim)
    wood = _fam(scene, T.wood_trim)
    if style in ("post", "double"):
        scene.set(x, y, z, trim.wall or "cobblestone_wall")
        for h in range(1, height):
            scene.set(x, y + h, z, wood.fence or "spruce_fence")
        top = y + height
        scene.set(x, top, z, wood.fence or "spruce_fence")
        arms = [facing] if style == "post" else [facing, OPP[facing]]
        for a in arms:
            dx, dz = DIRS[a]
            scene.set(x + dx, top, z + dz, wood.fence or "spruce_fence")
            scene.set(x + dx, top - 1, z + dz, T.lamp_hanging)
        scene.set(x, top + 1, z, f"{wood.slab or 'spruce_slab'}[type=bottom]")
    elif style == "pillar":
        for h in range(height - 1):
            scene.set(x, y + h, z, trim.wall or "stone_brick_wall")
        scene.set(x, y + height - 1, z, T.lamp)
    elif style == "stone_lantern":
        # tōrō: base, post, fire box with lantern, roof cap
        scene.set(x, y, z, "stone_brick_wall")
        scene.set(x, y + 1, z, "stone_brick_wall")
        scene.set(x, y + 2, z, "polished_andesite")
        scene.set(x, y + 3, z, "lantern")
        for d, (dx, dz) in DIRS.items():
            scene.set(x + dx, y + 3, z + dz, "stone_brick_wall")
        scene.set(x, y + 4, z, "polished_andesite_slab[type=bottom]")
        for d, (dx, dz) in DIRS.items():
            scene.set(x + dx, y + 4, z + dz, f"stone_brick_stairs[facing={OPP[d]}]")
        scene.set(x, y + 5, z, "stone_brick_wall")
    elif style == "brazier":
        scene.set(x, y, z, "polished_blackstone_wall")
        scene.set(x, y + 1, z, "polished_blackstone_wall")
        scene.set(x, y + 2, z, "soul_campfire[lit=true]" if T.name == "dark_infernal" else "campfire[lit=true]")
        for d, (dx, dz) in DIRS.items():
            scene.set(x + dx, y + 2, z + dz, f"polished_blackstone_stairs[facing={OPP[d]},half=top]")
    else:
        raise ValueError(f"unknown lamp style '{style}'")


def bench(scene, at, facing: str = "south", length: int = 3, *, theme=None) -> None:
    """Bench of stairs with trapdoor/sign armrests. ``facing`` = direction the sitter looks."""
    T = _theme(theme)
    wood = _fam(scene, T.wood_trim)
    x, y, z = (int(v) for v in at)
    y += 1
    rx, rz = (DIRS["east"] if facing in ("north", "south") else DIRS["south"])
    for i in range(length):
        scene.set(x + rx * i, y, z + rz * i, f"{wood.stairs}[facing={OPP[facing]}]")
    along_x = rx != 0
    for side in (-1, length):
        outward = ("east" if side == length else "west") if along_x else ("south" if side == length else "north")
        scene.set(x + rx * side, y, z + rz * side, f"{T.trapdoor}[facing={outward},open=true]")


def fountain(scene, at, radius: float = 4.0, *, theme=None, tiers: int = 2, liquid: str | None = None,
             centerpiece: str | None = None, lit: bool = True, material: str | None = None) -> Mask:
    """Round fountain standing on the ground block ``at``: a pool with a raised rim you can sit on
    (a step all around), a pedestal with bowls and four spouts falling into the pool, lights under
    the water (``lit``). ``centerpiece`` on top: None (water) | "crystal" (amethyst) | "lamp" | a block.
    ``material``: rim and bowls (a block with stairs and slabs, e.g. "smooth_quartz" to stand out
    against grey stone); default the theme trim."""
    T = _theme(theme)
    cx, gy, cz = at[0] + 0.5, int(at[1]), at[2] + 0.5
    liquid = liquid or T.liquid
    trim = _fam(scene, material or T.trim)
    dark = _fam(scene, getattr(T, "trim_dark", "") or T.trim)
    R = float(radius)
    disc = lambda rr, y: shapes.circle((cx, y, cz), rr, filled=True)  # noqa: E731
    pool = disc(R - 1.0, gy)
    rim = disc(R, gy) - pool
    step = disc(R + 1.0, gy + 1) - disc(R, gy + 1)
    scene.put(pool.below(1), dark.base)
    scene.put(pool.below(2), trim.base)
    scene.put(pool, liquid)
    scene.put(pool.above(1), liquid)
    scene.put(rim, trim.base)
    scene.put(rim.above(1), trim.base)
    scene.put(rim.above(2), f"{trim.slab}[type=bottom]" if trim.slab else trim.base)
    for (x, y, z) in step.points().tolist():
        if trim.stairs and scene.get(x, y, z) == "minecraft:air":
            scene.set(x, y, z, f"{trim.stairs}[facing={_face_to(x + 0.5, z + 0.5, cx, cz)},half=bottom]")
    if lit:
        for k in range(6):
            a = 2 * math.pi * k / 6
            lx, lz = int(math.floor(cx + math.cos(a) * (R - 2.2))), int(math.floor(cz + math.sin(a) * (R - 2.2)))
            scene.set(lx, gy - 1, lz, "sea_lantern")
    # pedestal with bowls; four spouts fall from the lowest bowl into the pool
    col_x, col_z = int(math.floor(cx)), int(math.floor(cz))
    y = gy + 2
    r = max(1.6, R * 0.5)
    for t in range(max(1, tiers)):
        for k in range(2):
            scene.set(col_x, y + k, col_z, dark.wall or dark.base)
        y += 2
        bowl = disc(r, y)
        edge = bowl - disc(r - 1.0, y)
        scene.put(bowl, trim.base)
        if trim.stairs:
            for (x, yy, z) in edge.points().tolist():
                scene.set(x, yy, z, f"{trim.stairs}[facing={_face_to(x + 0.5, z + 0.5, cx, cz)},half=top]")
        inner = disc(r - 1.0, y + 1)
        rim_up = disc(r, y + 1) - inner
        scene.put(inner, liquid)
        scene.put(rim_up, f"{trim.slab}[type=bottom]" if trim.slab else trim.base)
        if t == 0 and liquid == "water":
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                sx, sz = col_x + dx * int(round(r + 0.5)), col_z + dz * int(round(r + 0.5))
                for yy in range(y, gy + 1, -1):
                    if scene.get(sx, yy, sz) == "minecraft:air":
                        scene.set(sx, yy, sz, "water[level=8]")
        y += 1
        r = max(1.0, r * 0.6)
    scene.set(col_x, y, col_z, dark.wall or dark.base)
    top = y + 1
    if centerpiece == "crystal":
        scene.set(col_x, top, col_z, "amethyst_block")
        scene.set(col_x, top + 1, col_z, "amethyst_cluster[facing=up]")
    elif centerpiece == "lamp":
        scene.set(col_x, top, col_z, T.lamp)
    elif centerpiece:
        scene.put((col_x, top, col_z), centerpiece)
    else:
        scene.set(col_x, top, col_z, liquid)
    return rim | pool


def _face_to(x, z, cx, cz) -> str:
    dx, dz = cx - x, cz - z
    if abs(dx) > abs(dz):
        return "east" if dx > 0 else "west"
    return "south" if dz > 0 else "north"

def well(scene, at, *, theme=None) -> None:
    T = _theme(theme)
    x, y, z = (int(v) for v in at)
    trim = _fam(scene, T.trim)
    wood = _fam(scene, T.wood_trim)
    for dx in range(-1, 2):
        for dz in range(-1, 2):
            scene.set(x + dx, y + 1, z + dz, trim.base if (dx or dz) else "water")
            scene.set(x + dx, y, z + dz, trim.base if (dx or dz) else "water")
    for dx, dz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        scene.set(x + dx, y + 2, z + dz, wood.fence)
        scene.set(x + dx, y + 3, z + dz, wood.fence)
    for dx in range(-1, 2):
        for dz in range(-1, 2):
            scene.set(x + dx, y + 4, z + dz, f"{wood.stairs}[facing={'north' if dz > 0 else 'south'}]" if dz else
                      f"{wood.slab}[type=bottom]")
    scene.set(x, y + 3, z, "chain")
    scene.set(x, y + 2, z, "lantern[hanging=true]")


def market_stall(scene, at, facing: str = "south", *, theme=None, color: str = "red") -> None:
    """3x3 stall: counter, posts, striped wool awning, barrels."""
    T = _theme(theme)
    x, y, z = (int(v) for v in at)
    y += 1
    wood = _fam(scene, T.wood_trim)
    dx, dz = DIRS[facing]
    rx, rz = (1, 0) if facing in ("north", "south") else (0, 1)
    for i in range(-1, 2):
        cxp, czp = x + rx * i + dx, z + rz * i + dz
        scene.set(cxp, y, czp, "barrel[facing=up]" if i == 0 else f"{wood.slab}[type=top]")
    for i in (-2, 2):
        for h in range(3):
            scene.set(x + rx * i + dx, y + h, z + rz * i + dz, wood.fence)
            scene.set(x + rx * i - dx, y + h, z + rz * i - dz, wood.fence)
    for i in range(-2, 3):
        for j in (-1, 0, 1):
            col = f"{color}_wool" if (i + 10) % 2 == 0 else "white_wool"
            scene.set(x + rx * i + dx * j, y + 3, z + rz * i + dz * j, col)
    scene.set(x - dx, y, z - dz, "barrel[facing=up]")
    scene.set(x + rx - dx, y, z + rz - dz, "composter[level=8]")


TEXT_COLOR = {"red": "red", "lime": "green", "green": "dark_green", "light_blue": "aqua", "cyan": "dark_aqua",
              "blue": "blue", "yellow": "yellow", "orange": "gold", "purple": "dark_purple", "magenta": "light_purple",
              "pink": "light_purple", "white": "white", "light_gray": "gray", "gray": "gray", "black": "dark_gray",
              "brown": "gold"}


def portal_frame(scene, at, facing: str = "south", *, width: int = 5, height: int = 7, theme=None,
                 inner: str = "nether_portal", frame=None, label: str | None = None, color: str | None = None,
                 subtitle: str | None = None) -> Mask:
    """Game-mode portal: stone gate with piers, a round arch with dark voussoirs and a gold keystone,
    capitals, cornice, lanterns, mode-colored banners and a hologram label. Players walk in from
    ``facing``. inner: nether_portal | none | <any block> (a nether portal sends players to the Nether
    unless a portal plugin catches them or allow-nether=false). color: mode color (banner color name).
    """
    T = _theme(theme)
    x0, y0, z0 = (int(v) for v in at)
    by = y0 + 1
    fdx, fdz = DIRS[facing]
    udx, udz = -fdz, fdx
    ax = "x" if facing in ("north", "south") else "z"
    wall = frame or T.wall
    dark = _fam(scene, getattr(T, "trim_dark", "") or T.trim)
    trim = _fam(scene, T.trim)
    color = color or "red"
    half = max(1, width // 2)
    R = half + 0.5
    spring = max(2, height - (half + 1))
    top = height + 1  # v of the cornice row

    def P(u, v, n):
        return (x0 + udx * u + fdx * n, by + v, z0 + udz * u + fdz * n)

    def is_open(u, v):
        if abs(u) > half or v < 0:
            return False
        if v < spring:
            return True
        return u * u + (v - spring + 0.5) ** 2 <= R * R

    def outward(n):
        return facing if n > 0 else OPP[facing]

    cells = []
    for u in range(-half - 2, half + 3):
        for v in range(0, top):
            if is_open(u, v):
                continue
            ring = (not is_open(u, v)) and abs(u) <= half + 1 and v >= spring - 1 and \
                u * u + (v - spring + 0.5) ** 2 <= (R + 1.3) ** 2
            for n in (-1, 0, 1):
                p = P(u, v, n)
                block = dark.base if ring and n != 0 else wall
                scene.put(p, block)
                cells.append(p)
    # inner surface
    for u in range(-half, half + 1):
        for v in range(0, height + 1):
            if is_open(u, v):
                p = P(u, v, 0)
                if inner == "nether_portal":
                    scene.set(*p, f"nether_portal[axis={ax}]")
                elif inner and inner != "none":
                    scene.put(p, inner)
                for n in (-1, 1):
                    scene.set(*P(u, v, n), "air")
    # keystone on both faces
    kv = next(v for v in range(height + 1, spring - 1, -1) if not is_open(0, v) and is_open(0, v - 1))
    for n in (-1, 1):
        scene.put(P(0, kv, n), T.accent)
    # pier plinths and capitals (stairs on the outer faces)
    for u in (-half - 2, -half - 1, half + 1, half + 2):
        for n in (-1, 1):
            if dark.stairs:
                scene.set(*P(u, 0, n * 2), f"{dark.stairs}[facing={OPP[outward(n)]},half=bottom]")
                scene.set(*P(u, spring - 1, n * 2), f"{dark.stairs}[facing={OPP[outward(n)]},half=top]")
    for u in (-half - 3, half + 3):
        side = "east" if (udx, udz) == (1, 0) else "west" if (udx, udz) == (-1, 0) else \
            "south" if (udx, udz) == (0, 1) else "north"
        if u < 0:
            side = OPP[side]
        for n in (-1, 0, 1):
            if dark.stairs:
                scene.set(*P(u, 0, n), f"{dark.stairs}[facing={OPP[side]},half=bottom]")
    # cornice: slabs on top, upside-down stairs sticking out front and back
    for u in range(-half - 2, half + 3):
        for n in (-1, 0, 1):
            scene.put(P(u, top, n), trim.base)
            if dark.slab:
                scene.set(*P(u, top + 1, n), f"{dark.slab}[type=bottom]")
        for n in (-2, 2):
            if dark.stairs:
                scene.set(*P(u, top, n), f"{dark.stairs}[facing={OPP[outward(n)]},half=top]")
    # lanterns on the ends of the cornice and banners on the piers
    for u in (-half - 2, half + 2):
        scene.set(*P(u, top + 2, 0), T.lamp)
        for n in (-1, 1):
            bp = P(u, spring - 2, n * 2)
            scene.set(*bp, f"{color}_wall_banner[facing={outward(n)}]")
    if label:
        from .entities import component, hologram

        lines = [component(label, TEXT_COLOR.get(color, "white"), bold=True)]
        if subtitle:
            lines.append(component(subtitle, "gray"))
        hx, hy, hz = P(0, top + 2, 0)
        hologram(scene, (hx + 0.5, hy + 0.9, hz + 0.5), lines, billboard="center", scale=1.4)
    return Mask.from_points(cells)

def banner_pole(scene, at, *, color: str = "red", height: int = 6, theme=None, facing: str = "south") -> None:
    T = _theme(theme)
    x, y, z = (int(v) for v in at)
    y += 1
    wood = _fam(scene, T.wood_trim)
    for h in range(height):
        scene.set(x, y + h, z, wood.fence or "spruce_fence")
    dx, dz = DIRS[facing]
    scene.set(x + dx, y + height - 1, z + dz, f"{color}_wall_banner[facing={facing}]")
    scene.set(x, y + height, z, T.lamp)


def planter(scene, at, size: int = 3, *, theme=None, flowers=None) -> None:
    """Raised flower bed with a trim border."""
    T = _theme(theme)
    x, y, z = (int(v) for v in at)
    trim = _fam(scene, T.trim)
    fl = flowers or T.flowers or ["poppy"]
    for dx in range(size):
        for dz in range(size):
            border = dx in (0, size - 1) or dz in (0, size - 1)
            if border:
                scene.set(x + dx, y + 1, z + dz, f"{trim.slab}[type=top]" if trim.slab else trim.base)
            else:
                scene.set(x + dx, y + 1, z + dz, "moss_block" if T.name != "dark_infernal" else "soul_soil")
                scene.set(x + dx, y + 2, z + dz, fl[(dx * 3 + dz) % len(fl)])
