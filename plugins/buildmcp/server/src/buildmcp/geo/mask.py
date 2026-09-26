"""Boolean voxel masks in world coordinates.

A Mask is the universal "region" type: shapes, generators and scene queries return
masks, and the scene paints masks with blocks or palettes. Masks combine with
``|`` (union), ``&`` (intersection), ``-`` (difference) and ``^``.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
from scipy import ndimage

from .box import Box


class Mask:
    __slots__ = ("origin", "arr")

    def __init__(self, origin: Sequence[int], arr: np.ndarray):
        self.origin = np.asarray(origin, dtype=np.int64).reshape(3)
        self.arr = np.asarray(arr, dtype=bool)
        if self.arr.ndim != 3:
            raise ValueError("mask array must be 3D (x, y, z)")

    # ------------------------------------------------------------ construction
    @classmethod
    def empty(cls) -> "Mask":
        return cls((0, 0, 0), np.zeros((0, 0, 0), bool))

    @classmethod
    def box(cls, box) -> "Mask":
        b = Box.of(box)
        return cls(b.min, np.ones(b.size, bool))

    @classmethod
    def from_points(cls, points) -> "Mask":
        pts = np.asarray(list(points), dtype=np.int64).reshape(-1, 3)
        if len(pts) == 0:
            return cls.empty()
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        arr = np.zeros(tuple(hi - lo + 1), bool)
        rel = pts - lo
        arr[rel[:, 0], rel[:, 1], rel[:, 2]] = True
        return cls(lo, arr)

    @classmethod
    def from_function(cls, box, fn: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]) -> "Mask":
        """Evaluate ``fn(x, y, z) -> bool array`` over every cell of ``box`` (world coords)."""
        b = Box.of(box)
        xs, ys, zs = np.meshgrid(
            np.arange(b.x1, b.x2 + 1), np.arange(b.y1, b.y2 + 1), np.arange(b.z1, b.z2 + 1), indexing="ij"
        )
        return cls(b.min, np.asarray(fn(xs, ys, zs), bool))

    def copy(self) -> "Mask":
        return Mask(self.origin.copy(), self.arr.copy())

    # ----------------------------------------------------------------- queries
    @property
    def shape(self) -> tuple[int, int, int]:
        return self.arr.shape  # type: ignore[return-value]

    @property
    def count(self) -> int:
        return int(self.arr.sum())

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return bool(self.arr.any())

    @property
    def extent(self) -> Box | None:
        """Box of the whole array (not trimmed)."""
        if self.arr.size == 0:
            return None
        hi = self.origin + np.array(self.arr.shape) - 1
        return Box(*self.origin, *hi)

    @property
    def bbox(self) -> Box | None:
        """Tight box around the True cells (None if empty)."""
        if not self.arr.any():
            return None
        idx = [np.nonzero(self.arr.any(axis=tuple(a for a in range(3) if a != ax)))[0] for ax in range(3)]
        lo = self.origin + np.array([i[0] for i in idx])
        hi = self.origin + np.array([i[-1] for i in idx])
        return Box(*lo, *hi)

    def coords(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        xs, ys, zs = np.nonzero(self.arr)
        return xs + self.origin[0], ys + self.origin[1], zs + self.origin[2]

    def points(self) -> np.ndarray:
        """(N, 3) array of world coordinates."""
        xs, ys, zs = self.coords()
        return np.stack([xs, ys, zs], axis=1)

    def contains(self, p: Sequence[int]) -> bool:
        rel = np.asarray(p, np.int64) - self.origin
        if np.any(rel < 0) or np.any(rel >= np.array(self.arr.shape)):
            return False
        return bool(self.arr[tuple(rel)])

    # --------------------------------------------------------------- alignment
    def trim(self) -> "Mask":
        b = self.bbox
        if b is None:
            return Mask.empty()
        lo = np.array(b.min) - self.origin
        hi = np.array(b.max) - self.origin + 1
        return Mask(b.min, self.arr[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]].copy())

    def to_box(self, box) -> np.ndarray:
        """This mask resampled into the frame of ``box`` (cells outside are False)."""
        b = Box.of(box)
        out = np.zeros(b.size, bool)
        if self.arr.size == 0:
            return out
        src_lo = self.origin
        src_hi = self.origin + np.array(self.arr.shape)  # exclusive
        lo = np.maximum(src_lo, b.min)
        hi = np.minimum(src_hi, np.array(b.max) + 1)
        if np.any(hi <= lo):
            return out
        s = tuple(slice(lo[i] - src_lo[i], hi[i] - src_lo[i]) for i in range(3))
        d = tuple(slice(lo[i] - b.min[i], hi[i] - b.min[i]) for i in range(3))
        out[d] = self.arr[s]
        return out

    def _combine(self, other: "Mask", op) -> "Mask":
        other = as_mask(other)
        boxes = [m.extent for m in (self, other) if m.extent is not None]
        if not boxes:
            return Mask.empty()
        b = boxes[0]
        for x in boxes[1:]:
            b = b.union(x)
        return Mask(b.min, op(self.to_box(b), other.to_box(b)))

    def __or__(self, other) -> "Mask":
        return self._combine(other, np.logical_or)

    def __and__(self, other) -> "Mask":
        other = as_mask(other)
        a, b = self.extent, other.extent
        if a is None or b is None or a.intersect(b) is None:
            return Mask.empty()
        box = a.intersect(b)
        return Mask(box.min, self.to_box(box) & other.to_box(box))

    def __sub__(self, other) -> "Mask":
        if self.extent is None:
            return Mask.empty()
        other = as_mask(other)
        return Mask(self.origin, self.arr & ~other.to_box(self.extent))

    def __xor__(self, other) -> "Mask":
        return self._combine(other, np.logical_xor)

    # ----------------------------------------------------------- morphology
    def padded(self, n: int) -> "Mask":
        if self.arr.size == 0:
            return self
        return Mask(self.origin - n, np.pad(self.arr, n))

    def dilate(self, n: int = 1, horizontal: bool = False, vertical: bool = False) -> "Mask":
        """Grow by ``n`` cells (6-connected steps). ``horizontal``/``vertical`` limit the directions."""
        if n <= 0 or not self:
            return self.copy()
        m = self.padded(n)
        st = _structure(horizontal, vertical)
        return Mask(m.origin, ndimage.binary_dilation(m.arr, structure=st, iterations=n))

    def erode(self, n: int = 1, horizontal: bool = False, vertical: bool = False) -> "Mask":
        if n <= 0 or not self:
            return self.copy()
        m = self.padded(1)
        st = _structure(horizontal, vertical)
        out = ndimage.binary_erosion(m.arr, structure=st, iterations=n, border_value=0)
        return Mask(m.origin, out).trim()

    def dilate_round(self, r: float) -> "Mask":
        """Grow by a Euclidean radius (smooth, round blobs)."""
        if r <= 0 or not self:
            return self.copy()
        n = int(np.ceil(r))
        m = self.padded(n)
        dist = ndimage.distance_transform_edt(~m.arr)
        return Mask(m.origin, dist <= r)

    def erode_round(self, r: float) -> "Mask":
        if r <= 0 or not self:
            return self.copy()
        m = self.padded(1)
        dist = ndimage.distance_transform_edt(m.arr)
        return Mask(m.origin, dist > r).trim()

    def smooth(self, sigma: float = 1.0, threshold: float = 0.5) -> "Mask":
        """Gaussian smoothing of the shape (removes 1-block noise, rounds corners)."""
        if not self:
            return self.copy()
        n = int(np.ceil(sigma * 3)) + 1
        m = self.padded(n)
        f = ndimage.gaussian_filter(m.arr.astype(np.float32), sigma)
        return Mask(m.origin, f >= threshold).trim()

    def fill_holes(self) -> "Mask":
        return Mask(self.origin, ndimage.binary_fill_holes(self.arr))

    def largest_part(self) -> "Mask":
        """Only the biggest connected piece (26-neighbourhood): drops the loose specks a noisy shape
        (displaced SDF, thin tips) leaves floating around it."""
        if not self:
            return self.copy()
        lab, n = ndimage.label(self.arr, structure=np.ones((3, 3, 3), bool))
        if n <= 1:
            return self.copy()
        biggest = int(np.argmax(np.bincount(lab.ravel())[1:])) + 1
        return Mask(self.origin, lab == biggest)

    def shell(self, thickness: int = 1) -> "Mask":
        """Outer layer of the solid (cells within ``thickness`` of the outside, 6-connected)."""
        return self - self.erode(thickness)

    # ---------------------------------------------------------- surface parts
    def _shift_neighbor(self, axis: int, step: int) -> np.ndarray:
        """Boolean array: does the neighbor at (axis, step) belong to the mask?"""
        nb = np.zeros_like(self.arr)
        src = [slice(None)] * 3
        dst = [slice(None)] * 3
        if step > 0:
            src[axis] = slice(1, None)
            dst[axis] = slice(0, -1)
        else:
            src[axis] = slice(0, -1)
            dst[axis] = slice(1, None)
        nb[tuple(dst)] = self.arr[tuple(src)]
        return nb

    def top(self) -> "Mask":
        """Cells whose upper neighbor is outside the mask (the walkable surface)."""
        return Mask(self.origin, self.arr & ~self._shift_neighbor(1, +1))

    def bottom(self) -> "Mask":
        return Mask(self.origin, self.arr & ~self._shift_neighbor(1, -1))

    def sides(self) -> "Mask":
        """Cells exposed horizontally (at least one of N/S/E/W neighbors is outside)."""
        exposed = np.zeros_like(self.arr)
        for axis in (0, 2):
            for step in (1, -1):
                exposed |= ~self._shift_neighbor(axis, step)
        return Mask(self.origin, self.arr & exposed)

    def exposed(self) -> "Mask":
        """Cells with any of the 6 neighbors outside the mask."""
        exposed = np.zeros_like(self.arr)
        for axis in range(3):
            for step in (1, -1):
                exposed |= ~self._shift_neighbor(axis, step)
        return Mask(self.origin, self.arr & exposed)

    def rim(self) -> "Mask":
        """Top cells that are also on the horizontal edge (outline of the top surface)."""
        return self.top() & self.sides()

    def above(self, n: int = 1) -> "Mask":
        """The mask shifted up by ``n`` (e.g. where to put flowers on a surface)."""
        return self.translate(0, n, 0)

    def below(self, n: int = 1) -> "Mask":
        return self.translate(0, -n, 0)

    # ------------------------------------------------------------- transforms
    def translate(self, dx: int = 0, dy: int = 0, dz: int = 0) -> "Mask":
        return Mask(self.origin + np.array([dx, dy, dz]), self.arr)

    def where(self, fn: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]) -> "Mask":
        """Keep cells where ``fn(x, y, z)`` is true (vectorized, world coordinates)."""
        if not self:
            return self.copy()
        xs, ys, zs = np.nonzero(self.arr)
        keep = np.asarray(fn(xs + self.origin[0], ys + self.origin[1], zs + self.origin[2]), bool)
        out = np.zeros_like(self.arr)
        out[xs[keep], ys[keep], zs[keep]] = True
        return Mask(self.origin, out)

    def slice_y(self, y1: int, y2: int | None = None) -> "Mask":
        y2 = y1 if y2 is None else y2
        return self.where(lambda x, y, z: (y >= min(y1, y2)) & (y <= max(y1, y2)))

    def rotate(self, turns: int, center: Sequence[float] = (0, 0, 0)) -> "Mask":
        """Rotate around a vertical axis through ``center`` (quarter turns clockwise)."""
        from ..blocks.transforms import rotate_xz

        if not self:
            return self.copy()
        pts = self.points().astype(np.float64)
        cx, cz = float(center[0]), float(center[2])
        x, z = rotate_xz(pts[:, 0] - cx, pts[:, 2] - cz, turns)
        pts[:, 0] = np.round(x + cx)
        pts[:, 2] = np.round(z + cz)
        return Mask.from_points(pts.astype(np.int64))

    def mirror(self, axis: str, center: float = 0.0) -> "Mask":
        """Mirror across the plane x=center (axis='x') or z=center (axis='z')."""
        if not self:
            return self.copy()
        pts = self.points()
        i = 0 if axis == "x" else 2
        pts[:, i] = np.round(2 * center - pts[:, i]).astype(np.int64)
        return Mask.from_points(pts)

    def symmetric(self, center: Sequence[float], mode: str = "4") -> "Mask":
        """Union with rotated copies: mode '2' (half turn), '4' (quarter turns), 'x'/'z'/'xz' (mirrors)."""
        out = self.copy()
        if mode in ("2", "4"):
            for t in ([2] if mode == "2" else [1, 2, 3]):
                out = out | self.rotate(t, center)
        else:
            if "x" in mode:
                out = out | out.mirror("x", center[0])
            if "z" in mode:
                out = out | out.mirror("z", center[2])
        return out

    # ----------------------------------------------------------------- sampling
    def sample(self, count: int | None = None, density: float | None = None, min_dist: float = 0.0,
               seed: int = 0) -> list[tuple[int, int, int]]:
        """Random points from the mask. ``density`` = fraction of cells; ``min_dist`` = Poisson-disk spacing."""
        pts = self.points()
        if len(pts) == 0:
            return []
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(pts))
        target = count if count is not None else int(round(len(pts) * (density if density is not None else 0.05)))
        if min_dist <= 0:
            chosen = pts[order[:target]]
            return [tuple(int(v) for v in p) for p in chosen]
        chosen: list[np.ndarray] = []
        cell = min_dist / np.sqrt(3)
        grid: dict[tuple[int, int, int], list[np.ndarray]] = {}
        r = int(np.ceil(min_dist / cell))
        d2 = min_dist * min_dist
        for i in order:
            p = pts[i]
            key = tuple((p // cell).astype(int))
            ok = True
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        for q in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                            if float(((p - q) ** 2).sum()) < d2:
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if ok:
                chosen.append(p)
                grid.setdefault(key, []).append(p)
                if len(chosen) >= target:
                    break
        return [tuple(int(v) for v in p) for p in chosen]

    def heightmap(self) -> tuple[np.ndarray, int, int]:
        """(top_y array over x,z with -1 where empty, x0, z0)."""
        if not self:
            return np.full((0, 0), -1), 0, 0
        has = self.arr.any(axis=1)
        idx = self.arr.shape[1] - 1 - np.argmax(self.arr[:, ::-1, :], axis=1)
        top = np.where(has, idx + self.origin[1], -1)
        return top, int(self.origin[0]), int(self.origin[2])

    def __repr__(self) -> str:
        return f"Mask({self.count} cells, bbox={self.bbox})"


def _structure(horizontal: bool, vertical: bool) -> np.ndarray:
    st = ndimage.generate_binary_structure(3, 1)
    if horizontal:
        st[:, 0, :] = False
        st[:, 2, :] = False
    elif vertical:
        st[0, :, :] = False
        st[2, :, :] = False
        st[:, :, 0] = False
        st[:, :, 2] = False
        st[1, :, 1] = True
    return st


def as_mask(obj) -> Mask:
    """Coerce Box / tuple / list of points / Mask into a Mask."""
    if isinstance(obj, Mask):
        return obj
    if obj is None:
        return Mask.empty()
    if isinstance(obj, Box):
        return Mask.box(obj)
    if hasattr(obj, "mask") and callable(obj.mask):
        return obj.mask()
    seq = list(obj)
    if len(seq) == 6 and all(np.isscalar(v) for v in seq):
        return Mask.box(Box(*seq))
    if len(seq) == 3 and all(np.isscalar(v) for v in seq):
        return Mask.from_points([seq])
    if len(seq) == 2 and all(len(p) == 3 for p in seq) and all(np.isscalar(v) for p in seq for v in p):
        return Mask.box(Box.of(seq))
    return Mask.from_points(seq)
