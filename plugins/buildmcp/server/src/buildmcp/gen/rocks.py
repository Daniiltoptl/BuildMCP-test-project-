"""Rocks, boulders, spikes, crystals, stalactites."""

from __future__ import annotations

import math

import numpy as np

from ..geo import sdf
from ..geo.mask import Mask
from ..paint import palette as P
from .. import themes as themes_mod


def _theme(theme):
    if theme is None:
        return themes_mod.get("fantasy_medieval")
    return themes_mod.get(theme) if isinstance(theme, str) else theme


def boulder(scene, at, size: float = 3.0, *, theme=None, palette=None, seed: int = 0, sink: float = 0.35,
            moss: bool = True) -> Mask:
    """A natural rock resting on the ground at ``at`` (partly sunk). size = radius in blocks."""
    T = _theme(theme)
    rng = np.random.default_rng(seed)
    c = np.array([at[0] + 0.5, at[1] + 1 + size * (0.6 - sink), at[2] + 0.5])
    shape = sdf.ellipsoid(c, (size * rng.uniform(0.9, 1.3), size * rng.uniform(0.6, 0.9), size * rng.uniform(0.8, 1.2)))
    shape = shape.rotate("y", rng.uniform(0, 180), c).displace(size * 0.28, scale=max(2.0, size * 0.8), seed=seed)
    m = shape.mask()
    pal = palette or P.Gradient([T.rock, T.rock_deep], axis="y", start=c[1] + size, end=c[1] - size, jitter=1.0,
                                seed=seed)
    scene.put(m, pal, only="#replaceable|#plants")
    if moss and T.name in ("fantasy_medieval", "asian_sakura"):
        top = m.top().where(lambda x, y, z: np.random.default_rng(seed + 1).random(len(x)) < 0.55)
        scene.put(top, P.patches({"moss_block": 3, "mossy_cobblestone": 1}, size=2, seed=seed))
        above = m.top().above(1).where(lambda x, y, z: np.random.default_rng(seed + 2).random(len(x)) < 0.25)
        scene.put(above, "moss_carpet", only="#air")
    if T.name == "winter_north":
        scene.put(m.top().above(1), "snow[layers=2]", only="#air")
    return m


def rock_cluster(scene, at, size: float = 4.0, count: int = 4, *, theme=None, seed: int = 0) -> Mask:
    """A main boulder with smaller satellites around it."""
    rng = np.random.default_rng(seed)
    m = boulder(scene, at, size, theme=theme, seed=seed)
    for i in range(count - 1):
        a = rng.uniform(0, 2 * math.pi)
        d = size * rng.uniform(0.9, 1.6)
        p = (int(at[0] + math.cos(a) * d), int(at[1]), int(at[2] + math.sin(a) * d))
        top = scene.top_y(p[0], p[2])
        if top is not None:
            p = (p[0], top, p[2])
        m = m | boulder(scene, p, size * rng.uniform(0.35, 0.6), theme=theme, seed=seed + 10 + i)
    return m


def spike(scene, at, height: float = 12.0, radius: float = 2.5, *, lean: tuple[float, float] = (0.0, 0.0),
          palette=None, theme=None, seed: int = 0, down: bool = False, twist: float = 0.0) -> Mask:
    """A tapering spire (dark theme spikes, rock pinnacles) — or a stalactite with down=True."""
    T = _theme(theme)
    x, y, z = at[0] + 0.5, at[1] + (0 if down else 1), at[2] + 0.5
    tip = np.array([x + lean[0] * height, y + (-height if down else height), z + lean[1] * height])
    shape = sdf.capsule((x, y, z), tip, radius, 0.35).displace(radius * 0.3, scale=max(2.0, radius), seed=seed)
    if twist:
        shape = shape.twist(twist, (x, y, z))
    m = shape.mask().largest_part()  # the noise can cut loose bits off the thin tip
    pal = palette or (P.Gradient([T.rock_deep, T.rock], axis="y", start=y, end=tip[1], jitter=1.0, seed=seed))
    scene.put(m, pal, only="#replaceable")
    return m


def crystal(scene, at, height: float = 7.0, radius: float = 1.3, *, direction=(0.2, 1.0, 0.1), palette=None,
            theme=None, seed: int = 0, glow: bool = True) -> Mask:
    """Faceted crystal: hexagonal prism with a pointed tip, tilted along ``direction``."""
    T = _theme(theme)
    d = np.asarray(direction, float)
    d = d / np.linalg.norm(d)
    base = np.array([at[0] + 0.5, at[1] + 1.0, at[2] + 0.5])
    tip = base + d * height
    body = sdf.capsule(base, base + d * height * 0.72, radius, radius * 0.9)
    point = sdf.capsule(base + d * height * 0.72, tip, radius * 0.9, 0.2)
    m = (body | point).mask()
    scene.put(m, palette or T.crystal, only="#replaceable")
    if glow:
        # hidden light at the base so the crystal glows at night
        cx, cy, cz = int(base[0]), int(base[1]), int(base[2])
        if scene.get(cx, cy - 1, cz) != "minecraft:air":
            scene.set(cx, cy - 1, cz, T.light_hidden if T.light_hidden != "shroomlight" else "sea_lantern")
    return m


def crystal_cluster(scene, at, size: float = 6.0, count: int = 5, *, palette=None, theme=None, seed: int = 0) -> Mask:
    rng = np.random.default_rng(seed)
    m = Mask.empty()
    for i in range(count):
        a = rng.uniform(0, 2 * math.pi)
        tilt = rng.uniform(0.05, 0.6) if i else 0.05
        d = (math.cos(a) * tilt, 1.0, math.sin(a) * tilt)
        off = (int(round(math.cos(a) * rng.uniform(0, size * 0.25))), 0, int(round(math.sin(a) * rng.uniform(0, size * 0.25))))
        h = size * (1.0 if i == 0 else rng.uniform(0.35, 0.7))
        m = m | crystal(scene, (at[0] + off[0], at[1], at[2] + off[2]), h, max(0.8, h * 0.18), direction=d,
                        palette=palette, theme=theme, seed=seed + i, glow=(i == 0))
    return m


def stalactites(scene, ceiling_mask, density: float = 0.05, max_len: int = 6, *, block: str = "pointed_dripstone",
                seed: int = 0) -> int:
    """Hang dripstone (or other blocks) from the underside of a mask."""
    from ..geo.mask import as_mask

    rng = np.random.default_rng(seed)
    n = 0
    for (x, y, z) in as_mask(ceiling_mask).bottom().sample(density=density, seed=seed):
        length = int(rng.integers(1, max_len + 1))
        for k in range(1, length + 1):
            if scene.get(x, y - k, z) != "minecraft:air":
                break
            state = "pointed_dripstone[vertical_direction=down]" if block == "pointed_dripstone" else block
            scene.set(x, y - k, z, state)
            n += 1
    return n
