"""Discrete shapes and curves: lines, splines, circles, rings, polygons, arcs, spirals."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw

from .box import Box
from .mask import Mask


def line(a: Sequence[float], b: Sequence[float]) -> list[tuple[int, int, int]]:
    """6-connected-free voxel line from a to b (every step moves along the dominant axis)."""
    pa = np.asarray(a, float)
    pb = np.asarray(b, float)
    n = int(np.ceil(np.abs(pb - pa).max())) + 1
    pts = np.round(pa + (pb - pa) * np.linspace(0, 1, max(n, 2))[:, None]).astype(int)
    out = []
    for p in pts:
        t = (int(p[0]), int(p[1]), int(p[2]))
        if not out or out[-1] != t:
            out.append(t)
    return out


def polyline(points: Sequence[Sequence[float]]) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for i in range(len(points) - 1):
        seg = line(points[i], points[i + 1])
        out.extend(seg if not out else seg[1:])
    return out


def catmull_rom(points: Sequence[Sequence[float]], step: float = 0.5, closed: bool = False) -> np.ndarray:
    """Smooth curve through all points, sampled every ~``step`` blocks. Returns (N, D) floats."""
    p = np.asarray(points, float)
    if len(p) < 2:
        return p
    if closed:
        p = np.vstack([p[-1], p, p[0], p[1]])
    else:
        p = np.vstack([p[0] * 2 - p[1], p, p[-1] * 2 - p[-2]])
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        seg = np.linalg.norm(p2 - p1)
        n = max(2, int(seg / step))
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(p[-2])
    return np.asarray(out)


def bezier(points: Sequence[Sequence[float]], n: int | None = None) -> np.ndarray:
    """Bezier curve of any degree through its control points (de Casteljau). Returns (n, D)."""
    p = np.asarray(points, float)
    if n is None:
        n = max(8, int(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)) * 2))
    t = np.linspace(0, 1, n)[:, None]
    pts = [np.broadcast_to(q, (n, p.shape[1])) for q in p]
    while len(pts) > 1:
        pts = [(1 - t) * pts[i] + t * pts[i + 1] for i in range(len(pts) - 1)]
    return np.asarray(pts[0])


def _raster2d(draw_fn, x0: int, z0: int, w: int, h: int) -> np.ndarray:
    img = Image.new("1", (w, h), 0)
    d = ImageDraw.Draw(img)
    draw_fn(d)
    return np.asarray(img, dtype=bool)  # rows = z, cols = x


def circle(center: Sequence[float], r: float, y: int | None = None, filled: bool = True, thickness: float = 1.0) -> Mask:
    """Horizontal disc (or ring of ``thickness``) centered on (x, z) at height y (default center y)."""
    cx, cy, cz = (float(center[0]), float(center[1]), float(center[2])) if len(center) == 3 else (
        float(center[0]), float(y or 0), float(center[1]))
    yy = int(round(cy)) if y is None else int(y)
    R = int(math.ceil(r)) + 1
    xs = np.arange(int(math.floor(cx)) - R, int(math.floor(cx)) + R + 1)
    zs = np.arange(int(math.floor(cz)) - R, int(math.floor(cz)) + R + 1)
    X, Z = np.meshgrid(xs + 0.5, zs + 0.5, indexing="ij")
    d = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
    arr = d <= r if filled else (d <= r) & (d > r - thickness)
    return Mask((xs[0], yy, zs[0]), arr[:, None, :]).trim()


def ring(center: Sequence[float], r_outer: float, r_inner: float, y: int | None = None) -> Mask:
    return circle(center, r_outer, y, filled=False, thickness=r_outer - r_inner)


def polygon(points_xz: Sequence[Sequence[float]], y: int, filled: bool = True, width: int = 1) -> Mask:
    """2D polygon (list of (x, z)) at height y. ``filled=False`` draws the outline."""
    pts = np.asarray(points_xz, float)
    x0 = int(math.floor(pts[:, 0].min())) - 1
    z0 = int(math.floor(pts[:, 1].min())) - 1
    w = int(math.ceil(pts[:, 0].max())) - x0 + 3
    h = int(math.ceil(pts[:, 1].max())) - z0 + 3
    poly = [(float(p[0] - x0), float(p[1] - z0)) for p in pts]

    def draw(d):
        if filled:
            d.polygon(poly, fill=1, outline=1)
        else:
            d.line(poly + [poly[0]], fill=1, width=width)

    img = _raster2d(draw, x0, z0, w, h)
    return Mask((x0, y, z0), img.T[:, None, :]).trim()


def regular_polygon(center: Sequence[float], r: float, sides: int, rotation_deg: float = 0.0) -> list[tuple[float, float]]:
    """Vertices (x, z) of a regular polygon (use with polygon())."""
    cx, cz = float(center[0]), float(center[-1])
    return [(cx + r * math.cos(math.radians(rotation_deg) + 2 * math.pi * i / sides),
             cz + r * math.sin(math.radians(rotation_deg) + 2 * math.pi * i / sides)) for i in range(sides)]


def arc_points(center: Sequence[float], r: float, a0_deg: float, a1_deg: float, y: float | None = None,
               step: float = 0.5) -> np.ndarray:
    """Points along a horizontal arc (angles: 0 = +x/east, 90 = +z/south)."""
    cx, cy, cz = float(center[0]), float(center[1]) if y is None else float(y), float(center[2])
    n = max(2, int(abs(math.radians(a1_deg - a0_deg)) * r / step))
    a = np.radians(np.linspace(a0_deg, a1_deg, n))
    return np.stack([cx + r * np.cos(a), np.full(n, cy), cz + r * np.sin(a)], axis=1)


def spiral(center: Sequence[float], radius: float, y0: float, y1: float, turns: float, start_deg: float = 0.0,
           step: float = 0.5) -> np.ndarray:
    """Helix points (spiral staircases, twisted vines, dragon tails)."""
    cx, cz = float(center[0]), float(center[-1])
    length = abs(turns) * 2 * math.pi * radius + abs(y1 - y0)
    n = max(4, int(length / step))
    t = np.linspace(0, 1, n)
    a = np.radians(start_deg) + t * turns * 2 * math.pi
    return np.stack([cx + radius * np.cos(a), y0 + (y1 - y0) * t, cz + radius * np.sin(a)], axis=1)


def corridor(points: Sequence[Sequence[float]], width: float, y: int | None = None) -> Mask:
    """2D band of ``width`` along a polyline/curve of (x, y, z) points, flattened at y (or each point's y)."""
    pts = np.asarray(points, float)
    if pts.shape[1] == 2:
        pts = np.stack([pts[:, 0], np.full(len(pts), float(y or 0)), pts[:, 1]], axis=1)
    curve = catmull_rom(pts, step=0.4) if len(pts) > 2 else pts
    r = width / 2
    lo = np.floor(curve.min(axis=0) - r - 1).astype(int)
    hi = np.ceil(curve.max(axis=0) + r + 1).astype(int)
    xs = np.arange(lo[0], hi[0] + 1)
    zs = np.arange(lo[2], hi[2] + 1)
    X, Z = np.meshgrid(xs + 0.5, zs + 0.5, indexing="ij")
    dmin = np.full(X.shape, np.inf)
    ybest = np.zeros(X.shape)
    for i in range(len(curve) - 1):
        a = curve[i]
        b = curve[i + 1]
        ab = b[[0, 2]] - a[[0, 2]]
        L2 = float(ab @ ab) or 1e-9
        t = np.clip(((X - a[0]) * ab[0] + (Z - a[2]) * ab[1]) / L2, 0, 1)
        d = np.hypot(X - (a[0] + ab[0] * t), Z - (a[2] + ab[1] * t))
        upd = d < dmin
        dmin = np.where(upd, d, dmin)
        ybest = np.where(upd, a[1] + (b[1] - a[1]) * t, ybest)
    inside = dmin <= r
    if y is not None:
        return Mask((lo[0], int(y), lo[2]), inside[:, None, :]).trim()
    # follow the curve height
    yy = np.round(ybest).astype(int)
    ymin, ymax = int(yy[inside].min()), int(yy[inside].max())
    arr = np.zeros((len(xs), ymax - ymin + 1, len(zs)), bool)
    ix, iz = np.nonzero(inside)
    arr[ix, yy[ix, iz] - ymin, iz] = True
    return Mask((lo[0], ymin, lo[2]), arr).trim()


def points_mask(points: Sequence[Sequence[float]], radius: float = 0.0) -> Mask:
    """Mask of rounded points (radius 0: exact cells) — e.g. to thicken a curve."""
    pts = np.round(np.asarray(points, float)).astype(int)
    m = Mask.from_points(pts)
    return m.dilate_round(radius) if radius > 0 else m
