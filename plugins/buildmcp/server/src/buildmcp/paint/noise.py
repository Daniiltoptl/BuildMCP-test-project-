"""Deterministic noise fields (numba-accelerated): Perlin, fBm, ridged, Worley, hashes.

All functions take world coordinates as numbers or numpy arrays (broadcast together)
and return float arrays of the broadcast shape.
"""

from __future__ import annotations

import functools

import numpy as np
from numba import njit, prange


# ------------------------------------------------------------------ hashing
def hash_u64(x, y, z=0, seed: int = 0) -> np.ndarray:
    """64-bit hash of integer coordinates (vectorized, deterministic)."""
    with np.errstate(over="ignore"):
        xi = np.asarray(x, dtype=np.int64).astype(np.uint64)
        yi = np.asarray(y, dtype=np.int64).astype(np.uint64)
        zi = np.asarray(z, dtype=np.int64).astype(np.uint64)
        s = np.uint64((seed * 0x27D4EB2F165667C5 + 0x165667B19E3779F9) & 0xFFFFFFFFFFFFFFFF)
        h = xi * np.uint64(0x9E3779B97F4A7C15)
        h ^= yi * np.uint64(0xC2B2AE3D27D4EB4F)
        h ^= zi * np.uint64(0x94D049BB133111EB)
        h ^= s
        h ^= h >> np.uint64(33)
        h *= np.uint64(0xFF51AFD7ED558CCD)
        h ^= h >> np.uint64(33)
        h *= np.uint64(0xC4CEB9FE1A85EC53)
        h ^= h >> np.uint64(33)
    return h


def hash01(x, y, z=0, seed: int = 0) -> np.ndarray:
    """Uniform [0, 1) per integer cell."""
    h = hash_u64(x, y, z, seed)
    return (h >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)


# ------------------------------------------------------------------ perlin
@functools.lru_cache(maxsize=256)
def _perm(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed & 0xFFFFFFFF)
    p = rng.permutation(256).astype(np.int32)
    return np.concatenate([p, p])


@njit(cache=True, fastmath=True, inline="always")
def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


@njit(cache=True, fastmath=True, inline="always")
def _grad(h, x, y, z):
    h = h & 15
    u = x if h < 8 else y
    if h < 4:
        v = y
    elif h == 12 or h == 14:
        v = x
    else:
        v = z
    return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)


@njit(cache=True, fastmath=True)
def _perlin1(perm, x, y, z):
    fx = np.floor(x)
    fy = np.floor(y)
    fz = np.floor(z)
    X = int(fx) & 255
    Y = int(fy) & 255
    Z = int(fz) & 255
    x -= fx
    y -= fy
    z -= fz
    u = _fade(x)
    v = _fade(y)
    w = _fade(z)
    A = perm[X] + Y
    AA = perm[A] + Z
    AB = perm[A + 1] + Z
    B = perm[X + 1] + Y
    BA = perm[B] + Z
    BB = perm[B + 1] + Z
    l1 = _grad(perm[AA], x, y, z) + u * (_grad(perm[BA], x - 1, y, z) - _grad(perm[AA], x, y, z))
    l2 = _grad(perm[AB], x, y - 1, z) + u * (_grad(perm[BB], x - 1, y - 1, z) - _grad(perm[AB], x, y - 1, z))
    l3 = _grad(perm[AA + 1], x, y, z - 1) + u * (_grad(perm[BA + 1], x - 1, y, z - 1) - _grad(perm[AA + 1], x, y, z - 1))
    l4 = _grad(perm[AB + 1], x, y - 1, z - 1) + u * (
        _grad(perm[BB + 1], x - 1, y - 1, z - 1) - _grad(perm[AB + 1], x, y - 1, z - 1)
    )
    a = l1 + v * (l2 - l1)
    b = l3 + v * (l4 - l3)
    return a + w * (b - a)


@njit(cache=True, fastmath=True, parallel=True)
def _fbm_flat(perm, xs, ys, zs, freq, octaves, lacunarity, gain, ridged, out):
    n = xs.shape[0]
    for i in prange(n):
        amp = 1.0
        f = freq
        total = 0.0
        norm = 0.0
        weight = 1.0
        for o in range(octaves):
            ox = o * 17.31
            v = _perlin1(perm, xs[i] * f + ox, ys[i] * f + ox * 0.7, zs[i] * f + ox * 1.3)
            if ridged:
                r = 1.0 - abs(v)
                r = r * r * weight
                weight = min(1.0, max(0.0, r * 2.0))
                total += r * amp
            else:
                total += v * amp
            norm += amp
            amp *= gain
            f *= lacunarity
        out[i] = total / norm


def _flat(*arrs):
    b = np.broadcast_arrays(*[np.asarray(a, dtype=np.float64) for a in arrs])
    shape = b[0].shape
    return [np.ascontiguousarray(a).ravel() for a in b], shape


def fbm(x, y, z=0.0, scale: float = 32.0, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5,
        seed: int = 0) -> np.ndarray:
    """Fractal Perlin noise in roughly [-1, 1]. ``scale`` = feature size in blocks."""
    (xs, ys, zs), shape = _flat(x, y, z)
    out = np.empty(xs.shape[0])
    # offset z by a seed-dependent fraction so 2D use (z=0) never sits on lattice planes
    zs = zs + 0.5 + (seed % 97) * 0.0137 * scale
    _fbm_flat(_perm(seed), xs, ys, zs, 1.0 / max(scale, 1e-6), int(octaves), lacunarity, gain, False, out)
    return (out * 1.4).reshape(shape)


def perlin(x, y, z=0.0, scale: float = 16.0, seed: int = 0) -> np.ndarray:
    return fbm(x, y, z, scale=scale, octaves=1, seed=seed)


def ridged(x, y, z=0.0, scale: float = 32.0, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5,
           seed: int = 0) -> np.ndarray:
    """Ridged multifractal noise in [0, 1] (sharp crests: mountain ridges, cracks, veins)."""
    (xs, ys, zs), shape = _flat(x, y, z)
    out = np.empty(xs.shape[0])
    zs = zs + 0.5 + (seed % 97) * 0.0137 * scale
    _fbm_flat(_perm(seed), xs, ys, zs, 1.0 / max(scale, 1e-6), int(octaves), lacunarity, gain, True, out)
    return np.clip(out.reshape(shape), 0.0, 1.0)


def noise01(x, y, z=0.0, scale: float = 32.0, octaves: int = 4, seed: int = 0) -> np.ndarray:
    """fBm remapped to [0, 1] (0.5 average)."""
    return np.clip((fbm(x, y, z, scale=scale, octaves=octaves, seed=seed) + 1.0) * 0.5, 0.0, 1.0)


# ------------------------------------------------------------------ worley
@njit(cache=True, fastmath=True, parallel=True)
def _worley_flat(xs, ys, zs, inv, seed, f1_out, f2_out):
    n = xs.shape[0]
    for i in prange(n):
        px = xs[i] * inv
        py = ys[i] * inv
        pz = zs[i] * inv
        cx = int(np.floor(px))
        cy = int(np.floor(py))
        cz = int(np.floor(pz))
        f1 = 1e9
        f2 = 1e9
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    gx = cx + dx
                    gy = cy + dy
                    gz = cz + dz
                    h = (gx * 73856093) ^ (gy * 19349663) ^ (gz * 83492791) ^ (seed * 2654435761)
                    h = (h ^ (h >> 13)) * 1274126177
                    h = h ^ (h >> 16)
                    jx = ((h & 1023) / 1023.0)
                    jy = (((h >> 10) & 1023) / 1023.0)
                    jz = (((h >> 20) & 1023) / 1023.0)
                    ddx = gx + jx - px
                    ddy = gy + jy - py
                    ddz = gz + jz - pz
                    d = np.sqrt(ddx * ddx + ddy * ddy + ddz * ddz)
                    if d < f1:
                        f2 = f1
                        f1 = d
                    elif d < f2:
                        f2 = d
        f1_out[i] = f1
        f2_out[i] = f2


def worley(x, y, z=0.0, scale: float = 8.0, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Cellular noise: (F1, F2) distances to the nearest feature points, in cell units.
    ``F2 - F1`` near 0 marks cell borders (cracks, stone slabs, crystal facets)."""
    (xs, ys, zs), shape = _flat(x, y, z)
    f1 = np.empty(xs.shape[0])
    f2 = np.empty(xs.shape[0])
    _worley_flat(xs, ys, zs, 1.0 / max(scale, 1e-6), int(seed) & 0x7FFFFFFF, f1, f2)
    return f1.reshape(shape), f2.reshape(shape)
