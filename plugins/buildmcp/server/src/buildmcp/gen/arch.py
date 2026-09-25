"""Architecture: roofs, walls with depth, windows, doors, towers, arches, columns, houses,
pagodas, torii gates. Everything takes a ``theme`` for materials.

Box convention for buildings: (x1, y1, z1, x2, y2, z2) where y1 is the floor level and
y2 the top of the walls (the roof sits on top). Facing = the direction a side looks out.
"""

from __future__ import annotations

import math

import numpy as np

from ..blocks import families as F
from ..geo import sdf, shapes
from ..geo.box import Box
from ..geo.mask import Mask, as_mask
from ..paint import palette as P
from ..paint.noise import hash01
from .. import themes as themes_mod

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
# right-hand direction for someone outside looking at a wall that faces <key>
RIGHT_OF = {"north": "west", "south": "east", "east": "north", "west": "south"}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}
CW = {"north": "east", "east": "south", "south": "west", "west": "north"}


def _theme(theme):
    if theme is None:
        return themes_mod.get("fantasy_medieval")
    return themes_mod.get(theme) if isinstance(theme, str) else theme


def _fam(scene, base: str) -> F.Family:
    return F.family(scene.reg, base)


def _stairs_of(scene, base: str) -> str:
    return _fam(scene, base).stairs or "stone_brick_stairs"


def _slab_of(scene, base: str) -> str:
    return _fam(scene, base).slab or "stone_brick_slab"


def _wall_of(scene, base: str) -> str:
    return _fam(scene, base).wall or "cobblestone_wall"


# ======================================================================= roofs
def roof_heightfield(box: Box, style: str, pitch: float, overhang: int, axis: str | None) -> tuple[np.ndarray, int, int, str]:
    """Float roof heights (relative to the eave line) over the footprint expanded by the overhang."""
    x1, z1 = box.x1 - overhang, box.z1 - overhang
    x2, z2 = box.x2 + overhang, box.z2 + overhang
    xs = np.arange(x1, x2 + 1)
    zs = np.arange(z1, z2 + 1)
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    wx, wz = x2 - x1 + 1, z2 - z1 + 1
    if axis is None:
        axis = "x" if wx >= wz else "z"  # ridge runs along the longer side
    dx = np.minimum(X - x1, x2 - X).astype(float)  # distance from the west/east eaves
    dz = np.minimum(Z - z1, z2 - Z).astype(float)
    if style in ("gable", "nordic", "gothic"):
        d = dz if axis == "x" else dx
        h = d * pitch
    elif style in ("hip", "pyramid"):
        h = np.minimum(dx, dz) * pitch
    elif style == "asian":
        d = np.minimum(dx, dz)
        dmax = max(1.0, float(d.max()))
        t = d / dmax
        h = dmax * pitch * (t ** 1.35)  # concave: flat eaves, steep top
        # upturned corners: lift the eave where both distances are small
        corner = np.clip(1 - (dx + dz) / (0.9 * max(4.0, dmax)), 0, 1)
        h = h + 2.2 * corner ** 2
    elif style == "mansard":
        d = np.minimum(dx, dz)
        h = np.where(d < 3, d * 2.0, 6 + (d - 3) * 0.35)
    elif style == "flat":
        h = np.zeros_like(X, float)
    else:
        raise ValueError(f"unknown roof style '{style}'")
    return h, x1, z1, axis


def roof(scene, box, *, style: str | None = None, theme=None, material: str | None = None, accent: str | None = None,
         pitch: float | None = None, overhang: int = 1, axis: str | None = None, thickness: int = 1,
         gable_fill=None, trim: bool = True, seed: int = 0) -> Mask:
    """Roof on top of a building box. style: gable | hip | pyramid | asian | nordic | gothic | mansard | flat
    (default: theme roof_style). material: family base for the stairs/slabs (default theme.roof)."""
    T = _theme(theme)
    b = Box.of(box)
    style = style or T.roof_style
    if style == "nordic":
        pitch = pitch or 1.6
    elif style == "gothic":
        pitch = pitch or 2.0
    else:
        pitch = pitch or 1.0
    mat = material or T.roof
    fam = _fam(scene, mat)
    stairs = fam.stairs or _stairs_of(scene, "stone_bricks")
    slab = fam.slab or _slab_of(scene, "stone_bricks")
    full = fam.base
    acc_fam = _fam(scene, accent or T.roof_accent)
    h, x0, z0, axis = roof_heightfield(b, style, pitch, overhang, axis)
    eave_y = b.y2 + 1
    H = np.floor(h + 1e-6).astype(int) + eave_y  # top cell y per column
    nx, nz = H.shape
    placed = []
    for i in range(nx):
        for k in range(nz):
            x, z = x0 + i, z0 + k
            top = int(H[i, k])
            # find the up-slope neighbor
            best, best_dir = top, None
            for dname, (ddx, ddz) in DIRS.items():
                ii, kk = i + ddx, k + ddz
                if 0 <= ii < nx and 0 <= kk < nz and H[ii, kk] > best:
                    best, best_dir = int(H[ii, kk]), dname
            # shell below the top cell, deep enough to close steps towards lower neighbours
            nb_min = top
            for (ddx, ddz) in DIRS.values():
                ii, kk = i + ddx, k + ddz
                if 0 <= ii < nx and 0 <= kk < nz:
                    nb_min = min(nb_min, int(H[ii, kk]))
            low = min(top - thickness, nb_min)
            for y in range(low + 1, top):
                scene.set(x, y, z, full)
            if best_dir is not None and best - top == 1:
                scene.set(x, top, z, f"{stairs}[facing={best_dir},half=bottom]")
            elif best_dir is not None:
                # steep step: full block with a stair on top, so every riser is capped by a stair
                scene.set(x, top, z, full)
                scene.set(x, top + 1, z, f"{stairs}[facing={best_dir},half=bottom]")
            else:
                # ridge / flat top
                scene.set(x, top, z, slab if style not in ("flat", "mansard") else full)
            placed.append((x, top, z))
            # eave underside trim (upside-down stairs facing outwards at the overhang edge)
            on_edge = i == 0 or k == 0 or i == nx - 1 or k == nz - 1
            if trim and on_edge and top <= eave_y + 1:
                out_dir = "west" if i == 0 else "east" if i == nx - 1 else "north" if k == 0 else "south"
                below = scene.get(x, low, z)
                if below == "minecraft:air" and acc_fam.stairs:
                    scene.set(x, low, z, f"{acc_fam.stairs}[facing={OPP[out_dir]},half=top]")
    # gable ends: fill the triangle under the roof inside the wall line
    if style in ("gable", "nordic", "gothic"):
        fill = gable_fill or T.plaster
        ends = ("x",) if axis == "x" else ("z",)
        for i in range(nx):
            for k in range(nz):
                x, z = x0 + i, z0 + k
                if not (b.x1 <= x <= b.x2 and b.z1 <= z <= b.z2):
                    continue
                on_end = (axis == "x" and x in (b.x1, b.x2)) or (axis == "z" and z in (b.z1, b.z2))
                if on_end:
                    for y in range(b.y2 + 1, int(H[i, k]) - thickness + 1):
                        scene.put((x, y, z), fill, only="#air")
        # ridge ornaments for nordic roofs (crossed beams)
        if style == "nordic":
            ridge = int(H.max())
            for ex in (0, nx - 1) if axis == "x" else ():
                k = int(np.argmax(H[ex]))
                scene.set(x0 + ex, ridge + 1, z0 + k, acc_fam.fence or "spruce_fence")
            for ek in (0, nz - 1) if axis == "z" else ():
                i = int(np.argmax(H[:, ek]))
                scene.set(x0 + i, ridge + 1, z0 + ek, acc_fam.fence or "spruce_fence")
    if style == "asian":
        # ornaments on the lifted corners
        for (i, k) in ((0, 0), (0, nz - 1), (nx - 1, 0), (nx - 1, nz - 1)):
            x, z = x0 + i, z0 + k
            scene.set(x, int(H[i, k]) + 1, z, acc_fam.fence or acc_fam.wall or "dark_oak_fence")
    return Mask.from_points(placed)


def stairify(scene, where, material: str, *, only_top: bool = True) -> int:
    """Turn the stepped top surface of a solid (cone, dome, rock, sculpted roof) into stairs/slabs:
    each top cell with exactly one lower open side becomes a stair facing into the solid."""
    m = as_mask(where)
    fam = _fam(scene, material)
    stairs = fam.stairs
    slab = fam.slab
    if not stairs:
        return 0
    n = 0
    top = m.top()
    for (x, y, z) in top.points().tolist():
        open_dirs = [d for d, (dx, dz) in DIRS.items() if scene.get(x + dx, y, z + dz) == "minecraft:air"]
        if len(open_dirs) == 1:
            scene.set(x, y, z, f"{stairs}[facing={OPP[open_dirs[0]]}]")
            n += 1
        elif len(open_dirs) == 2 and OPP[open_dirs[0]] != open_dirs[1]:
            # outer corner: stair facing away from both open sides; finalize() makes the corner shape
            scene.set(x, y, z, f"{stairs}[facing={OPP[open_dirs[0]]}]")
            n += 1
        elif len(open_dirs) >= 3 and slab:
            scene.set(x, y, z, f"{slab}[type=bottom]")
            n += 1
    return n


def cone_roof(scene, center, radius: float, height: float | None = None, *, theme=None, material: str | None = None,
              base_y: int | None = None, overhang: float = 1.0, spire: bool = True) -> Mask:
    """Round tower roof (witch hat) with stairs smoothing and an optional spire."""
    T = _theme(theme)
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    by = int(cy) if base_y is None else int(base_y)
    r = radius + overhang
    hgt = height or r * 1.9
    cone = sdf.cone((cx, by, cz), hgt, r, 0.4).mask()
    mat = material or T.roof
    scene.put(cone, _fam(scene, mat).base)
    stairify(scene, cone, mat)
    if spire:
        top = by + int(hgt)
        for k in range(3):
            scene.set(int(math.floor(cx)), top + k, int(math.floor(cz)), _wall_of(scene, T.trim) if k < 2 else T.metal)
        scene.set(int(math.floor(cx)), top + 3, int(math.floor(cz)), "lightning_rod")
    return cone


def dome_roof(scene, center, radius: float, *, theme=None, material: str | None = None, base_y: int | None = None,
              height: float | None = None, onion: bool = False) -> Mask:
    T = _theme(theme)
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    by = int(cy) if base_y is None else int(base_y)
    if onion:
        prof = [(radius, 0), (radius * 1.15, radius * 0.5), (radius * 0.9, radius * 1.1), (radius * 0.35, radius * 1.6),
                (0.2, radius * 2.1)]
        m = sdf.lathe((cx, by, cz), prof).mask()
    else:
        m = sdf.dome((cx, by, cz), radius, height).mask()
    mat = material or T.roof
    scene.put(m, _fam(scene, mat).base)
    stairify(scene, m, mat)
    return m


# ======================================================================= walls
def _sides(b: Box):
    """(name, facing, cells list along the side at y=0, axis along)"""
    return [
        ("north", [(x, b.z1) for x in range(b.x1, b.x2 + 1)], "x"),
        ("south", [(x, b.z2) for x in range(b.x1, b.x2 + 1)], "x"),
        ("west", [(b.x1, z) for z in range(b.z1, b.z2 + 1)], "z"),
        ("east", [(b.x2, z) for z in range(b.z1, b.z2 + 1)], "z"),
    ]


def walls(scene, box, *, theme=None, style: str | None = None, fill=None, base=None, frame: str | None = None,
          pillar_every: int = 4, base_height: int = 1, beams: bool = True, plinth: bool = True,
          cornice: bool = True, seed: int = 0) -> Mask:
    """Four walls with depth: corner/interval pillars, inset panels, base course, beams, cornice.

    style: stone | timber (stone base + timber frame + plaster) | plaster | log | gothic (default by theme).
    """
    T = _theme(theme)
    b = Box.of(box)
    style = style or {"fantasy_medieval": "timber", "asian_sakura": "plaster", "dark_infernal": "gothic",
                      "winter_north": "log"}.get(T.name, "stone")
    frame = frame or T.frame
    fill = fill or {"timber": T.plaster, "plaster": T.wall, "log": T.wall, "gothic": T.wall}.get(style, T.wall)
    base = base or T.wall_base
    trim_fam = _fam(scene, T.trim)
    cells = []
    for name, line, axis in _sides(b):
        for idx, (x, z) in enumerate(line):
            corner = idx == 0 or idx == len(line) - 1
            pillar = corner or (pillar_every > 0 and idx % pillar_every == 0)
            for y in range(b.y1, b.y2 + 1):
                cells.append((x, y, z))
                if y < b.y1 + base_height:
                    scene.put((x, y, z), base)
                elif pillar:
                    if style in ("timber", "log", "plaster"):
                        scene.set(x, y, z, f"{frame}[axis=y]" if "log" in frame or "stem" in frame or "basalt" in frame
                                  else frame)
                    else:
                        scene.put((x, y, z), T.pillar if not isinstance(T.pillar, str) else T.pillar)
                else:
                    beam_row = beams and style in ("timber", "log") and (y == b.y2 or (y - b.y1) % 4 == 3)
                    if beam_row:
                        la = "x" if axis == "x" else "z"
                        scene.set(x, y, z, f"{frame}[axis={la}]" if ("log" in frame or "stem" in frame) else frame)
                    else:
                        scene.put((x, y, z), fill)
    # base plinth: stairs outside at ground level (sloping away from the wall)
    if plinth and trim_fam.stairs:
        for name, line, axis in _sides(b):
            dx, dz = DIRS[name]
            for (x, z) in line:
                px, pz = x + dx, z + dz
                if scene.get(px, b.y1, pz) == "minecraft:air":
                    scene.set(px, b.y1, pz, f"{trim_fam.stairs}[facing={OPP[name]}]")
    # cornice: upside-down stairs sticking out under the eave
    if cornice and trim_fam.stairs:
        for name, line, axis in _sides(b):
            dx, dz = DIRS[name]
            for (x, z) in line:
                px, pz = x + dx, z + dz
                if scene.get(px, b.y2, pz) == "minecraft:air":
                    scene.set(px, b.y2, pz, f"{trim_fam.stairs}[facing={OPP[name]},half=top]")
    return Mask.from_points(cells)


def window(scene, pos, facing: str, *, width: int = 1, height: int = 2, theme=None, style: str = "shutters",
           glass: str | None = None) -> None:
    """Window in a wall. ``pos`` = bottom-left wall cell (as seen from outside), ``facing`` = outward direction.
    style: plain | shutters | arched | slit | flowerbox."""
    T = _theme(theme)
    x, y, z = (int(v) for v in pos)
    dx, dz = DIRS[facing]
    rx, rz = DIRS[RIGHT_OF[facing]]
    glass = glass or T.window
    trim_fam = _fam(scene, T.trim)
    wood_fam = _fam(scene, T.wood_trim)
    if style == "slit":
        width, height = 1, max(2, height)
    for w in range(width):
        for h in range(height):
            gx, gz = x + rx * w, z + rz * w
            if style == "slit":
                scene.set(gx, y + h, gz, "iron_bars" if T.name != "asian_sakura" else glass)
            else:
                scene.set(gx, y + h, gz, glass)
    # sill below (outside) and lintel above
    for w in range(-1 if style != "slit" else 0, width + (1 if style != "slit" else 0)):
        gx, gz = x + rx * w + dx, z + rz * w + dz
        if trim_fam.stairs and style != "slit":
            scene.set(gx, y - 1, gz, f"{trim_fam.stairs}[facing={OPP[facing]},half=top]")
        if style == "arched" and 0 <= w < width:
            scene.set(x + rx * w, y + height, z + rz * w, f"{trim_fam.stairs}[facing={facing},half=top]"
                      if width > 1 else glass)
        elif style != "slit" and trim_fam.slab:
            scene.set(gx, y + height, gz, f"{trim_fam.slab}[type=top]" if 0 <= w < width else
                      f"{trim_fam.stairs}[facing={OPP[facing]},half=top]")
    if style in ("shutters", "flowerbox"):
        tr = T.trapdoor
        for side, off in (("left", -1), ("right", width)):
            sx, sz = x + rx * off + dx, z + rz * off + dz
            for h in range(height):
                if scene.get(sx, y + h, sz) == "minecraft:air":
                    scene.set(sx, y + h, sz, f"{tr}[facing={facing},open=true,half=bottom]")
    if style == "flowerbox":
        planter_soil = "moss_block" if T.name != "dark_infernal" else "soul_soil"
        for w in range(width):
            fx, fz = x + rx * w + dx, z + rz * w + dz
            scene.set(fx, y - 1, fz, planter_soil)
            flower = T.flowers[w % len(T.flowers)] if T.flowers else "poppy"
            scene.set(fx, y, fz, flower)
            scene.set(fx + dx, y - 1, fz + dz, f"{T.trapdoor}[facing={facing},open=true,half=bottom]")


def door(scene, pos, facing: str, *, theme=None, width: int = 1, lamps: bool = True, awning: bool = True) -> None:
    """Door opening at ``pos`` (bottom cell in the wall) facing outward; frame, lanterns, awning."""
    T = _theme(theme)
    x, y, z = (int(v) for v in pos)
    dx, dz = DIRS[facing]
    rx, rz = DIRS[RIGHT_OF[facing]]
    for w in range(width):
        scene.set(x + rx * w, y, z + rz * w, f"{T.door}[facing={OPP[facing]},half=lower,hinge={'left' if w == 0 else 'right'}]")
        scene.set(x + rx * w, y + 1, z + rz * w, f"{T.door}[facing={OPP[facing]},half=upper,hinge={'left' if w == 0 else 'right'}]")
    frame = T.frame
    for h in range(0, 3):
        for side in (-1, width):
            fx, fz = x + rx * side, z + rz * side
            scene.set(fx, y + h, fz, f"{frame}[axis=y]" if ("log" in frame or "stem" in frame or "basalt" in frame) else frame)
    for w in range(-1, width + 1):
        la = "x" if rx != 0 else "z"
        scene.set(x + rx * w, y + 2, z + rz * w, f"{frame}[axis={la}]" if ("log" in frame or "stem" in frame) else frame)
    if lamps:
        # a short post on each side of the door with a lantern on top
        for side in (-1, width):
            lx, lz = x + rx * side + dx, z + rz * side + dz
            if scene.get(lx, y, lz) == "minecraft:air":
                scene.set(lx, y, lz, _wall_of(scene, T.trim))
            if scene.get(lx, y + 1, lz) == "minecraft:air":
                scene.set(lx, y + 1, lz, T.lamp)
    if awning:
        wood = _fam(scene, T.wood_trim)
        for w in range(-1, width + 1):
            ax, az = x + rx * w + dx, z + rz * w + dz
            if wood.stairs:
                scene.set(ax, y + 3, az, f"{wood.stairs}[facing={OPP[facing]}]")
    # clear a landing outside
    for w in range(width):
        scene.put((x + rx * w + dx, y, z + rz * w + dz), "air", only="#plants|snow")


# ======================================================================= towers
def tower(scene, center, radius: float, height: int, *, theme=None, shape: str = "round", roof: str = "cone",
          windows: bool = True, band_every: int = 6, buttresses: int = 0, material=None, seed: int = 0) -> Mask:
    """Tower standing on ``center`` (x, ground y, z). shape: round | square | octagon.
    roof: cone | dome | onion | battlements | pyramid | asian | none."""
    T = _theme(theme)
    cx, cy, cz = float(center[0]) + 0.5, int(center[1]), float(center[2]) + 0.5
    r = float(radius)
    mat = material or T.wall
    trim = _fam(scene, T.trim)
    cells = []

    def footprint(rr: float, y: int, filled: bool):
        if shape == "round":
            return shapes.circle((cx, y, cz), rr, filled=filled, thickness=1.2)
        sides = 4 if shape == "square" else 8
        rot = 45 if shape == "square" else 22.5
        return shapes.polygon(shapes.regular_polygon((cx, cz), rr / (math.cos(math.pi / sides) if shape == "square" else 1), sides, rot),
                              y, filled=filled)

    # base flare (slightly wider bottom)
    for y in range(cy, cy + height):
        flare = 1.0 if y - cy < 2 else 0.0
        ring = footprint(r + flare, y, filled=False)
        inner = footprint(r + flare - 1.2, y, filled=True)
        wall = ring | (footprint(r + flare, y, True) - inner)
        pal = T.wall_base if y - cy < 3 else mat
        scene.put(wall, pal)
        cells.extend(wall.points().tolist())
        scene.put(inner, "air")
        if y == cy:
            scene.put(inner, T.floor)
    # trim bands (upside-down stairs ring facing inward = sticking out)
    for y in range(cy + band_every, cy + height, band_every):
        ring = footprint(r + 1, y, filled=False)
        _stair_ring(scene, ring, cx, cz, trim.stairs, half="top")
    top_y = cy + height
    # machicolation corbels + parapet
    ring = footprint(r + 1, top_y - 1, filled=False)
    _stair_ring(scene, ring, cx, cz, trim.stairs, half="top")
    if roof == "battlements":
        disc = footprint(r + 1, top_y, filled=True)
        scene.put(disc, T.floor if T.floor else mat)
        edge = footprint(r + 1, top_y + 1, filled=False)
        for i, (x, y, z) in enumerate(sorted(edge.points().tolist(), key=lambda p: math.atan2(p[2] - cz, p[0] - cx))):
            scene.put((x, y, z), mat)
            if i % 2 == 0:
                scene.put((x, y + 1, z), mat)
    elif roof in ("cone", "asian"):
        scene.put(footprint(r + 1, top_y, filled=True), mat)
        cone_roof(scene, (cx, top_y + 1, cz), r, theme=T, overhang=1.0 if roof == "cone" else 2.0)
    elif roof in ("dome", "onion"):
        scene.put(footprint(r + 1, top_y, filled=True), mat)
        dome_roof(scene, (cx, top_y + 1, cz), r + 0.5, theme=T, onion=roof == "onion")
    elif roof == "pyramid":
        rb = Box(int(cx - r - 1), top_y - 1, int(cz - r - 1), int(cx + r), top_y - 1, int(cz + r))
        globals()["roof"](scene, rb, style="hip", theme=T, overhang=1)
    if windows:
        rng = np.random.default_rng(seed)
        for y in range(cy + 4, cy + height - 3, 5):
            for k in range(4):
                a = k * math.pi / 2 + (y // 5) * 0.4
                wx = int(math.floor(cx + math.cos(a) * r))
                wz = int(math.floor(cz + math.sin(a) * r))
                for h in range(2):
                    scene.set(wx, y + h, wz, T.window if T.name != "fantasy_medieval" else "glass_pane")
    if buttresses:
        for k in range(buttresses):
            a = 2 * math.pi * k / buttresses
            bx = cx + math.cos(a) * (r + 1)
            bz = cz + math.sin(a) * (r + 1)
            for y in range(cy, cy + int(height * 0.35)):
                scene.put((int(math.floor(bx)), y, int(math.floor(bz))), T.wall_base)
            scene.set(int(math.floor(bx)), cy + int(height * 0.35), int(math.floor(bz)),
                      f"{trim.stairs}[facing={_face_to(bx, bz, cx, cz)}]")
    return Mask.from_points(cells)


def _face_to(x, z, cx, cz) -> str:
    """Horizontal direction from (x, z) towards (cx, cz)."""
    dx, dz = cx - x, cz - z
    if abs(dx) > abs(dz):
        return "east" if dx > 0 else "west"
    return "south" if dz > 0 else "north"


def _stair_ring(scene, ring: Mask, cx: float, cz: float, stairs: str | None, half: str = "top") -> None:
    if not stairs:
        return
    for (x, y, z) in ring.points().tolist():
        if scene.get(x, y, z) == "minecraft:air":
            scene.set(x, y, z, f"{stairs}[facing={_face_to(x + 0.5, z + 0.5, cx, cz)},half={half}]")


# ======================================================================= details
def column(scene, base, height: int, *, theme=None, material: str | None = None, style: str = "classic") -> Mask:
    """Column with a base and a capital. style: classic (stairs base/capital) | log | wall."""
    T = _theme(theme)
    x, y, z = (int(v) for v in base)
    mat = material or T.trim
    fam = _fam(scene, mat)
    cells = []
    for h in range(height):
        if style == "log":
            scene.set(x, y + h, z, f"{T.frame}[axis=y]" if "log" in T.frame else T.frame)
        elif style == "wall" and fam.wall:
            scene.set(x, y + h, z, fam.wall)
        else:
            scene.set(x, y + h, z, "quartz_pillar[axis=y]" if mat == "quartz_block" else fam.base)
        cells.append((x, y + h, z))
    if style == "classic" and fam.stairs:
        for d, (dx, dz) in DIRS.items():
            scene.set(x + dx, y, z + dz, f"{fam.stairs}[facing={OPP[d]}]")
            scene.set(x + dx, y + height - 1, z + dz, f"{fam.stairs}[facing={OPP[d]},half=top]")
    return Mask.from_points(cells)


def arch(scene, center, span: int, height: int, *, axis: str = "x", thickness: int = 1, theme=None,
         material=None, clear: bool = True) -> Mask:
    """Round arch standing on the ground at ``center`` (x, y, z): opening ``span`` wide along ``axis``,
    ``height`` high at the apex. Walls of the arch are 2 blocks wide."""
    T = _theme(theme)
    cx, cy, cz = (float(v) for v in center)
    r = span / 2.0
    spring = height - r  # height where the curve starts
    cells = []
    open_cells = []
    for off in range(-int(r) - 2, int(r) + 3):
        for y in range(int(cy), int(cy + height + 2)):
            yy = y - cy
            inside_open = abs(off + 0.5) < r and (yy < spring or (off + 0.5) ** 2 + (yy - spring) ** 2 < r * r)
            inside_outer = abs(off + 0.5) < r + 2 and (yy < spring or (off + 0.5) ** 2 + (yy - spring) ** 2 < (r + 2) ** 2) \
                and yy <= height + 1
            for t in range(thickness):
                p = (int(math.floor(cx)) + off, y, int(math.floor(cz)) + t) if axis == "x" else \
                    (int(math.floor(cx)) + t, y, int(math.floor(cz)) + off)
                if inside_open:
                    open_cells.append(p)
                elif inside_outer:
                    cells.append(p)
    m = Mask.from_points(cells)
    scene.put(m, material or T.wall)
    if clear and open_cells:
        scene.put(Mask.from_points(open_cells), "air")
    return m


def battlements(scene, box, *, theme=None, material=None) -> Mask:
    """Crenellated parapet on the top edge of a box (y2 + 1)."""
    T = _theme(theme)
    b = Box.of(box)
    cells = []
    for name, line, axis in _sides(b):
        for idx, (x, z) in enumerate(line):
            cells.append((x, b.y2 + 1, z))
            if idx % 2 == 0:
                cells.append((x, b.y2 + 2, z))
    m = Mask.from_points(cells)
    scene.put(m, material or T.wall)
    return m


# ======================================================================= buildings
def house(scene, box, *, theme=None, style: str | None = None, roof_style: str | None = None,
          door_side: str = "south", floors: int | None = None, chimney: bool | None = None, seed: int = 0) -> dict:
    """A complete building: walls with depth, windows, door, floors, roof, chimney, lamps.
    ``box`` = footprint (x1, y1, z1, x2, y2, z2): y1 floor level, y2 wall top."""
    T = _theme(theme)
    b = Box.of(box)
    rng = np.random.default_rng(seed)
    # foundation under the floor
    scene.fill((b.x1, b.y1 - 1, b.z1, b.x2, b.y1 - 1, b.z2), T.wall_base)
    scene.fill((b.x1 + 1, b.y1, b.z1 + 1, b.x2 - 1, b.y2, b.z2 - 1), "air")
    scene.fill((b.x1 + 1, b.y1, b.z1 + 1, b.x2 - 1, b.y1, b.z2 - 1), T.floor)
    walls(scene, b, theme=T, style=style, seed=seed)
    # floors every 5 blocks
    storey = 5
    for y in range(b.y1 + storey, b.y2, storey):
        scene.fill((b.x1 + 1, y, b.z1 + 1, b.x2 - 1, y, b.z2 - 1), T.floor)
    # windows between pillars on every side, each storey
    for name, line, axis in _sides(b):
        for y in range(b.y1 + 2, b.y2 - 1, storey):
            for idx in range(2, len(line) - 2, 4):
                x, z = line[idx]
                if name == door_side and abs(idx - len(line) // 2) <= 1 and y == b.y1 + 2:
                    continue
                window(scene, (x, y, z), name, width=1, height=2, theme=T,
                       style="shutters" if T.name in ("fantasy_medieval", "winter_north") else "plain")
    # door in the middle of the door side
    line = dict((n, l) for n, l, _ in _sides(b))[door_side]
    mx, mz = line[len(line) // 2]
    door(scene, (mx, b.y1, mz), door_side, theme=T)
    r = roof(scene, b, style=roof_style, theme=T, seed=seed)
    if chimney if chimney is not None else T.name in ("fantasy_medieval", "winter_north"):
        cxz = (b.x1 + 2, b.z1 + 2)
        top = int(r.bbox.y2) + 2 if r.bbox else b.y2 + 6
        for y in range(b.y1 + 1, top):
            scene.put((cxz[0], y, cxz[1]), P.mix({"bricks": 3, "cobblestone": 1, "stone_bricks": 1}))
        scene.set(cxz[0], top, cxz[1], "campfire[lit=true,signal_fire=false]")
    return {"box": b.as_tuple(), "roof": r.bbox.as_tuple() if r.bbox else None}


def pagoda(scene, center, *, tiers: int = 3, base: int = 11, tier_height: int = 5, theme=None, seed: int = 0) -> Mask:
    """Asian pagoda: stacked shrinking storeys with curved roofs and a finial."""
    T = _theme(theme or "asian_sakura")
    cx, cy, cz = (int(v) for v in center)
    y = cy
    size = base
    cells = []
    for t in range(tiers):
        half = size // 2
        b = Box(cx - half, y, cz - half, cx + half, y + tier_height - 1, cz + half)
        scene.fill((b.x1, b.y1 - 1, b.z1, b.x2, b.y1 - 1, b.z2), T.wall_base if t == 0 else T.floor)
        scene.fill(b, "air")
        # red pillars at corners and every 3rd block, white walls between
        pillar = T.pillar if isinstance(T.pillar, str) else "stripped_mangrove_log"
        pillar_state = f"{pillar}[axis=y]" if ("log" in pillar or "stem" in pillar) else pillar
        for name, line, axis in _sides(b):
            for idx, (x, z) in enumerate(line):
                is_p = idx in (0, len(line) - 1) or idx % 3 == 0
                for yy in range(b.y1, b.y2 + 1):
                    if is_p:
                        scene.set(x, yy, z, pillar_state)
                    else:
                        scene.put((x, yy, z), T.wall)
            for idx in range(2, len(line) - 2, 3):
                x, z = line[idx]
                window(scene, (x, b.y1 + 1, z), name, height=2, theme=T, style="plain")
        roof(scene, b, style="asian", theme=T, overhang=2 + (1 if t == 0 else 0), pitch=0.8)
        cells.extend(Mask.box(b).points().tolist())
        rb = scene.bbox()
        y = b.y2 + 1 + max(3, int(size * 0.28))
        size = max(5, size - 4)
    # finial
    for k in range(4):
        scene.set(cx, y - 1 + k, cz, "chain" if k % 2 else "gold_block" if k == 3 else _wall_of(scene, "stone_bricks"))
    return Mask.from_points(cells)


def torii(scene, pos, facing: str = "south", *, width: int = 7, height: int = 7, theme=None) -> Mask:
    """Torii gate: two red pillars, the kasagi top beam with upturned ends and the nuki tie beam.
    ``pos`` = ground cell under the gate's center; the path goes along ``facing``."""
    T = _theme(theme or "asian_sakura")
    x, y, z = (int(v) for v in pos)
    ax = "x" if facing in ("north", "south") else "z"
    half = width // 2
    red = "stripped_mangrove_log" if "mangrove" in str(T.pillar) or T.name == "asian_sakura" else "red_terracotta"
    dark = "dark_oak_planks"
    cells = []

    def at(o, yy):
        return (x + o, yy, z) if ax == "x" else (x, yy, z + o)

    for o in (-half + 1, half - 1):
        for h in range(1, height + 1):
            p = at(o, y + h)
            scene.set(*p, f"{red}[axis=y]" if "log" in red else red)
            cells.append(p)
    # nuki (tie beam) and kasagi (top beam)
    for o in range(-half, half + 1):
        p = at(o, y + height - 1)
        if abs(o) < half:
            scene.set(*p, "red_terracotta")
            cells.append(p)
        p2 = at(o, y + height + 1)
        scene.set(*p2, "dark_oak_planks")
        cells.append(p2)
    for o in range(-half - 1, half + 2):
        p3 = at(o, y + height + 2)
        st = "dark_oak_slab[type=bottom]" if abs(o) <= half - 1 else "dark_oak_stairs[facing=" + (
            ("east" if o > 0 else "west") if ax == "x" else ("south" if o > 0 else "north")) + ",half=bottom]"
        scene.set(*p3, st)
        cells.append(p3)
    # plaque in the middle
    p = at(0, y + height)
    scene.set(*p, "red_terracotta")
    return Mask.from_points(cells)
