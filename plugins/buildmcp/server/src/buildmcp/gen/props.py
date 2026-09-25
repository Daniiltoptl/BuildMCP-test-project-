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


def fountain(scene, at, radius: float = 4.0, *, theme=None, tiers: int = 2, liquid: str | None = None) -> Mask:
    """Round tiered fountain with a basin rim and a central spout."""
    T = _theme(theme)
    cx, cy, cz = at[0] + 0.5, int(at[1]) + 1, at[2] + 0.5
    liquid = liquid or T.liquid
    trim = _fam(scene, T.trim)
    basin = shapes.circle((cx, cy, cz), radius)
    rim = shapes.ring((cx, cy, cz), radius, radius - 1.2)
    scene.put(basin.below(1), T.wall_base)
    scene.put(basin - rim, liquid)
    scene.put(rim, trim.base)
    scene.put(rim.above(1), f"{trim.slab}[type=bottom]" if trim.slab else trim.base)
    # central column + upper bowls
    col_h = 2 + tiers * 2
    for h in range(col_h):
        scene.set(int(cx), cy + h, int(cz), trim.wall or trim.base)
    r = radius * 0.5
    y = cy + 2
    for t in range(tiers):
        bowl = shapes.circle((cx, y, cz), r)
        ring = shapes.ring((cx, y, cz), r, r - 1.0)
        scene.put(bowl, trim.base)
        scene.put(ring.above(1), f"{trim.slab}[type=bottom]" if trim.slab else trim.base)
        scene.put((bowl - ring).above(1), liquid)
        y += 2
        r = max(1.0, r * 0.55)
    scene.set(int(cx), cy + col_h, int(cz), liquid)
    return basin


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


def portal_frame(scene, at, facing: str = "south", *, width: int = 5, height: int = 7, theme=None,
                 inner: str = "nether_portal", frame=None, label: str | None = None) -> Mask:
    """Game-mode portal: framed arch facing ``facing`` (players walk in from that side).
    inner: nether_portal | end_gateway | <any glass/block>. Adds a pedestal spot for an NPC and a hologram."""
    T = _theme(theme)
    x, y, z = (int(v) for v in at)
    y += 1
    ax = "x" if facing in ("north", "south") else "z"
    frame = frame or T.wall
    trim = _fam(scene, T.trim)
    cells = []
    half = width // 2
    for o in range(-half - 1, half + 2):
        for h in range(height + 2):
            edge = abs(o) == half + 1 or h == 0 or h == height + 1
            p = (x + o, y + h - 1, z) if ax == "x" else (x, y + h - 1, z + o)
            if edge:
                scene.put(p, frame)
                cells.append(p)
            elif h >= 1:
                if inner == "nether_portal":
                    scene.set(*p, f"nether_portal[axis={ax}]")
                else:
                    scene.set(*p, inner)
    # crown on top and side pillars
    for o in (-half - 2, half + 2):
        for h in range(height + 2):
            p = (x + o, y + h - 1, z) if ax == "x" else (x, y + h - 1, z + o)
            scene.set(*p, trim.wall or trim.base)
    top = y + height + 1
    for o in range(-half - 1, half + 2):
        p = (x + o, top, z) if ax == "x" else (x, top, z + o)
        scene.set(*p, f"{trim.stairs}[facing={facing},half=bottom]" if abs(o) != 0 else T.lamp)
    if label:
        from .entities import hologram

        hx, hz = (x + 0.5, z + 0.5)
        hologram(scene, (hx, top + 1.3, hz), [label], billboard="center")
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
