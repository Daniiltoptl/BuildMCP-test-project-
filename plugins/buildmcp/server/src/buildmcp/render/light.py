"""Game-like light propagation (block light and sky light, levels 0..15)."""

from __future__ import annotations

import numpy as np
from numba import njit

from .models import F_OCC


@njit(cache=True)
def _bfs(light, blocked, filt):
    sx, sy, sz = light.shape
    n = sx * sy * sz
    queue = np.empty(n, np.int64)
    head = 0
    tail = 0
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                if light[x, y, z] > 1:
                    queue[tail % n] = (x * sy + y) * sz + z
                    tail += 1
    dxs = (1, -1, 0, 0, 0, 0)
    dys = (0, 0, 1, -1, 0, 0)
    dzs = (0, 0, 0, 0, 1, -1)
    while head < tail:
        idx = queue[head % n]
        head += 1
        z = idx % sz
        y = (idx // sz) % sy
        x = idx // (sy * sz)
        lv = light[x, y, z]
        if lv <= 1:
            continue
        for k in range(6):
            nx = x + dxs[k]
            ny = y + dys[k]
            nz = z + dzs[k]
            if nx < 0 or ny < 0 or nz < 0 or nx >= sx or ny >= sy or nz >= sz:
                continue
            if blocked[nx, ny, nz]:
                continue
            nl = lv - 1 - filt[nx, ny, nz]
            if nl > light[nx, ny, nz]:
                light[nx, ny, nz] = nl
                if tail - head < n:
                    queue[tail % n] = (nx * sy + ny) * sz + nz
                    tail += 1
    return light


@njit(cache=True)
def _sky_columns(blocked, filt, sky):
    sx, sy, sz = blocked.shape
    for x in range(sx):
        for z in range(sz):
            lv = 15
            for y in range(sy - 1, -1, -1):
                if blocked[x, y, z]:
                    lv = 0
                else:
                    lv = max(0, lv - filt[x, y, z])
                sky[x, y, z] = lv
                if lv == 0 and blocked[x, y, z]:
                    # everything below stays 0 until spread by BFS
                    for yy in range(y - 1, -1, -1):
                        sky[x, yy, z] = 0
                    break
    return sky


def compute_light(vox: np.ndarray, st_flags: np.ndarray, st_emit: np.ndarray, st_filter: np.ndarray):
    """(block_light, sky_light) uint8 arrays for a padded voxel grid."""
    blocked = (st_flags[vox] & F_OCC) != 0
    filt = st_filter[vox].astype(np.int16)
    filt[blocked] = 15
    block = st_emit[vox].astype(np.int16)
    block = _bfs(block, blocked, filt)
    sky = np.zeros(vox.shape, np.int16)
    sky = _sky_columns(blocked, filt, sky)
    sky = _bfs(sky, blocked, filt)
    return block.astype(np.uint8), sky.astype(np.uint8)
