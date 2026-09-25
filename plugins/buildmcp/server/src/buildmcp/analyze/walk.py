"""Player walkability: can a player get from the spawn point to every NPC/portal?"""

from __future__ import annotations

from collections import deque

import numpy as np

from ..blocks import families as F
from ..geo.box import Box


def _tables(scene):
    """Per palette entry: (passable, stand_on) booleans."""
    n = len(scene.palette)
    passable = np.zeros(n, bool)
    stand = np.zeros(n, bool)
    for i, st in enumerate(scene.palette):
        name = st.removeprefix("minecraft:").split("[", 1)[0]
        base = st.split("{", 1)[0]
        try:
            boxes = scene.reg.collision(base)
        except Exception:  # noqa: BLE001
            boxes = ()
        top = max((b[4] for b in boxes), default=0.0)
        passable[i] = (not boxes) or top <= 0.2 or name in ("water",)
        stand[i] = bool(boxes) and top > 0.2 and name not in ("water", "lava")
        if F.kind_of(scene.reg, name) in (F.FENCE, F.WALL, F.FENCE_GATE):
            stand[i] = False  # 1.5 high: players can't step over, treat as blocking
            passable[i] = False
    return passable, stand


def walk_graph(scene, start, box: Box | None = None, max_nodes: int = 400_000):
    """BFS over standable cells from ``start`` (a position where a player stands).
    Returns (reached set of (x,y,z) foot positions, parent dict)."""
    b = box or scene.bbox()
    if b is None:
        return set(), {}
    b = b.expand(1, 3, 1)
    ids = scene.ids(b)
    passable, stand = _tables(scene)
    P = passable[ids]
    S = stand[ids]
    ox, oy, oz = b.min
    sx, sy, sz = ids.shape

    def ok(x, y, z):
        i, j, k = x - ox, y - oy, z - oz
        if not (0 <= i < sx and 1 <= j < sy - 1 and 0 <= k < sz):
            return False
        return S[i, j - 1, k] and P[i, j, k] and P[i, j + 1, k]

    sx0, sy0, sz0 = (int(v) for v in start)
    for dy in (0, 1, -1, 2):
        if ok(sx0, sy0 + dy, sz0):
            sy0 += dy
            break
    else:
        return set(), {}
    seen = {(sx0, sy0, sz0)}
    parent = {}
    q = deque([(sx0, sy0, sz0)])
    while q and len(seen) < max_nodes:
        x, y, z = q.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dy in (0, 1, -1, -2, -3):
                nx, ny, nz = x + dx, y + dy, z + dz
                if dy == 1 and not (P[x - ox, y + 2 - oy, z - oz] if 0 <= y + 2 - oy < sy else False):
                    continue  # need headroom to jump
                if ok(nx, ny, nz):
                    if (nx, ny, nz) not in seen:
                        seen.add((nx, ny, nz))
                        parent[(nx, ny, nz)] = (x, y, z)
                        q.append((nx, ny, nz))
                    break
    return seen, parent


def reachability(scene, start_marker: str = "spawn", targets: list[str] | None = None) -> dict:
    """Which markers can be walked to from the spawn marker (by kind npc/portal/warp by default)."""
    if start_marker not in scene.markers:
        return {"error": f"no '{start_marker}' marker"}
    sm = scene.markers[start_marker]
    reached, parent = walk_graph(scene, [int(np.floor(v)) for v in sm.pos])
    names = targets or [n for n, m in scene.markers.items() if m.kind in ("npc", "portal", "warp") and n != start_marker]
    out = {"walkable_cells": len(reached), "targets": {}}
    for n in names:
        m = scene.markers.get(n)
        if m is None:
            continue
        tx, ty, tz = (int(np.floor(v)) for v in m.pos)
        best = None
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for dy in range(-2, 3):
                    if (tx + dx, ty + dy, tz + dz) in reached:
                        d = abs(dx) + abs(dz) + abs(dy)
                        if best is None or d < best[0]:
                            best = (d, (tx + dx, ty + dy, tz + dz))
        if best is None:
            out["targets"][n] = {"reachable": False}
        else:
            length = 0
            node = best[1]
            while node in parent and length < 100000:
                node = parent[node]
                length += 1
            out["targets"][n] = {"reachable": True, "path_len": length}
    return out
