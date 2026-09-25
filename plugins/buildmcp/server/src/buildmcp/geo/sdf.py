"""Signed distance fields: smooth organic shapes, rasterized to voxel masks.

Every shape is an SDF object: ``shape.mask()`` gives a Mask (cells whose center is
inside), shapes combine with ``|`` ``&`` ``-``, ``smooth_union``, ``.displace(...)``
(noise), ``.translate/.rotate/.scale``. Units are blocks, coordinates are world coords.

    rock = sdf.ellipsoid((0, 70, 0), (6, 4, 5)).displace(1.5, scale=4, seed=2)
    S.put(rock, P.patches(["stone", "andesite", "tuff"], size=3))
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

from .box import Box
from .mask import Mask


class SDF:
    """f(x, y, z) -> distance (negative inside). ``lo``/``hi`` bound the shape."""

    def __init__(self, fn: Callable, lo: Sequence[float], hi: Sequence[float]):
        self.fn = fn
        self.lo = np.asarray(lo, float)
        self.hi = np.asarray(hi, float)

    # ------------------------------------------------------------- evaluation
    def __call__(self, x, y, z):
        return self.fn(x, y, z)

    @property
    def bbox(self) -> Box:
        lo = np.floor(self.lo).astype(int)
        hi = np.ceil(self.hi).astype(int)
        return Box(*lo, *hi)

    def mask(self, within=None) -> Mask:
        """Rasterize: a cell (x, y, z) is inside when f at its center (x+0.5, y+0.5, z+0.5) <= 0."""
        b = self.bbox if within is None else Box.of(within)
        xs = np.arange(b.x1, b.x2 + 1)
        ys = np.arange(b.y1, b.y2 + 1)
        zs = np.arange(b.z1, b.z2 + 1)
        out = np.zeros(b.size, bool)
        # evaluate in y-slabs to bound memory
        step = max(1, int(2_000_000 // max(1, len(xs) * len(zs))))
        X, Z = np.meshgrid(xs + 0.5, zs + 0.5, indexing="ij")
        for j0 in range(0, len(ys), step):
            yy = ys[j0:j0 + step] + 0.5
            Xb = np.broadcast_to(X[:, None, :], (len(xs), len(yy), len(zs)))
            Yb = np.broadcast_to(yy[None, :, None], (len(xs), len(yy), len(zs)))
            Zb = np.broadcast_to(Z[:, None, :], (len(xs), len(yy), len(zs)))
            out[:, j0:j0 + step, :] = self.fn(Xb, Yb, Zb) <= 0
        return Mask(b.min, out).trim()

    def field(self, within=None) -> tuple[np.ndarray, Box]:
        """Raw distance values on the cell centers of ``within`` (default: bounds)."""
        b = self.bbox if within is None else Box.of(within)
        X, Y, Z = np.meshgrid(np.arange(b.x1, b.x2 + 1) + 0.5, np.arange(b.y1, b.y2 + 1) + 0.5,
                              np.arange(b.z1, b.z2 + 1) + 0.5, indexing="ij")
        return self.fn(X, Y, Z), b

    # ------------------------------------------------------------ combinators
    def __or__(self, other: "SDF") -> "SDF":
        return SDF(lambda x, y, z: np.minimum(self.fn(x, y, z), other.fn(x, y, z)),
                   np.minimum(self.lo, other.lo), np.maximum(self.hi, other.hi))

    def __and__(self, other: "SDF") -> "SDF":
        return SDF(lambda x, y, z: np.maximum(self.fn(x, y, z), other.fn(x, y, z)),
                   np.maximum(self.lo, other.lo), np.minimum(self.hi, other.hi))

    def __sub__(self, other: "SDF") -> "SDF":
        return SDF(lambda x, y, z: np.maximum(self.fn(x, y, z), -other.fn(x, y, z)), self.lo, self.hi)

    def smooth_union(self, other: "SDF", k: float = 3.0) -> "SDF":
        """Union with a smooth fillet of size ~k blocks (organic blending)."""
        def f(x, y, z):
            a = self.fn(x, y, z)
            b = other.fn(x, y, z)
            h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
            return b * (1 - h) + a * h - k * h * (1 - h)
        return SDF(f, np.minimum(self.lo, other.lo) - k, np.maximum(self.hi, other.hi) + k)

    def smooth_subtract(self, other: "SDF", k: float = 3.0) -> "SDF":
        def f(x, y, z):
            a = self.fn(x, y, z)
            b = -other.fn(x, y, z)
            h = np.clip(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
            return a * (1 - h) + b * h + k * h * (1 - h)
        return SDF(f, self.lo, self.hi)

    def shell(self, thickness: float = 1.0) -> "SDF":
        return SDF(lambda x, y, z: np.abs(self.fn(x, y, z)) - thickness / 2, self.lo - thickness, self.hi + thickness)

    def offset(self, d: float) -> "SDF":
        """Grow (d > 0) or shrink the shape by d blocks."""
        return SDF(lambda x, y, z: self.fn(x, y, z) - d, self.lo - max(d, 0), self.hi + max(d, 0))

    def displace(self, amount: float = 1.5, scale: float = 6.0, octaves: int = 3, seed: int = 0,
                 ridged: bool = False) -> "SDF":
        """Warp the surface with noise (amount in blocks) — rocks, islands, organic blobs."""
        from ..paint.noise import fbm, ridged as ridged_fn

        def f(x, y, z):
            n = ridged_fn(x, y, z, scale=scale, octaves=octaves, seed=seed) * 2 - 1 if ridged else \
                fbm(x, y, z, scale=scale, octaves=octaves, seed=seed)
            return self.fn(x, y, z) + n * amount
        return SDF(f, self.lo - amount, self.hi + amount)

    def translate(self, dx: float, dy: float = 0.0, dz: float = 0.0) -> "SDF":
        d = np.array([dx, dy, dz], float)
        return SDF(lambda x, y, z: self.fn(x - d[0], y - d[1], z - d[2]), self.lo + d, self.hi + d)

    def scale(self, s: float, center: Sequence[float] | None = None) -> "SDF":
        c = np.asarray(center if center is not None else (self.lo + self.hi) / 2, float)
        return SDF(lambda x, y, z: self.fn((x - c[0]) / s + c[0], (y - c[1]) / s + c[1], (z - c[2]) / s + c[2]) * s,
                   c + (self.lo - c) * s, c + (self.hi - c) * s)

    def rotate(self, axis: str, degrees: float, center: Sequence[float] | None = None) -> "SDF":
        """Rotate by any angle around an axis through ``center`` (default: bounds center)."""
        c = np.asarray(center if center is not None else (self.lo + self.hi) / 2, float)
        a = math.radians(degrees)
        ca, sa = math.cos(a), math.sin(a)

        def f(x, y, z):
            px, py, pz = x - c[0], y - c[1], z - c[2]
            # inverse rotation of the query point
            if axis == "y":
                qx, qy, qz = ca * px - sa * pz, py, sa * px + ca * pz
            elif axis == "x":
                qx, qy, qz = px, ca * py + sa * pz, -sa * py + ca * pz
            else:
                qx, qy, qz = ca * px + sa * py, -sa * px + ca * py, pz
            return self.fn(qx + c[0], qy + c[1], qz + c[2])

        r = float(np.max(np.abs(np.stack([self.lo - c, self.hi - c])))) * math.sqrt(3)
        return SDF(f, c - r, c + r)

    def twist(self, degrees_per_block: float, center: Sequence[float] | None = None) -> "SDF":
        """Twist around the vertical axis (spires, drills, spiral towers)."""
        c = np.asarray(center if center is not None else (self.lo + self.hi) / 2, float)
        k = math.radians(degrees_per_block)

        def f(x, y, z):
            a = (y - c[1]) * k
            ca, sa = np.cos(a), np.sin(a)
            px, pz = x - c[0], z - c[2]
            return self.fn(ca * px - sa * pz + c[0], y, sa * px + ca * pz + c[2])

        r = float(max(np.abs(self.lo[[0, 2]] - c[[0, 2]]).max(), np.abs(self.hi[[0, 2]] - c[[0, 2]]).max())) * 1.5
        return SDF(f, [c[0] - r, self.lo[1], c[2] - r], [c[0] + r, self.hi[1], c[2] + r])

    def mirror(self, axis: str, center: float) -> "SDF":
        i = "xyz".index(axis)

        def f(x, y, z):
            p = [x, y, z]
            p[i] = center - np.abs(p[i] - center)
            return self.fn(*p)
        lo = self.lo.copy()
        hi = self.hi.copy()
        hi[i] = max(hi[i], 2 * center - lo[i])
        lo[i] = min(lo[i], 2 * center - self.hi[i])
        return SDF(f, lo, hi)


# ------------------------------------------------------------------ primitives
def sphere(center: Sequence[float], r: float) -> SDF:
    c = np.asarray(center, float)
    return SDF(lambda x, y, z: np.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2) - r, c - r, c + r)


def ellipsoid(center: Sequence[float], radii: Sequence[float]) -> SDF:
    c = np.asarray(center, float)
    r = np.asarray(radii, float)

    def f(x, y, z):
        k0 = np.sqrt(((x - c[0]) / r[0]) ** 2 + ((y - c[1]) / r[1]) ** 2 + ((z - c[2]) / r[2]) ** 2)
        k1 = np.sqrt(((x - c[0]) / r[0] ** 2) ** 2 + ((y - c[1]) / r[1] ** 2) ** 2 + ((z - c[2]) / r[2] ** 2) ** 2)
        return np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -r.min())
    return SDF(f, c - r, c + r)


def box(lo: Sequence[float], hi: Sequence[float], rounding: float = 0.0) -> SDF:
    """Axis-aligned box between corners (inclusive block coords); ``rounding`` rounds edges."""
    a = np.asarray(lo, float)
    b = np.asarray(hi, float) + 1.0
    c = (a + b) / 2
    h = (b - a) / 2 - rounding

    def f(x, y, z):
        qx = np.abs(x - c[0]) - h[0]
        qy = np.abs(y - c[1]) - h[1]
        qz = np.abs(z - c[2]) - h[2]
        outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
        inside = np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0)
        return outside + inside - rounding
    return SDF(f, a, b)


def cylinder(base: Sequence[float], height: float, radius: float, radius_top: float | None = None) -> SDF:
    """Vertical cylinder (or cone frustum if ``radius_top`` differs) standing on ``base`` (x, y, z)."""
    bx, by, bz = (float(v) for v in base)
    r1 = float(radius)
    r2 = r1 if radius_top is None else float(radius_top)

    def f(x, y, z):
        t = np.clip((y - by) / max(height, 1e-6), 0, 1)
        r = r1 + (r2 - r1) * t
        d_r = np.sqrt((x - bx) ** 2 + (z - bz) ** 2) - r
        d_y = np.maximum(by - y, y - (by + height))
        return np.maximum(d_r, d_y)
    rm = max(r1, r2)
    return SDF(f, (bx - rm, by, bz - rm), (bx + rm, by + height, bz + rm))


def cone(base: Sequence[float], height: float, radius: float, tip_radius: float = 0.0) -> SDF:
    return cylinder(base, height, radius, tip_radius)


def capsule(a: Sequence[float], b: Sequence[float], r1: float, r2: float | None = None) -> SDF:
    """Tube from a to b with radius r1 at a and r2 at b (tapered branches, pipes, beams)."""
    pa = np.asarray(a, float)
    pb = np.asarray(b, float)
    r2 = r1 if r2 is None else r2
    ba = pb - pa
    L2 = float(ba @ ba) or 1e-9

    def f(x, y, z):
        px, py, pz = x - pa[0], y - pa[1], z - pa[2]
        t = np.clip((px * ba[0] + py * ba[1] + pz * ba[2]) / L2, 0, 1)
        dx = px - ba[0] * t
        dy = py - ba[1] * t
        dz = pz - ba[2] * t
        return np.sqrt(dx * dx + dy * dy + dz * dz) - (r1 + (r2 - r1) * t)
    rm = max(r1, r2)
    return SDF(f, np.minimum(pa, pb) - rm, np.maximum(pa, pb) + rm)


def torus(center: Sequence[float], R: float, r: float, axis: str = "y") -> SDF:
    c = np.asarray(center, float)

    def f(x, y, z):
        px, py, pz = x - c[0], y - c[1], z - c[2]
        if axis == "x":
            px, py = py, px
        elif axis == "z":
            pz, py = py, pz
        q = np.sqrt(px * px + pz * pz) - R
        return np.sqrt(q * q + py * py) - r
    e = R + r
    return SDF(f, c - e, c + e)


def tube(points: Sequence[Sequence[float]], radii: float | Sequence[float]) -> SDF:
    """Smooth tube through points (union of tapered capsules). ``radii``: one value or one per point."""
    pts = [np.asarray(p, float) for p in points]
    if len(pts) < 2:
        raise ValueError("tube needs at least 2 points")
    rs = [float(radii)] * len(pts) if np.isscalar(radii) else [float(r) for r in radii]
    out = capsule(pts[0], pts[1], rs[0], rs[1])
    for i in range(1, len(pts) - 1):
        out = out | capsule(pts[i], pts[i + 1], rs[i], rs[i + 1])
    return out


def lathe(center: Sequence[float], profile: Sequence[tuple[float, float]]) -> SDF:
    """Solid of revolution around a vertical axis: ``profile`` = [(radius, y_offset), ...] from bottom to top.
    Great for vases, fountains, towers with bulges, onion domes, columns."""
    c = np.asarray(center, float)
    prof = np.asarray(profile, float)
    ys = prof[:, 1]
    rs = prof[:, 0]

    def f(x, y, z):
        rr = np.sqrt((x - c[0]) ** 2 + (z - c[2]) ** 2)
        yy = y - c[1]
        r_at = np.interp(yy, ys, rs, left=-1, right=-1)
        inside_y = (yy >= ys.min()) & (yy <= ys.max())
        d = np.where(inside_y, rr - r_at, np.maximum(ys.min() - yy, yy - ys.max()) + np.maximum(rr - rs.max(), 0))
        return d
    rm = rs.max()
    return SDF(f, (c[0] - rm, c[1] + ys.min(), c[2] - rm), (c[0] + rm, c[1] + ys.max(), c[2] + rm))


def dome(center: Sequence[float], radius: float, height: float | None = None) -> SDF:
    """Half ellipsoid standing on ``center`` (its flat side down)."""
    h = radius if height is None else height
    c = np.asarray(center, float)
    e = ellipsoid(c, (radius, h, radius))
    cut = box((c[0] - radius - 1, c[1], c[2] - radius - 1), (c[0] + radius + 1, c[1] + h + 1, c[2] + radius + 1))
    return e & cut


def extrude(mask2d: np.ndarray, origin: Sequence[int], depth: int, axis: str = "y") -> Mask:
    """Extrude a 2D boolean image into a Mask. axis 'y': image rows=z, cols=x, extruded upward;
    'z': image rows = -y (top row is highest), cols = x, extruded along +z; 'x': cols = z."""
    img = np.asarray(mask2d, bool)
    h, w = img.shape
    if axis == "y":
        arr = np.repeat(img.T[:, None, :], depth, axis=1)  # (x, y, z)
    elif axis == "z":
        arr = np.repeat(img[::-1, :].T[:, :, None], depth, axis=2)  # (x, y, z)
    else:
        arr = np.repeat(img[::-1, :].T[None, :, :].transpose(0, 2, 1), depth, axis=0)  # (x, y, z)
    return Mask(origin, arr)
