"""Palettes: how a region gets its blocks.

Anywhere a *block* is accepted you can pass:
  - a state string: ``"stone_bricks"``, ``"oak_stairs[facing=east]"``
  - a dict of weights: ``{"stone": 6, "andesite": 3, "cobblestone": 1}`` (random mix)
  - a list: ``["stone", "andesite"]`` (equal mix)
  - a Palette object (below) — palettes nest, so members can be palettes too
  - a function ``f(x, y, z) -> str | array of str`` (vectorized, world coordinates)

Good texture = few related blocks, clustered (``cluster=``) rather than salt-and-pepper,
with gradients towards the ground, edges and corners.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence

import numpy as np
from scipy.special import erf

from .noise import fbm, hash01

Blocklike = Any


def _seed_of(obj: Any) -> int:
    import zlib

    return zlib.crc32(repr(obj).encode()) & 0x7FFFFFFF


class Palette:
    """Base class. Subclasses implement ``ids_for(scene, xs, ys, zs)``."""

    seed: int = 0

    def ids_for(self, scene, xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def members(self) -> list:
        return []

    def states(self) -> list[str]:
        """Every block state this palette may produce (flattened)."""
        out: list[str] = []
        for m in self.members():
            if isinstance(m, Palette):
                out.extend(m.states())
            elif isinstance(m, str):
                out.append(m)
        return list(dict.fromkeys(out))

    def with_seed(self, seed: int) -> "Palette":
        import copy

        p = copy.copy(self)
        p.seed = int(seed)
        return p


def as_palette(block: Blocklike) -> Blocklike:
    """Normalize dict/list shorthands into Palette objects (strings and callables pass through)."""
    if isinstance(block, dict):
        return Mix(block)
    if isinstance(block, (list, tuple)):
        return Mix({m if isinstance(m, str) else m: 1 for m in block}) if all(isinstance(m, str) for m in block) \
            else Mix(list(block))
    return block


def resolve_ids(scene, block: Blocklike, xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> np.ndarray:
    """Block ids (scene palette indices) for every coordinate."""
    n = len(xs)
    block = as_palette(block)
    if isinstance(block, str):
        return np.full(n, scene.id_of(block), dtype=np.uint16)
    if isinstance(block, Palette):
        return block.ids_for(scene, xs, ys, zs).astype(np.uint16, copy=False)
    if hasattr(block, "base") and isinstance(getattr(block, "base"), str):  # Family
        return np.full(n, scene.id_of(block.base), dtype=np.uint16)
    if callable(block):
        res = block(xs, ys, zs)
        if isinstance(res, str):
            return np.full(n, scene.id_of(res), dtype=np.uint16)
        if isinstance(res, Palette):
            return res.ids_for(scene, xs, ys, zs)
        arr = np.asarray(res, dtype=object).reshape(-1)
        if arr.shape[0] != n:
            raise ValueError(f"block function returned {arr.shape[0]} values for {n} cells")
        uniq, inv = np.unique(arr.astype(str), return_inverse=True)
        lut = np.array([scene.id_of(u) for u in uniq], dtype=np.uint16)
        return lut[inv]
    raise TypeError(f"Not a block/palette: {block!r}")


# Standard deviation of noise.fbm by octave count (measured), used to flatten its distribution.
FBM_SIGMA = {1: 0.37, 2: 0.276, 3: 0.243, 4: 0.228, 5: 0.222, 6: 0.22}


def _uniformize(v: np.ndarray, sigma: float) -> np.ndarray:
    """Map roughly-normal noise values to ~uniform [0, 1)."""
    return np.clip(0.5 * (1.0 + erf(v / (sigma * math.sqrt(2.0)))), 0.0, 0.999999)


class Mix(Palette):
    """Weighted mix of blocks.

    ``cluster=0`` gives per-block random choice; ``cluster=6`` makes organic patches ~6
    blocks wide (members are ordered: neighbors in the list touch each other, so order
    them like a gradient, e.g. grass -> moss -> coarse_dirt). ``jitter`` blurs patch edges.
    """

    def __init__(self, members: dict | Sequence, cluster: float = 0.0, jitter: float = 0.12, seed: int | None = None):
        if isinstance(members, dict):
            items = list(members.items())
        else:
            items = [(m, 1.0) for m in members]
        if not items:
            raise ValueError("empty palette")
        self._members = [as_palette(m) for m, _ in items]
        w = np.array([float(x) for _, x in items], dtype=np.float64)
        if np.any(w < 0) or w.sum() <= 0:
            raise ValueError("weights must be positive")
        self.weights = w / w.sum()
        self.cum = np.cumsum(self.weights)
        self.cum[-1] = 1.0
        self.cluster = float(cluster)
        self.jitter = float(jitter)
        self.seed = _seed_of((items, cluster)) if seed is None else int(seed)

    def members(self) -> list:
        return list(self._members)

    def field(self, xs, ys, zs) -> np.ndarray:
        if self.cluster > 0:
            v = fbm(xs, ys, zs, scale=self.cluster, octaves=3, seed=self.seed)
            u = _uniformize(v, FBM_SIGMA[3])
            if self.jitter > 0:
                u = np.clip(u + (hash01(xs, ys, zs, self.seed + 7) - 0.5) * self.jitter, 0.0, 0.999999)
            return u
        return hash01(xs, ys, zs, self.seed)

    def ids_for(self, scene, xs, ys, zs):
        u = self.field(xs, ys, zs)
        idx = np.searchsorted(self.cum, u, side="right")
        idx = np.minimum(idx, len(self._members) - 1)
        out = np.empty(len(xs), dtype=np.uint16)
        for i, m in enumerate(self._members):
            sel = idx == i
            if sel.any():
                out[sel] = resolve_ids(scene, m, xs[sel], ys[sel], zs[sel])
        return out

    def __repr__(self):
        return f"Mix({[(m, round(float(w), 3)) for m, w in zip(self._members, self.weights)]}, cluster={self.cluster})"


class Gradient(Palette):
    """Blocks changing along an axis with a dithered transition.

    axis: 'x' | 'y' | 'z' | 'radial' (horizontal distance from ``center``) | 'sphere' (3D distance).
    ``start``/``end`` are coordinates (or distances) mapped to the first/last member.
    ``jitter`` (in bands) randomizes each cell; ``noise`` (blocks) warps the bands organically.
    """

    def __init__(self, members: Sequence[Blocklike], axis: str = "y", start: float = 0.0, end: float = 16.0,
                 center: Sequence[float] = (0, 0, 0), jitter: float = 0.8, noise: float = 0.0,
                 noise_scale: float = 12.0, seed: int | None = None):
        if not members:
            raise ValueError("empty gradient")
        self._members = [as_palette(m) for m in members]
        self.axis = axis
        self.start = float(start)
        self.end = float(end)
        self.center = tuple(float(c) for c in center)
        self.jitter = float(jitter)
        self.noise = float(noise)
        self.noise_scale = float(noise_scale)
        self.seed = _seed_of((list(members), axis, start, end)) if seed is None else int(seed)

    def members(self) -> list:
        return list(self._members)

    def coord(self, xs, ys, zs) -> np.ndarray:
        cx, cy, cz = self.center
        if self.axis == "x":
            return xs.astype(np.float64)
        if self.axis == "y":
            return ys.astype(np.float64)
        if self.axis == "z":
            return zs.astype(np.float64)
        if self.axis == "radial":
            return np.hypot(xs - cx, zs - cz)
        if self.axis == "sphere":
            return np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2 + (zs - cz) ** 2)
        raise ValueError(f"unknown gradient axis '{self.axis}'")

    def ids_for(self, scene, xs, ys, zs):
        c = self.coord(xs, ys, zs)
        if self.noise > 0:
            c = c + fbm(xs, ys, zs, scale=self.noise_scale, octaves=2, seed=self.seed) * self.noise
        span = self.end - self.start
        t = (c - self.start) / (span if abs(span) > 1e-9 else 1e-9)
        n = len(self._members)
        b = t * n
        if self.jitter > 0:
            b = b + (hash01(xs, ys, zs, self.seed) - 0.5) * self.jitter
        idx = np.clip(np.floor(b), 0, n - 1).astype(np.int64)
        out = np.empty(len(xs), dtype=np.uint16)
        for i, m in enumerate(self._members):
            sel = idx == i
            if sel.any():
                out[sel] = resolve_ids(scene, m, xs[sel], ys[sel], zs[sel])
        return out


class Layers(Palette):
    """Horizontal bands: ``Layers([(64, "stone"), (70, "dirt"), (None, "grass_block")])`` —
    each member applies up to and including its y (None = everything above)."""

    def __init__(self, bands: Sequence[tuple[float | None, Blocklike]], jitter: float = 0.0, seed: int | None = None):
        self.bands = [(None if y is None else float(y), as_palette(m)) for y, m in bands]
        self.jitter = float(jitter)
        self.seed = _seed_of(list(bands)) if seed is None else int(seed)

    def members(self) -> list:
        return [m for _, m in self.bands]

    def ids_for(self, scene, xs, ys, zs):
        yv = ys.astype(np.float64)
        if self.jitter > 0:
            yv = yv + (hash01(xs, ys, zs, self.seed) - 0.5) * self.jitter * 2
        out = np.empty(len(xs), dtype=np.uint16)
        done = np.zeros(len(xs), dtype=bool)
        for top, m in self.bands:
            sel = ~done if top is None else (~done & (yv <= top))
            if sel.any():
                out[sel] = resolve_ids(scene, m, xs[sel], ys[sel], zs[sel])
                done |= sel
        if not done.all():
            last = self.bands[-1][1]
            sel = ~done
            out[sel] = resolve_ids(scene, last, xs[sel], ys[sel], zs[sel])
        return out


class Field(Palette):
    """Members chosen by a custom field ``fn(x, y, z) -> float in [0, 1]`` (0 -> first member)."""

    def __init__(self, fn: Callable, members: Sequence[Blocklike], jitter: float = 0.5, seed: int | None = None):
        self.fn = fn
        self._members = [as_palette(m) for m in members]
        self.jitter = float(jitter)
        self.seed = _seed_of(list(members)) if seed is None else int(seed)

    def members(self) -> list:
        return list(self._members)

    def ids_for(self, scene, xs, ys, zs):
        t = np.asarray(self.fn(xs, ys, zs), dtype=np.float64).reshape(-1)
        n = len(self._members)
        b = t * n
        if self.jitter > 0:
            b = b + (hash01(xs, ys, zs, self.seed) - 0.5) * self.jitter
        idx = np.clip(np.floor(b), 0, n - 1).astype(np.int64)
        out = np.empty(len(xs), dtype=np.uint16)
        for i, m in enumerate(self._members):
            sel = idx == i
            if sel.any():
                out[sel] = resolve_ids(scene, m, xs[sel], ys[sel], zs[sel])
        return out


class Pattern(Palette):
    """Regular patterns for floors and walls.

    kind: 'checker' (size = square size), 'stripes' (along ``axis``), 'border' (members[0]
    inside, members[1] on every cell where (coord - offset) % size == 0 → grid lines),
    'diagonal'.
    """

    def __init__(self, members: Sequence[Blocklike], kind: str = "checker", size: int = 1, axis: str = "x",
                 offset: Sequence[int] = (0, 0, 0)):
        self._members = [as_palette(m) for m in members]
        self.kind = kind
        self.size = max(1, int(size))
        self.axis = axis
        self.offset = tuple(int(o) for o in offset)
        self.seed = 0

    def members(self) -> list:
        return list(self._members)

    def ids_for(self, scene, xs, ys, zs):
        ox, oy, oz = self.offset
        s = self.size
        n = len(self._members)
        if self.kind == "checker":
            idx = ((xs - ox) // s + (zs - oz) // s + (ys - oy) // s) % n
        elif self.kind == "stripes":
            c = {"x": xs - ox, "y": ys - oy, "z": zs - oz}[self.axis]
            idx = (c // s) % n
        elif self.kind == "diagonal":
            idx = (((xs - ox) + (zs - oz)) // s) % n
        elif self.kind == "border":
            on = ((xs - ox) % s == 0) | ((zs - oz) % s == 0)
            idx = np.where(on, 1 % n, 0)
        else:
            raise ValueError(f"unknown pattern kind '{self.kind}'")
        idx = np.asarray(idx, dtype=np.int64)
        out = np.empty(len(xs), dtype=np.uint16)
        for i, m in enumerate(self._members):
            sel = idx == i
            if sel.any():
                out[sel] = resolve_ids(scene, m, xs[sel], ys[sel], zs[sel])
        return out


# --------------------------------------------------------------- shorthands
def mix(members, cluster: float = 0.0, jitter: float = 0.12, seed: int | None = None) -> Mix:
    """Weighted mix. ``mix({"stone": 5, "andesite": 3}, cluster=5)``."""
    return Mix(members, cluster=cluster, jitter=jitter, seed=seed)


def patches(members, size: float = 6.0, jitter: float = 0.12, seed: int | None = None) -> Mix:
    """Organic patches ``size`` blocks wide (ordered members blend into their neighbors)."""
    return Mix(members, cluster=size, jitter=jitter, seed=seed)


def gradient(members, axis: str = "y", start: float = 0.0, end: float = 16.0, **kw) -> Gradient:
    return Gradient(members, axis=axis, start=start, end=end, **kw)


def layers(bands, jitter: float = 0.0) -> Layers:
    return Layers(bands, jitter=jitter)


def field(fn, members, jitter: float = 0.5) -> Field:
    return Field(fn, members, jitter=jitter)


def checker(a, b, size: int = 1) -> Pattern:
    return Pattern([a, b], kind="checker", size=size)


def stripes(members, axis: str = "x", width: int = 1) -> Pattern:
    return Pattern(members, kind="stripes", size=width, axis=axis)
