"""Integer boxes in world coordinates (inclusive bounds)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Box:
    x1: int
    y1: int
    z1: int
    x2: int
    y2: int
    z2: int

    def __post_init__(self):
        lo = (min(self.x1, self.x2), min(self.y1, self.y2), min(self.z1, self.z2))
        hi = (max(self.x1, self.x2), max(self.y1, self.y2), max(self.z1, self.z2))
        object.__setattr__(self, "x1", int(lo[0]))
        object.__setattr__(self, "y1", int(lo[1]))
        object.__setattr__(self, "z1", int(lo[2]))
        object.__setattr__(self, "x2", int(hi[0]))
        object.__setattr__(self, "y2", int(hi[1]))
        object.__setattr__(self, "z2", int(hi[2]))

    # ----------------------------------------------------------- construction
    @staticmethod
    def of(obj) -> "Box":
        """Accepts Box, (x1,y1,z1,x2,y2,z2), ((x1,y1,z1),(x2,y2,z2)) or a single point (x,y,z)."""
        if isinstance(obj, Box):
            return obj
        if hasattr(obj, "bbox") and not isinstance(obj, (tuple, list)):
            b = obj.bbox
            b = b() if callable(b) else b
            if b is None:
                raise ValueError("empty region has no box")
            return b
        seq = list(obj)
        if len(seq) == 6:
            return Box(*seq)
        if len(seq) == 2 and all(isinstance(p, (tuple, list)) and len(p) == 3 for p in seq):
            return Box(*seq[0], *seq[1])
        if len(seq) == 3 and all(isinstance(v, (int, float)) or hasattr(v, "__int__") for v in seq):
            x, y, z = (int(round(float(v))) for v in seq)
            return Box(x, y, z, x, y, z)
        raise ValueError(f"Cannot make a box from {obj!r}; use (x1,y1,z1,x2,y2,z2)")

    @staticmethod
    def around(center: Sequence[float], rx: int, ry: int | None = None, rz: int | None = None) -> "Box":
        cx, cy, cz = (int(round(c)) for c in center)
        ry = rx if ry is None else ry
        rz = rx if rz is None else rz
        return Box(cx - rx, cy - ry, cz - rz, cx + rx, cy + ry, cz + rz)

    @staticmethod
    def bounding(points: Iterable[Sequence[int]]) -> "Box":
        pts = list(points)
        xs, ys, zs = zip(*pts)
        return Box(min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

    # ---------------------------------------------------------------- queries
    @property
    def min(self) -> tuple[int, int, int]:
        return (self.x1, self.y1, self.z1)

    @property
    def max(self) -> tuple[int, int, int]:
        return (self.x2, self.y2, self.z2)

    @property
    def size(self) -> tuple[int, int, int]:
        return (self.x2 - self.x1 + 1, self.y2 - self.y1 + 1, self.z2 - self.z1 + 1)

    @property
    def volume(self) -> int:
        sx, sy, sz = self.size
        return sx * sy * sz

    @property
    def center(self) -> tuple[float, float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2, (self.z1 + self.z2) / 2)

    def contains(self, p: Sequence[int]) -> bool:
        return self.x1 <= p[0] <= self.x2 and self.y1 <= p[1] <= self.y2 and self.z1 <= p[2] <= self.z2

    def contains_box(self, b: "Box") -> bool:
        return self.contains(b.min) and self.contains(b.max)

    # ------------------------------------------------------------- operations
    def union(self, b: "Box") -> "Box":
        return Box(min(self.x1, b.x1), min(self.y1, b.y1), min(self.z1, b.z1),
                   max(self.x2, b.x2), max(self.y2, b.y2), max(self.z2, b.z2))

    def intersect(self, b: "Box") -> "Box | None":
        x1, y1, z1 = max(self.x1, b.x1), max(self.y1, b.y1), max(self.z1, b.z1)
        x2, y2, z2 = min(self.x2, b.x2), min(self.y2, b.y2), min(self.z2, b.z2)
        if x1 > x2 or y1 > y2 or z1 > z2:
            return None
        return Box(x1, y1, z1, x2, y2, z2)

    def expand(self, dx: int, dy: int | None = None, dz: int | None = None) -> "Box":
        dy = dx if dy is None else dy
        dz = dx if dz is None else dz
        return Box(self.x1 - dx, self.y1 - dy, self.z1 - dz, self.x2 + dx, self.y2 + dy, self.z2 + dz)

    def translate(self, dx: int, dy: int = 0, dz: int = 0) -> "Box":
        return Box(self.x1 + dx, self.y1 + dy, self.z1 + dz, self.x2 + dx, self.y2 + dy, self.z2 + dz)

    def as_tuple(self) -> tuple[int, int, int, int, int, int]:
        return (self.x1, self.y1, self.z1, self.x2, self.y2, self.z2)

    def __iter__(self):
        return iter(self.as_tuple())

    def __repr__(self) -> str:
        return f"Box({self.x1},{self.y1},{self.z1} .. {self.x2},{self.y2},{self.z2})"
