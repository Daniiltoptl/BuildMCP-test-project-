"""Procedural custom trees (the thing that makes a build look 'pro').

    trees.tree(S, (x, y, z), kind="oak_giant", height=20, theme=T, seed=4)
    trees.forest(S, island.surface, kinds=["oak", "birch"], count=12, min_dist=9, theme=T, avoid=plaza)

Kinds: oak_giant, oak, birch, willow, cherry, pine, dead, fungus_giant, bush.
``at`` is the ground block the tree stands on top of (the trunk starts one above).
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

import numpy as np

from ..geo import sdf
from ..geo.mask import Mask, as_mask
from ..paint import palette as P
from ..paint.noise import hash01
from .. import themes as themes_mod

KINDS = ("oak_giant", "oak", "birch", "willow", "cherry", "pine", "dead", "fungus_giant", "bush")


@dataclass
class TreeResult:
    wood: Mask
    leaves: Mask
    extra: Mask = field(default_factory=Mask.empty)
    top: tuple = (0, 0, 0)
    roots: Mask = field(default_factory=Mask.empty)

    @property
    def all(self) -> Mask:
        return self.wood | self.leaves | self.extra


def _theme(theme):
    if theme is None:
        return themes_mod.get("fantasy_medieval")
    return themes_mod.get(theme) if isinstance(theme, str) else theme


def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0.0, 1.0, 0.0])


def _perturb(d, rng, amount):
    return _unit(d + rng.normal(0, amount, 3))


def _grow(start, direction, length, r0, r1, rng, *, step=1.4, wobble=0.18, up_bias=0.0, gravity=0.0):
    """Polyline branch: returns list of (p0, p1, ra, rb) segments and the tip point."""
    segs = []
    p = np.asarray(start, float)
    d = _unit(direction)
    n = max(2, int(length / step))
    for i in range(n):
        t0 = i / n
        t1 = (i + 1) / n
        d = _perturb(d, rng, wobble)
        d = _unit(d + np.array([0.0, up_bias - gravity * t1, 0.0]))
        q = p + d * (length / n)
        segs.append((p, q, r0 + (r1 - r0) * t0, r0 + (r1 - r0) * t1))
        p = q
    return segs, p


def _segments_mask(segs) -> Mask:
    m = Mask.empty()
    for a, b, ra, rb in segs:
        m = m | sdf.capsule(a, b, max(ra, 0.45), max(rb, 0.45)).mask()
    return m


def _cluster(center, radius, flat, rng, seed):
    r = radius * rng.uniform(0.85, 1.15)
    e = sdf.ellipsoid(center, (r * rng.uniform(0.9, 1.1), r * flat, r * rng.uniform(0.9, 1.1)))
    return e.displace(min(1.6, r * 0.28), scale=max(2.5, r * 0.7), octaves=2, seed=seed).mask()


def tree(scene, at, kind: str = "oak", *, height: float | None = None, theme=None, seed: int = 0,
         wood=None, leaves=None, place: bool = True, snow: bool | None = None) -> TreeResult:
    """Grow one tree standing on the block ``at``. Returns the masks it occupies."""
    T = _theme(theme)
    if kind not in KINDS:
        raise ValueError(f"unknown tree kind '{kind}'. Kinds: {', '.join(KINDS)}")
    # zlib.crc32, not hash(): str hashes change from one Python process to the next, and a build
    # must come out the same in every session (the rendered and the exported build are one)
    rng = np.random.default_rng(seed * 7919 + zlib.crc32(kind.encode()) % 10007)
    base = np.array([at[0] + 0.5, at[1] + 1.0, at[2] + 0.5])
    fn = {
        "oak_giant": _oak_giant, "oak": _oak, "birch": _birch, "willow": _willow, "cherry": _cherry,
        "pine": _pine, "dead": _dead, "fungus_giant": _fungus, "bush": _bush,
    }[kind]
    res: TreeResult = fn(base, height, rng, seed)
    if place:
        wood_block = wood or _default_wood(kind, T)
        leaf_block = leaves or _default_leaves(kind, T)
        scene.put(res.wood, wood_block, only="#replaceable|#leaves")
        if res.roots:
            # roots hug the ground: they may replace soil so they look embedded
            scene.put(res.roots, wood_block, only="#replaceable|#leaves|grass_block|dirt|coarse_dirt|podzol|"
                      "moss_block|rooted_dirt|mud|snow_block|crimson_nylium|warped_nylium|netherrack|soul_soil")
        scene.put(res.leaves - res.wood, leaf_block, only="#replaceable")
        if kind == "fungus_giant":
            _fungus_extras(scene, res, rng, T)
        if kind == "cherry":
            _petals(scene, res, rng)
        if kind == "pine" and (snow if snow is not None else T.name == "winter_north"):
            _snow_caps(scene, res)
        if kind == "willow":
            _vines(scene, res, rng, 0.25)
    return res


def _default_wood(kind, T):
    if kind in ("birch",):
        return "birch_wood"
    if kind == "cherry":
        return "cherry_wood"
    if kind == "pine":
        return "spruce_wood"
    if kind == "dead":
        return P.mix({"stripped_dark_oak_wood": 3, "dark_oak_wood": 2, "stripped_spruce_wood": 1}, seed=5)
    if kind == "fungus_giant":
        return "crimson_hyphae" if T.name != "winter_north" else "warped_hyphae"
    if kind == "willow":
        return "dark_oak_wood"
    return T.trunk if T.trunk.endswith(("_wood", "_hyphae")) else "oak_wood"


def _default_leaves(kind, T):
    if kind == "birch":
        return P.patches({"birch_leaves": 5, "oak_leaves": 1}, size=2)
    if kind == "cherry":
        return P.patches({"cherry_leaves": 9, "flowering_azalea_leaves": 0.6}, size=3)
    if kind == "pine":
        return P.patches({"spruce_leaves": 6, "dark_oak_leaves": 0.5}, size=2)
    if kind == "fungus_giant":
        return P.patches({"nether_wart_block": 8, "shroomlight": 0.5}, size=2)
    if kind == "willow":
        return P.patches({"oak_leaves": 3, "mangrove_leaves": 2, "azalea_leaves": 1}, size=2)
    return T.leaves


# ------------------------------------------------------------------ kinds
def _oak_giant(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(18, 25)
    r_base = H * rng.uniform(0.12, 0.145)
    lean = _unit([rng.normal(0, 0.12), 1.0, rng.normal(0, 0.12)])
    trunk, top = _grow(base, lean, H * 0.58, r_base, r_base * 0.5, rng, step=1.6, wobble=0.08)
    segs = list(trunk)
    tips = []
    mids = []
    n_br = int(rng.integers(5, 8))
    golden = rng.uniform(0, 2 * math.pi)
    for i in range(n_br):
        t = rng.uniform(0.42, 1.0)
        k = min(len(trunk) - 1, int(t * len(trunk)))
        start = trunk[k][1]
        az = golden + i * 2.39996
        el = math.radians(rng.uniform(40, 68))
        d = np.array([math.cos(az) * math.sin(el), math.cos(el), math.sin(az) * math.sin(el)])
        L = H * rng.uniform(0.38, 0.55)
        br, tip = _grow(start, d, L, r_base * 0.48, r_base * 0.16, rng, wobble=0.16, up_bias=0.06)
        segs += br
        tips.append(tip)
        mids.append(br[len(br) // 2][1])
        for _ in range(int(rng.integers(1, 4))):
            j = int(len(br) * rng.uniform(0.35, 0.8))
            sd = _perturb(d + np.array([0, 0.35, 0]), rng, 0.6)
            sb, stip = _grow(br[j][1], sd, L * rng.uniform(0.3, 0.5), r_base * 0.2, 0.45, rng, wobble=0.2)
            segs += sb
            tips.append(stip)
    tips.append(top + np.array([0, 2.0, 0]))
    roots = []
    for i in range(int(rng.integers(5, 8))):
        az = i * (2 * math.pi / 6) + rng.uniform(-0.4, 0.4)
        d = np.array([math.cos(az), -0.12, math.sin(az)])
        rt, _ = _grow(base + np.array([0, 0.9, 0]), d, r_base * rng.uniform(2.4, 3.8), r_base * 0.8, 0.45, rng,
                      wobble=0.12, gravity=0.18)
        roots += rt
    wood = _segments_mask(segs)
    leaves = Mask.empty()
    cr = H * 0.165
    for i, tip in enumerate(tips):
        leaves = leaves | _cluster(tip + np.array([0, cr * 0.3, 0]), cr * rng.uniform(0.8, 1.15), 0.6, rng, seed + i)
    for i, m in enumerate(mids):
        if rng.random() < 0.6:
            leaves = leaves | _cluster(m + np.array([0, cr * 0.5, 0]), cr * 0.65, 0.6, rng, seed + 50 + i)
    leaves = _droop(leaves, rng, 0.14, 2, seed)
    base_i = int(math.floor(base[1])) - 1
    root_mask = _segments_mask(roots).where(lambda x, y, z: y >= base_i)
    return TreeResult(wood, leaves, top=tuple(top), roots=root_mask)


def _oak(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(9, 13)
    r0 = max(0.6, H * 0.075)
    trunk, top = _grow(base, [rng.normal(0, 0.1), 1, rng.normal(0, 0.1)], H * 0.6, r0, r0 * 0.7, rng,
                       step=1.3, wobble=0.1)
    segs = list(trunk)
    tips = [top]
    for i in range(int(rng.integers(2, 4))):
        k = int(len(trunk) * rng.uniform(0.5, 0.95))
        az = rng.uniform(0, 2 * math.pi)
        d = np.array([math.cos(az) * 0.7, 0.7, math.sin(az) * 0.7])
        br, tip = _grow(trunk[k][1], d, H * rng.uniform(0.25, 0.4), r0 * 0.6, 0.45, rng, wobble=0.18)
        segs += br
        tips.append(tip)
    wood = _segments_mask(segs)
    leaves = Mask.empty()
    for i, tip in enumerate(tips):
        leaves = leaves | _cluster(tip + np.array([0, 1.0, 0]), H * rng.uniform(0.26, 0.33), 0.7, rng, seed + i)
    leaves = _droop(leaves, rng, 0.08, 1, seed)
    return TreeResult(wood, leaves, top=tuple(top))


def _birch(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(11, 16)
    trunk, top = _grow(base, [rng.normal(0, 0.06), 1, rng.normal(0, 0.06)], H * 0.85, 0.55, 0.45, rng,
                       step=1.5, wobble=0.05)
    segs = list(trunk)
    tips = [top]
    for i in range(int(rng.integers(2, 4))):
        k = int(len(trunk) * rng.uniform(0.55, 0.9))
        az = rng.uniform(0, 2 * math.pi)
        br, tip = _grow(trunk[k][1], [math.cos(az), 1.1, math.sin(az)], H * 0.18, 0.45, 0.45, rng)
        segs += br
        tips.append(tip)
    wood = _segments_mask(segs)
    leaves = Mask.empty()
    for i, tip in enumerate(tips):
        leaves = leaves | _cluster(tip + np.array([0, -0.5, 0]), rng.uniform(2.8, 3.6), 1.35, rng, seed + i)
    return TreeResult(wood, leaves, top=tuple(top))


def _willow(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(11, 15)
    r0 = H * 0.09
    trunk, top = _grow(base, [rng.normal(0, 0.15), 1, rng.normal(0, 0.15)], H * 0.55, r0, r0 * 0.6, rng,
                       step=1.3, wobble=0.12)
    segs = list(trunk)
    tips = []
    for i in range(int(rng.integers(5, 8))):
        k = int(len(trunk) * rng.uniform(0.6, 1.0)) - 1
        az = i * 2.39996 + rng.uniform(0, 0.5)
        d = np.array([math.cos(az), 0.9, math.sin(az)])
        br, tip = _grow(trunk[k][1], d, H * rng.uniform(0.35, 0.5), r0 * 0.5, 0.45, rng, wobble=0.12,
                        gravity=0.55)
        segs += br
        tips.append(tip)
    wood = _segments_mask(segs)
    leaves = Mask.empty()
    for i, tip in enumerate(tips + [top]):
        leaves = leaves | _cluster(tip + np.array([0, 1.0, 0]), H * 0.22, 0.55, rng, seed + i)
    leaves = _droop(leaves, rng, 0.45, 7, seed)
    return TreeResult(wood, leaves, top=tuple(top))


def _cherry(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(10, 14)
    r0 = H * 0.085
    lean = _unit([rng.normal(0, 0.35), 1, rng.normal(0, 0.35)])
    trunk, top = _grow(base, lean, H * 0.45, r0, r0 * 0.7, rng, step=1.2, wobble=0.14)
    segs = list(trunk)
    tips = []
    for i in range(int(rng.integers(3, 5))):
        az = i * 2.39996 + rng.uniform(0, 1.0)
        d = np.array([math.cos(az), 0.55, math.sin(az)])
        br, tip = _grow(top, d, H * rng.uniform(0.4, 0.55), r0 * 0.6, 0.45, rng, wobble=0.14, up_bias=0.08)
        segs += br
        tips.append(tip)
    wood = _segments_mask(segs)
    leaves = Mask.empty()
    for i, tip in enumerate(tips):
        leaves = leaves | _cluster(tip + np.array([0, 1.2, 0]), H * rng.uniform(0.28, 0.34), 0.5, rng, seed + i)
    leaves = _droop(leaves, rng, 0.2, 3, seed)
    return TreeResult(wood, leaves, top=tuple(top))


def _pine(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(15, 23)
    trunk, top = _grow(base, [rng.normal(0, 0.04), 1, rng.normal(0, 0.04)], H, max(0.6, H * 0.055), 0.45, rng,
                       step=1.5, wobble=0.03)
    wood = _segments_mask(trunk)
    leaves = Mask.empty()
    y = base[1] + H * 0.18
    k = 0
    width = H * rng.uniform(0.26, 0.32)
    while y < base[1] + H:
        t = (y - base[1]) / H
        R = max(1.0, (1 - t) ** 0.9 * width + 0.6)
        c = np.array([base[0] + (top[0] - base[0]) * t, y, base[2] + (top[2] - base[2]) * t])
        tier = sdf.cylinder(c, 1.6 + (1 - t), R, R * 0.45).displace(0.7, scale=2.5, seed=seed + k).mask()
        # tier edges droop by one block
        droop = sdf.cylinder(c - np.array([0, 1.0, 0]), 1.0, R * 0.95, R * 0.8).mask() - \
            sdf.cylinder(c - np.array([0, 1.0, 0]), 1.0, R * 0.65, R * 0.5).mask()
        leaves = leaves | tier | droop.where(lambda x, yy, z, s=seed + k: hash01(x, yy, z, s) < 0.55)
        y += rng.uniform(1.4, 2.0)
        k += 1
    leaves = leaves | sdf.cylinder(top, 3.5, 1.3, 0.2).mask()
    return TreeResult(wood, leaves, top=tuple(top))


def _dead(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(13, 20)
    r0 = H * 0.08
    trunk, top = _grow(base, [rng.normal(0, 0.2), 1, rng.normal(0, 0.2)], H * 0.6, r0, r0 * 0.5, rng,
                       step=1.2, wobble=0.25)
    segs = list(trunk)
    for i in range(int(rng.integers(4, 8))):
        k = int(len(trunk) * rng.uniform(0.35, 1.0)) - 1
        az = rng.uniform(0, 2 * math.pi)
        d = np.array([math.cos(az), rng.uniform(0.2, 1.0), math.sin(az)])
        br, tip = _grow(trunk[k][1], d, H * rng.uniform(0.25, 0.45), r0 * 0.45, 0.45, rng, wobble=0.35)
        segs += br
        for _ in range(int(rng.integers(0, 3))):
            j = int(len(br) * rng.uniform(0.3, 0.9))
            sb, _ = _grow(br[j][1], _perturb(d, rng, 0.9), H * 0.15, 0.45, 0.45, rng, wobble=0.4)
            segs += sb
    return TreeResult(_segments_mask(segs), Mask.empty(), top=tuple(top))


def _fungus(base, height, rng, seed) -> TreeResult:
    H = height or rng.uniform(12, 18)
    r0 = max(0.8, H * 0.08)
    stem, top = _grow(base, [rng.normal(0, 0.12), 1, rng.normal(0, 0.12)], H * 0.8, r0, r0 * 0.8, rng,
                      step=1.3, wobble=0.1)
    wood = _segments_mask(stem)
    cap_r = H * rng.uniform(0.38, 0.48)
    cap_c = top + np.array([0, 0.5, 0])
    outer = sdf.ellipsoid(cap_c, (cap_r, cap_r * 0.62, cap_r)).displace(1.2, scale=4, seed=seed)
    inner = sdf.ellipsoid(cap_c - np.array([0, 2.0, 0]), (cap_r - 1.8, cap_r * 0.62 - 1.2, cap_r - 1.8))
    cut = sdf.box((cap_c[0] - cap_r - 3, cap_c[1] - cap_r * 0.25, cap_c[2] - cap_r - 3),
                  (cap_c[0] + cap_r + 3, cap_c[1] + cap_r + 3, cap_c[2] + cap_r + 3))
    cap = ((outer - inner) & cut).mask()
    return TreeResult(wood, cap, top=tuple(top))


def _bush(base, height, rng, seed) -> TreeResult:
    r = (height or rng.uniform(2.0, 3.2))
    c = base + np.array([0, r * 0.35, 0])
    leaves = _cluster(c, r, 0.72, rng, seed)
    wood = Mask.from_points([tuple(np.floor(base).astype(int))])
    return TreeResult(wood, leaves - wood, top=tuple(c))


# ------------------------------------------------------------------ details
def _droop(leaves: Mask, rng, chance: float, max_len: int, seed: int) -> Mask:
    """Hang leaves below the canopy bottom (short fringes or long willow curtains)."""
    if max_len <= 0 or not leaves:
        return leaves
    bottom = leaves.bottom().points()
    add = []
    r = hash01(bottom[:, 0], bottom[:, 1], bottom[:, 2], seed + 91)
    for (x, y, z), v in zip(bottom.tolist(), r.tolist()):
        if v < chance:
            n = 1 + int(hash01(x, y, z, seed + 92) * max_len)
            for k in range(1, n + 1):
                add.append((x, y - k, z))
    return leaves | Mask.from_points(add) if add else leaves


def _fungus_extras(scene, res: TreeResult, rng, T) -> None:
    under = res.leaves.bottom().points()
    for (x, y, z) in under.tolist():
        if rng.random() < 0.18 and scene.get(x, y - 1, z) == "minecraft:air":
            n = int(rng.integers(2, 8))
            for k in range(1, n + 1):
                if scene.get(x, y - k, z) != "minecraft:air":
                    break
                scene.set(x, y - k, z, "weeping_vines")


def _petals(scene, res: TreeResult, rng) -> None:
    b = res.leaves.bbox
    if b is None:
        return
    for x in range(b.x1 - 2, b.x2 + 3):
        for z in range(b.z1 - 2, b.z2 + 3):
            if rng.random() > 0.35:
                continue
            y = scene.top_y(x, z)
            if y is None or y >= b.y1:
                continue
            g = scene.get(x, y, z)
            if scene.get(x, y + 1, z) == "minecraft:air" and ("grass_block" in g or "moss_block" in g or "dirt" in g):
                facing = ["north", "east", "south", "west"][int(rng.integers(0, 4))]
                scene.set(x, y + 1, z, f"pink_petals[flower_amount={int(rng.integers(1, 5))},facing={facing}]")


def _snow_caps(scene, res: TreeResult) -> None:
    for (x, y, z) in res.leaves.top().points().tolist():
        if scene.get(x, y + 1, z) == "minecraft:air":
            scene.set(x, y + 1, z, "snow[layers=2]")


_SIDES = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


def _vines(scene, res: TreeResult, rng, chance: float) -> None:
    """Vines clinging to the side of the lower canopy and hanging down from there. Every vine below
    keeps the same face: the game lets a vine hold on to the one above it only through that face
    (a chain under a vine[up=true] would drop off on the first block update)."""
    for (x, y, z) in res.leaves.bottom().points().tolist():
        if rng.random() >= chance:
            continue
        face = list(_SIDES)[int(rng.integers(0, 4))]
        dx, dz = _SIDES[face]
        vx, vz = x - dx, z - dz  # the leaf is on the ``face`` side of the vine
        for k in range(int(rng.integers(2, 6))):
            if scene.get(vx, y - k, vz) != "minecraft:air":
                break
            scene.set(vx, y - k, vz, f"vine[{face}=true]")


def forest(scene, surface, kinds=None, *, count: int | None = None, density: float = 0.004, min_dist: float = 8,
           theme=None, avoid=None, seed: int = 0, height_scale: tuple[float, float] = (0.8, 1.2)) -> list[TreeResult]:
    """Scatter trees over surface cells (Poisson-disk spaced). ``kinds`` defaults to the theme's."""
    T = _theme(theme)
    kinds = kinds or T.tree_kinds or ["oak"]
    surf = as_mask(surface)
    if avoid is not None:
        surf = surf - as_mask(avoid).dilate(2, horizontal=True)
    pts = surf.sample(count=count, density=None if count else density, min_dist=min_dist, seed=seed)
    rng = np.random.default_rng(seed + 5)
    out = []
    for i, p in enumerate(pts):
        kind = kinds[int(rng.integers(0, len(kinds)))]
        out.append(tree(scene, p, kind, theme=T, seed=seed * 1000 + i,
                        height=None if rng.random() < 0.5 else None))
    return out
