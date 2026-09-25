"""Paths, plazas, stairs on slopes, bridges.

    paths.path(S, [(0, 80, 0), (20, 81, 10), (40, 80, 5)], width=5, theme=T)
    paths.plaza(S, (0, 80, 0), radius=9, theme=T, pattern="rings")
"""

from __future__ import annotations

import math

import numpy as np

from ..blocks import families as F
from ..geo import shapes
from ..geo.box import Box
from ..geo.mask import Mask, as_mask
from ..paint import palette as P
from ..paint.noise import fbm, hash01
from .. import themes as themes_mod


def _theme(theme):
    if theme is None:
        return themes_mod.get("fantasy_medieval")
    return themes_mod.get(theme) if isinstance(theme, str) else theme


def path(scene, points, width: float = 4.0, *, theme=None, palette=None, edge=None, edge_width: float = 1.2,
         follow_ground: bool = True, clear_above: int = 3, seed: int = 0) -> Mask:
    """Paint a path along a smooth curve through ``points`` (x, y, z).

    follow_ground: snap to the existing top surface of each column (else use the curve height).
    edge: palette blended at the borders (default: the theme soil) for a natural transition.
    Plants and ground cover above the path are cleared.
    """
    T = _theme(theme)
    pal = palette or T.path
    edge_pal = edge if edge is not None else P.Mix([T.soil, T.grass], cluster=2, seed=seed + 3)
    band = shapes.corridor(points, width + 2 * edge_width)
    core = shapes.corridor(points, width)
    cells_core = []
    cells_edge = []
    for (x, y, z) in band.points().tolist():
        gy = scene.top_y(x, z, "!#air|!#plants|!#replaceable") if follow_ground else y
        if gy is None:
            continue
        if follow_ground and abs(gy - y) > 6:
            continue
        in_core = core.contains((x, y, z)) if not follow_ground else any(core.contains((x, yy, z)) for yy in range(y - 1, y + 2))
        # jagged, noisy edge
        n = hash01(x, gy, z, seed + 5)
        if in_core or (n < 0.35):
            cells_core.append((x, gy, z))
        elif n < 0.7:
            cells_edge.append((x, gy, z))
    if cells_core:
        m = Mask.from_points(cells_core)
        scene.put(m, pal)
        if clear_above:
            for k in range(1, clear_above + 1):
                scene.put(m.above(k), "air", only="#plants|#replaceable|!#liquid|!#air")
    if cells_edge:
        scene.put(Mask.from_points(cells_edge), edge_pal)
        scene.put(Mask.from_points(cells_edge).above(1), "air", only="#plants|snow")
    return Mask.from_points(cells_core) if cells_core else Mask.empty()


def plaza(scene, center, radius: float, *, theme=None, palette=None, pattern: str = "rings", y: int | None = None,
          border=None, level: bool = True, seed: int = 0) -> Mask:
    """Round paved plaza. pattern: rings | radial | checker | plain. ``level`` flattens terrain to y."""
    T = _theme(theme)
    cx, cy, cz = (float(v) for v in center)
    yy = int(cy) if y is None else int(y)
    disc = shapes.circle((cx, yy, cz), radius)
    if level:
        for (x, _, z) in disc.points().tolist():
            top = scene.top_y(x, z)
            if top is not None and top > yy:
                scene.put(Box(x, yy + 1, z, x, top + 2, z), "air")
            for fy in range(yy - 1, yy - 4, -1):
                if scene.get(x, fy, z) == "minecraft:air":
                    scene.set(x, fy, z, "minecraft:stone")
    pal = palette or T.plaza
    if pattern == "rings":
        trim = F.family(scene.reg, T.trim).base if isinstance(T.trim, str) else "polished_andesite"
        accent = "polished_andesite" if T.name != "dark_infernal" else "polished_blackstone"
        pal = P.field(lambda x, yv, z: ((np.hypot(x + 0.5 - cx, z + 0.5 - cz) // 3) % 2) * 0.99, [pal, accent], jitter=0.0)
    elif pattern == "radial":
        pal = P.field(lambda x, yv, z: (((np.degrees(np.arctan2(z + 0.5 - cz, x + 0.5 - cx)) + 360) // 22.5) % 2) * 0.99,
                      [pal, T.wall_base], jitter=0.0)
    elif pattern == "checker":
        pal = P.checker(pal, T.wall_base, size=2)
    scene.put(disc, pal)
    rim = shapes.ring((cx, yy, cz), radius, radius - 1.2)
    scene.put(rim, border or T.wall_base)
    scene.put(disc.above(1), "air", only="#plants|#replaceable|!#liquid|!#air")
    return disc


def steps(scene, start, end, width: int = 3, *, material: str | None = None, theme=None) -> Mask:
    """A straight staircase from ``start`` (bottom) to ``end`` (top), ``width`` wide, with solid fill below."""
    T = _theme(theme)
    fam = F.family(scene.reg, material or T.trim)
    stairs = fam.stairs or "stone_brick_stairs"
    sx, sy, sz = (int(v) for v in start)
    ex, ey, ez = (int(v) for v in end)
    rise = ey - sy
    if rise <= 0:
        raise ValueError("end must be higher than start")
    dx, dz = ex - sx, ez - sz
    if abs(dx) >= abs(dz):
        facing = "east" if dx > 0 else "west"
        step = (1 if dx > 0 else -1, 0)
    else:
        facing = "south" if dz > 0 else "north"
        step = (0, 1 if dz > 0 else -1)
    perp = (step[1], step[0])
    cells = []
    for i in range(rise):
        bx = sx + step[0] * i
        bz = sz + step[1] * i
        by = sy + i
        for w in range(width):
            px = bx + perp[0] * (w - width // 2)
            pz = bz + perp[1] * (w - width // 2)
            scene.set(px, by, pz, f"{stairs}[facing={facing}]")
            for fy in range(by - 1, sy - 2, -1):
                if scene.get(px, fy, pz) in ("minecraft:air",):
                    scene.set(px, fy, pz, fam.base)
            cells.append((px, by, pz))
    return Mask.from_points(cells)


def bridge(scene, a, b, width: int = 3, *, theme=None, arch: float = 2.0, deck=None, rail=None,
           style: str = "stone") -> Mask:
    """Arched bridge between two points (x, y, z) at deck level. style: stone | wood | asian."""
    T = _theme(theme)
    pa = np.asarray(a, float)
    pb = np.asarray(b, float)
    L = float(np.linalg.norm(pb[[0, 2]] - pa[[0, 2]]))
    n = max(2, int(L * 2))
    dirv = (pb - pa)
    dirv[1] = 0
    dirv /= (np.linalg.norm(dirv) or 1)
    perp = np.array([-dirv[2], 0, dirv[0]])
    deck_pal = deck or ({"wood": T.floor, "asian": "dark_oak_planks"}.get(style, T.plaza))
    rail_blk = rail or ({"wood": T.fence, "asian": "mangrove_fence"}.get(style, T.railing))
    cells = []
    rails = []
    for i in range(n + 1):
        t = i / n
        p = pa + (pb - pa) * t
        lift = arch * math.sin(math.pi * t)
        y = int(round(p[1] + lift))
        for w in range(-(width // 2), width // 2 + 1):
            q = p + perp * w
            cells.append((int(math.floor(q[0])), y, int(math.floor(q[2]))))
        for side in (-(width // 2) - 1, width // 2 + 1):
            q = p + perp * side
            rails.append((int(math.floor(q[0])), y, int(math.floor(q[2]))))
    deck_m = Mask.from_points(cells)
    scene.put(deck_m, deck_pal)
    rail_m = Mask.from_points(rails) - deck_m
    scene.put(rail_m, P.mix({T.wall_base if style == "stone" else deck_pal: 1}) if style == "stone" else deck_pal)
    scene.put(rail_m.above(1), rail_blk)
    if style == "stone":
        # support arch underneath
        under = deck_m.below(1) | deck_m.below(2).where(lambda x, y, z: hash01(x, y, z, 3) < 0.5)
        scene.put(under, T.wall_base, only="#air")
    return deck_m
