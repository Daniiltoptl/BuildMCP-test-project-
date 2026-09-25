"""Numba voxel ray tracer: exact block models, cutout/translucent textures, sun shadows,
ambient occlusion, sky and block light, water, fog.

Coordinates here are *grid* coordinates (cell (i, j, k) spans [i, i+1) etc.).
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

from .models import F_INVISIBLE, F_LIQUID, F_OCC, F_SELF_CULL, F_WATER, T_CUTOUT, T_TRANSLUCENT

INF = 1e30

# face index: 0 down, 1 up, 2 north(-z), 3 south(+z), 4 west(-x), 5 east(+x)


@njit(cache=True, fastmath=True)
def _hash3(x, y, z):
    h = (x * 73856093) ^ (y * 19349663) ^ (z * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFF) / 65536.0


@njit(cache=True, fastmath=True)
def _sample(tex_data, tex_off, tex_w, tex_h, tid, u, v):
    w = tex_w[tid]
    h = tex_h[tid]
    px = int(u * w)
    py = int(v * h)
    if px < 0:
        px = 0
    elif px >= w:
        px = w - 1
    if py < 0:
        py = 0
    elif py >= h:
        py = h - 1
    i = tex_off[tid] + (py * w + px) * 4
    return (tex_data[i] / 255.0, tex_data[i + 1] / 255.0, tex_data[i + 2] / 255.0, tex_data[i + 3] / 255.0)


@njit(cache=True, fastmath=True)
def _face_st(face, px, py, pz, fx, fy, fz, tx, ty, tz):
    """Fractions (s, t) of a hit point inside a face, in texture directions (u right, v down)."""
    dx = tx - fx
    dy = ty - fy
    dz = tz - fz
    if dx < 1e-9:
        dx = 1e-9
    if dy < 1e-9:
        dy = 1e-9
    if dz < 1e-9:
        dz = 1e-9
    if face == 1:  # up
        return (px - fx) / dx, (pz - fz) / dz
    if face == 0:  # down
        return (px - fx) / dx, (tz - pz) / dz
    if face == 2:  # north
        return (tx - px) / dx, (ty - py) / dy
    if face == 3:  # south
        return (px - fx) / dx, (ty - py) / dy
    if face == 4:  # west
        return (pz - fz) / dz, (ty - py) / dy
    return (tz - pz) / dz, (ty - py) / dy  # east


@njit(cache=True, fastmath=True)
def _world_uv(face, lx, ly, lz):
    """uvlock / liquids: texture coordinates projected from block-local world position (0..1)."""
    if face == 1:
        return lx, lz
    if face == 0:
        return lx, 1.0 - lz
    if face == 2:
        return 1.0 - lx, 1.0 - ly
    if face == 3:
        return lx, 1.0 - ly
    if face == 4:
        return lz, 1.0 - ly
    return 1.0 - lz, 1.0 - ly


@njit(cache=True, fastmath=True)
def _rot_st(s, t, rot):
    if rot == 1:
        return t, 1.0 - s
    if rot == 2:
        return 1.0 - s, 1.0 - t
    if rot == 3:
        return 1.0 - t, s
    return s, t


@njit(cache=True, fastmath=True)
def _face_normal(face):
    if face == 0:
        return 0.0, -1.0, 0.0
    if face == 1:
        return 0.0, 1.0, 0.0
    if face == 2:
        return 0.0, 0.0, -1.0
    if face == 3:
        return 0.0, 0.0, 1.0
    if face == 4:
        return -1.0, 0.0, 0.0
    return 1.0, 0.0, 0.0


@njit(cache=True, fastmath=True)
def _face_offset(face):
    if face == 0:
        return 0, -1, 0
    if face == 1:
        return 0, 1, 0
    if face == 2:
        return 0, 0, -1
    if face == 3:
        return 0, 0, 1
    if face == 4:
        return -1, 0, 0
    return 1, 0, 0


@njit(cache=True, fastmath=True)
def _state_at(vox, x, y, z, y_cut):
    sx, sy, sz = vox.shape
    if x < 0 or y < 0 or z < 0 or x >= sx or y >= sy or z >= sz:
        return 0
    if y > y_cut:
        return 0
    return vox[x, y, z]


@njit(cache=True, fastmath=True)
def _hit_cell(vox, cx, cy, cz, sid, ox, oy, oz, dx, dy, dz, t_lo, t_hi, y_cut,
              st_var_start, st_var_count, st_flags, st_height, var_elem_start, var_elem_count, var_weight,
              el_A, el_b, el_from, el_to, el_face, el_flags, fc_tex, fc_uv, fc_rot, fc_tint, fc_cull,
              tex_off, tex_w, tex_h, tex_mode, tex_data, tints, fixed_tints, shadow_mode):
    """Nearest visible texel inside one cell.

    Returns (hit, t, r, g, b, a, nx, ny, nz, mode, shade, face_axis_aligned)
    """
    nvar = st_var_count[sid]
    if nvar == 0:
        return False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 1, False
    v0 = st_var_start[sid]
    vi = v0
    if nvar > 1:
        r = _hash3(cx, cy, cz)
        for k in range(nvar):
            if r <= var_weight[v0 + k]:
                vi = v0 + k
                break
    e0 = var_elem_start[vi]
    ne = var_elem_count[vi]
    flags = st_flags[sid]
    # local ray (block-local world coords, 0..1)
    lox = ox - cx
    loy = oy - cy
    loz = oz - cz
    best_t = INF
    br = 0.0
    bg = 0.0
    bb = 0.0
    ba = 0.0
    bnx = 0.0
    bny = 0.0
    bnz = 0.0
    bmode = 0
    bshade = 1
    baxis = True
    liquid = (flags & F_LIQUID) != 0
    top_h = st_height[sid]
    same_above = False
    if liquid:
        if _state_at(vox, cx, cy + 1, cz, y_cut) == sid:
            same_above = True
            top_h = 1.0
    for e in range(e0, e0 + ne):
        A = el_A[e]
        bv = el_b[e]
        # ray in element space
        pex = A[0, 0] * lox + A[0, 1] * loy + A[0, 2] * loz + bv[0]
        pey = A[1, 0] * lox + A[1, 1] * loy + A[1, 2] * loz + bv[1]
        pez = A[2, 0] * lox + A[2, 1] * loy + A[2, 2] * loz + bv[2]
        dex = A[0, 0] * dx + A[0, 1] * dy + A[0, 2] * dz
        dey = A[1, 0] * dx + A[1, 1] * dy + A[1, 2] * dz
        dez = A[2, 0] * dx + A[2, 1] * dy + A[2, 2] * dz
        fx = el_from[e, 0]
        fy = el_from[e, 1]
        fz = el_from[e, 2]
        tx = el_to[e, 0]
        ty = el_to[e, 1]
        tz = el_to[e, 2]
        if liquid:
            ty = top_h
        tn = -INF
        tf = INF
        face = -1
        # slab x
        if abs(dex) < 1e-12:
            if pex < fx - 1e-9 or pex > tx + 1e-9:
                continue
        else:
            inv = 1.0 / dex
            t1 = (fx - pex) * inv
            t2 = (tx - pex) * inv
            f_near = 4
            if dex < 0:  # entering through the max side (also correct for zero-thickness planes)
                t1, t2 = t2, t1
                f_near = 5
            if t1 > tn:
                tn = t1
                face = f_near
            if t2 < tf:
                tf = t2
        if abs(dey) < 1e-12:
            if pey < fy - 1e-9 or pey > ty + 1e-9:
                continue
        else:
            inv = 1.0 / dey
            t1 = (fy - pey) * inv
            t2 = (ty - pey) * inv
            f_near = 0
            if dey < 0:  # entering through the max side (also correct for zero-thickness planes)
                t1, t2 = t2, t1
                f_near = 1
            if t1 > tn:
                tn = t1
                face = f_near
            if t2 < tf:
                tf = t2
        if abs(dez) < 1e-12:
            if pez < fz - 1e-9 or pez > tz + 1e-9:
                continue
        else:
            inv = 1.0 / dez
            t1 = (fz - pez) * inv
            t2 = (tz - pez) * inv
            f_near = 2
            if dez < 0:  # entering through the max side (also correct for zero-thickness planes)
                t1, t2 = t2, t1
                f_near = 3
            if t1 > tn:
                tn = t1
                face = f_near
            if t2 < tf:
                tf = t2
        if face < 0 or tn > tf + 1e-9 or tn < t_lo - 1e-6 or tn > t_hi + 1e-6 or tn > best_t + 1e-7:
            continue
        fidx = el_face[e, face]
        if fidx < 0:
            continue
        # face normal in world space: A^T n_elem
        nex, ney, nez = _face_normal(face)
        wnx = A[0, 0] * nex + A[1, 0] * ney + A[2, 0] * nez
        wny = A[0, 1] * nex + A[1, 1] * ney + A[2, 1] * nez
        wnz = A[0, 2] * nex + A[1, 2] * ney + A[2, 2] * nez
        ln = math.sqrt(wnx * wnx + wny * wny + wnz * wnz)
        if ln > 0:
            wnx /= ln
            wny /= ln
            wnz /= ln
        # cull faces toward opaque neighbors / same translucent block
        cdir = fc_cull[fidx]
        if liquid:
            # liquid box faces: cull toward same liquid or opaque full blocks
            ax = abs(wnx)
            ay = abs(wny)
            if ay > 0.5:
                cdir = 1 if wny > 0 else 0
            elif ax > 0.5:
                cdir = 5 if wnx > 0 else 4
            else:
                cdir = 3 if wnz > 0 else 2
            if cdir == 1 and not same_above:
                cdir = -2  # top surface never culled
        if cdir >= 0:
            ox_, oy_, oz_ = _face_offset(cdir)
            nsid = _state_at(vox, cx + ox_, cy + oy_, cz + oz_, y_cut)
            if (st_flags[nsid] & F_OCC) != 0:
                continue
            if nsid == sid and (flags & (F_SELF_CULL | F_LIQUID)) != 0:
                continue
        # texture coordinates
        hx = pex + dex * tn
        hy = pey + dey * tn
        hz = pez + dez * tn
        tid = fc_tex[fidx]
        if (el_flags[e] & 2) != 0 or liquid:
            # world-locked uv: from block-local world position of the hit
            lx = lox + dx * tn
            ly = loy + dy * tn
            lz = loz + dz * tn
            wf = face
            if abs(wny) > 0.9:
                wf = 1 if wny > 0 else 0
            elif abs(wnx) > 0.9:
                wf = 5 if wnx > 0 else 4
            elif abs(wnz) > 0.9:
                wf = 3 if wnz > 0 else 2
            u, v = _world_uv(wf, min(max(lx, 0.0), 0.99999), min(max(ly, 0.0), 0.99999),
                             min(max(lz, 0.0), 0.99999))
        else:
            s, t = _face_st(face, hx, hy, hz, fx, fy, fz, tx, ty, tz)
            s, t = _rot_st(s, t, fc_rot[fidx])
            u = (fc_uv[fidx, 0] + (fc_uv[fidx, 2] - fc_uv[fidx, 0]) * s) / 16.0
            v = (fc_uv[fidx, 1] + (fc_uv[fidx, 3] - fc_uv[fidx, 1]) * t) / 16.0
        r, g, b, a = _sample(tex_data, tex_off, tex_w, tex_h, tid, u, v)
        mode = tex_mode[tid]
        if mode == T_CUTOUT or (mode == T_TRANSLUCENT and shadow_mode):
            if a < 0.5:
                continue
        elif mode == T_TRANSLUCENT and a < 0.02:
            continue
        tint = fc_tint[fidx]
        if tint > 0:
            if tint <= 3:
                tr = tints[tint - 1, 0]
                tg = tints[tint - 1, 1]
                tb = tints[tint - 1, 2]
            else:
                tr = fixed_tints[tint - 4, 0]
                tg = fixed_tints[tint - 4, 1]
                tb = fixed_tints[tint - 4, 2]
            r *= tr
            g *= tg
            b *= tb
        # nearer hit wins; on a tie the later element wins (overlays such as grass block sides)
        if tn < best_t - 1e-7 or abs(tn - best_t) <= 1e-7:
            best_t = tn
            br = r
            bg = g
            bb = b
            ba = a if mode != 0 else 1.0
            bnx = wnx
            bny = wny
            bnz = wnz
            bmode = mode
            bshade = el_flags[e] & 1
            baxis = abs(wnx) > 0.99 or abs(wny) > 0.99 or abs(wnz) > 0.99
    if best_t >= INF:
        return False, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 1, False
    if liquid:
        bmode = T_TRANSLUCENT
        if (flags & F_WATER) != 0:
            ba = 0.62
        else:
            ba = 1.0
            bmode = 0
    return True, best_t, br, bg, bb, ba, bnx, bny, bnz, bmode, bshade, baxis


@njit(cache=True, fastmath=True)
def _light_at(arr, x, y, z):
    sx, sy, sz = arr.shape
    if x < 0 or y < 0 or z < 0 or x >= sx or z >= sz:
        return 15.0
    if y >= sy:
        return 15.0
    return float(arr[x, y, z])


@njit(cache=True, fastmath=True)
def _mc_bright(level):
    """Game-like light curve (lightmap at 50% brightness): level 0..15 -> 0.04..1."""
    f = level / 15.0
    if f < 0.0:
        f = 0.0
    b = f / (4.0 - 3.0 * f)
    g = 1.0 - (1.0 - b) ** 4
    return (b + (g - b) * 0.5) * 0.96 + 0.04


@njit(cache=True, fastmath=True)
def _simple_light(px, py, pz, nx, ny, nz, block_light, sky_light, lp, sunx, suny, sunz):
    """Lighting without shadows/AO (used for translucent layers such as water and glass)."""
    fx = int(math.floor(px + nx * 0.5))
    fy = int(math.floor(py + ny * 0.5))
    fz = int(math.floor(pz + nz * 0.5))
    skyf = _mc_bright(_light_at(sky_light, fx, fy, fz))
    blk = _light_at(block_light, fx, fy, fz)
    ndl = nx * sunx + ny * suny + nz * sunz
    if ndl < 0:
        ndl = 0.0
    bl = (_mc_bright(blk) if blk > 0 else 0.0) * lp[5]
    lr = lp[0] * lp[6] * skyf + lp[1] * ndl * lp[2] + bl
    lg = lp[0] * lp[7] * skyf + lp[1] * ndl * lp[3] + bl * 0.82
    lb = lp[0] * lp[8] * skyf + lp[1] * ndl * lp[4] + bl * 0.6
    return lr, lg, lb


@njit(cache=True, fastmath=True)
def _ray_box(ox, oy, oz, dx, dy, dz, sx, sy, sz):
    tn = -INF
    tf = INF
    for axis in range(3):
        if axis == 0:
            o = ox
            d = dx
            s = sx
        elif axis == 1:
            o = oy
            d = dy
            s = sy
        else:
            o = oz
            d = dz
            s = sz
        if abs(d) < 1e-12:
            if o < 0 or o > s:
                return INF, -INF
        else:
            t1 = (0.0 - o) / d
            t2 = (s - o) / d
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > tn:
                tn = t1
            if t2 < tf:
                tf = t2
    return tn, tf


@njit(cache=True, fastmath=True)
def _trace(vox, ox, oy, oz, dx, dy, dz, y_cut, max_t,
           st_var_start, st_var_count, st_flags, st_height, var_elem_start, var_elem_count, var_weight,
           el_A, el_b, el_from, el_to, el_face, el_flags, fc_tex, fc_uv, fc_rot, fc_tint, fc_cull,
           tex_off, tex_w, tex_h, tex_mode, tex_data, bio, tint_table, fixed_tints, shadow_mode,
           block_light, sky_light, lp, sunx, suny, sunz):
    """First opaque hit (with translucent layers collected).

    Returns (hit, t, r, g, b, nx, ny, nz, cell x, y, z, sid, shade, axis_aligned, trans_r, trans_g, trans_b,
    transmittance, water_depth)
    """
    sx, sy, sz = vox.shape
    tn, tf = _ray_box(ox, oy, oz, dx, dy, dz, sx, sy, sz)
    acc_r = 0.0
    acc_g = 0.0
    acc_b = 0.0
    T = 1.0
    water_depth = 0.0
    if tn > tf or tf < 0:
        return False, INF, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 1, False, acc_r, acc_g, acc_b, T, water_depth
    t = max(tn, 0.0) + 1e-6
    if tf > max_t:
        tf = max_t
    px = ox + dx * t
    py = oy + dy * t
    pz = oz + dz * t
    cx = int(math.floor(px))
    cy = int(math.floor(py))
    cz = int(math.floor(pz))
    if cx >= sx:
        cx = sx - 1
    if cy >= sy:
        cy = sy - 1
    if cz >= sz:
        cz = sz - 1
    if cx < 0:
        cx = 0
    if cy < 0:
        cy = 0
    if cz < 0:
        cz = 0
    stx = 1 if dx > 0 else -1
    sty = 1 if dy > 0 else -1
    stz = 1 if dz > 0 else -1
    tdx = abs(1.0 / dx) if abs(dx) > 1e-12 else INF
    tdy = abs(1.0 / dy) if abs(dy) > 1e-12 else INF
    tdz = abs(1.0 / dz) if abs(dz) > 1e-12 else INF
    if abs(dx) > 1e-12:
        tmx = ((cx + (1 if dx > 0 else 0)) - ox) / dx
    else:
        tmx = INF
    if abs(dy) > 1e-12:
        tmy = ((cy + (1 if dy > 0 else 0)) - oy) / dy
    else:
        tmy = INF
    if abs(dz) > 1e-12:
        tmz = ((cz + (1 if dz > 0 else 0)) - oz) / dz
    else:
        tmz = INF
    t_enter = t
    in_water_sid = -1
    buried = 0
    for _ in range(4 * (sx + sy + sz) + 8):
        t_exit = min(tmx, tmy, tmz)
        if cy <= y_cut:
            sid = vox[cx, cy, cz]
        else:
            sid = 0
        if sid != 0 and (st_flags[sid] & F_INVISIBLE) == 0:
            tint_row = bio[cx, cz]
            hit, th, r, g, b, a, nx, ny, nz, mode, shade, aligned = _hit_cell(
                vox, cx, cy, cz, sid, ox, oy, oz, dx, dy, dz, t_enter, t_exit, y_cut,
                st_var_start, st_var_count, st_flags, st_height, var_elem_start, var_elem_count, var_weight,
                el_A, el_b, el_from, el_to, el_face, el_flags, fc_tex, fc_uv, fc_rot, fc_tint, fc_cull,
                tex_off, tex_w, tex_h, tex_mode, tex_data, tint_table[tint_row], fixed_tints, shadow_mode)
            if hit:
                if mode == T_TRANSLUCENT:
                    if shadow_mode:
                        T *= (1.0 - a * 0.7)
                    else:
                        hx = ox + dx * th
                        hy = oy + dy * th
                        hz = oz + dz * th
                        lr, lg, lb = _simple_light(hx, hy, hz, nx, ny, nz, block_light, sky_light, lp, sunx, suny, sunz)
                        acc_r += T * a * r * lr
                        acc_g += T * a * g * lg
                        acc_b += T * a * b * lb
                        T *= (1.0 - a)
                    if (st_flags[sid] & F_WATER) != 0:
                        in_water_sid = sid
                    if T < 0.02:
                        return True, th, 0.0, 0.0, 0.0, nx, ny, nz, cx, cy, cz, sid, shade, aligned, acc_r, acc_g, acc_b, 0.0, water_depth
                else:
                    return True, th, r, g, b, nx, ny, nz, cx, cy, cz, sid, shade, aligned, acc_r, acc_g, acc_b, T, water_depth
            if in_water_sid >= 0 and sid == in_water_sid:
                water_depth += (t_exit - t_enter)
            if (st_flags[sid] & F_OCC) != 0 and not hit:
                # travelling inside solid blocks (camera underground): stop, render as dark rock
                buried += 1
                if buried > 1:
                    return True, t_enter, 0.03, 0.03, 0.035, 0.0, 1.0, 0.0, cx, cy, cz, sid, 0, False, acc_r, acc_g, acc_b, T, water_depth
        # advance
        if t_exit > tf:
            break
        t_enter = t_exit
        if tmx < tmy:
            if tmx < tmz:
                cx += stx
                tmx += tdx
            else:
                cz += stz
                tmz += tdz
        else:
            if tmy < tmz:
                cy += sty
                tmy += tdy
            else:
                cz += stz
                tmz += tdz
        if cx < 0 or cy < 0 or cz < 0 or cx >= sx or cy >= sy or cz >= sz:
            break
    return False, INF, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 1, False, acc_r, acc_g, acc_b, T, water_depth


@njit(cache=True, fastmath=True)
def _hit_entities(wox, woy, woz, dx, dy, dz, t_max, ent_A, ent_b, ent_from, ent_to, ent_face, ent_flags, ent_aabb,
                  fc_tex, fc_uv, fc_rot, fc_tint, tex_off, tex_w, tex_h, tex_mode, tex_data, fixed_tints):
    """Nearest display-entity texel along a world-space ray, closer than t_max."""
    n = ent_A.shape[0]
    best_t = t_max
    found = False
    br = 0.0
    bg = 0.0
    bb = 0.0
    ba = 0.0
    bnx = 0.0
    bny = 1.0
    bnz = 0.0
    bflags = 0
    for e in range(n):
        # world AABB reject
        tn0 = -INF
        tf0 = INF
        miss = False
        for axis in range(3):
            if axis == 0:
                o = wox
                d = dx
            elif axis == 1:
                o = woy
                d = dy
            else:
                o = woz
                d = dz
            lo = ent_aabb[e, axis] - 1e-4
            hi = ent_aabb[e, axis + 3] + 1e-4
            if abs(d) < 1e-12:
                if o < lo or o > hi:
                    miss = True
                    break
            else:
                t1 = (lo - o) / d
                t2 = (hi - o) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                if t1 > tn0:
                    tn0 = t1
                if t2 < tf0:
                    tf0 = t2
        if miss or tn0 > tf0 or tf0 < 0 or tn0 > best_t:
            continue
        A = ent_A[e]
        bv = ent_b[e]
        pex = A[0, 0] * wox + A[0, 1] * woy + A[0, 2] * woz + bv[0]
        pey = A[1, 0] * wox + A[1, 1] * woy + A[1, 2] * woz + bv[1]
        pez = A[2, 0] * wox + A[2, 1] * woy + A[2, 2] * woz + bv[2]
        dex = A[0, 0] * dx + A[0, 1] * dy + A[0, 2] * dz
        dey = A[1, 0] * dx + A[1, 1] * dy + A[1, 2] * dz
        dez = A[2, 0] * dx + A[2, 1] * dy + A[2, 2] * dz
        fx = ent_from[e, 0]
        fy = ent_from[e, 1]
        fz = ent_from[e, 2]
        tx = ent_to[e, 0]
        ty = ent_to[e, 1]
        tz = ent_to[e, 2]
        tn = -INF
        tf = INF
        face = -1
        ok = True
        for axis in range(3):
            if axis == 0:
                o = pex
                d = dex
                lo = fx
                hi = tx
                fl = 4
                fh = 5
            elif axis == 1:
                o = pey
                d = dey
                lo = fy
                hi = ty
                fl = 0
                fh = 1
            else:
                o = pez
                d = dez
                lo = fz
                hi = tz
                fl = 2
                fh = 3
            if abs(d) < 1e-12:
                if o < lo - 1e-9 or o > hi + 1e-9:
                    ok = False
                    break
            else:
                t1 = (lo - o) / d
                t2 = (hi - o) / d
                fn = fl
                if d < 0:
                    t1, t2 = t2, t1
                    fn = fh
                if t1 > tn:
                    tn = t1
                    face = fn
                if t2 < tf:
                    tf = t2
        if not ok or face < 0 or tn > tf + 1e-9 or tn < 0 or tn >= best_t:
            continue
        fidx = ent_face[e, face]
        if fidx < 0:
            continue
        hx = pex + dex * tn
        hy = pey + dey * tn
        hz = pez + dez * tn
        s, t = _face_st(face, hx, hy, hz, fx, fy, fz, tx, ty, tz)
        s, t = _rot_st(s, t, fc_rot[fidx])
        u = (fc_uv[fidx, 0] + (fc_uv[fidx, 2] - fc_uv[fidx, 0]) * s) / 16.0
        v = (fc_uv[fidx, 1] + (fc_uv[fidx, 3] - fc_uv[fidx, 1]) * t) / 16.0
        tid = fc_tex[fidx]
        r, g, b, a = _sample(tex_data, tex_off, tex_w, tex_h, tid, u, v)
        if tex_mode[tid] == T_CUTOUT and a < 0.5:
            continue
        if a < 0.05:
            continue
        tint = fc_tint[fidx]
        if tint > 3:
            r *= fixed_tints[tint - 4, 0]
            g *= fixed_tints[tint - 4, 1]
            b *= fixed_tints[tint - 4, 2]
        nex, ney, nez = _face_normal(face)
        wnx = A[0, 0] * nex + A[1, 0] * ney + A[2, 0] * nez
        wny = A[0, 1] * nex + A[1, 1] * ney + A[2, 1] * nez
        wnz = A[0, 2] * nex + A[1, 2] * ney + A[2, 2] * nez
        ln = math.sqrt(wnx * wnx + wny * wny + wnz * wnz)
        if ln > 0:
            wnx /= ln
            wny /= ln
            wnz /= ln
        best_t = tn
        found = True
        br = r
        bg = g
        bb = b
        ba = a if tex_mode[tid] == T_TRANSLUCENT else 1.0
        bnx = wnx
        bny = wny
        bnz = wnz
        bflags = ent_flags[e]
    return found, best_t, br, bg, bb, ba, bnx, bny, bnz, bflags


@njit(cache=True, fastmath=True)
def _occ(vox, st_flags, x, y, z, y_cut):
    sid = _state_at(vox, x, y, z, y_cut)
    return 1 if (st_flags[sid] & F_OCC) != 0 else 0


@njit(cache=True, fastmath=True)
def _vao(s1, s2, c):
    if s1 == 1 and s2 == 1:
        return 0.0
    return 3.0 - (s1 + s2 + c)


@njit(cache=True, fastmath=True)
def _ambient_occlusion(vox, st_flags, px, py, pz, nx, ny, nz, y_cut):
    # cell in front of the face
    fx = int(math.floor(px + nx * 0.02))
    fy = int(math.floor(py + ny * 0.02))
    fz = int(math.floor(pz + nz * 0.02))
    if abs(ny) > 0.9:
        a1 = (1, 0, 0)
        a2 = (0, 0, 1)
        f1 = px - math.floor(px)
        f2 = pz - math.floor(pz)
    elif abs(nx) > 0.9:
        a1 = (0, 1, 0)
        a2 = (0, 0, 1)
        f1 = py - math.floor(py)
        f2 = pz - math.floor(pz)
    else:
        a1 = (1, 0, 0)
        a2 = (0, 1, 0)
        f1 = px - math.floor(px)
        f2 = py - math.floor(py)
    s1m = _occ(vox, st_flags, fx - a1[0], fy - a1[1], fz - a1[2], y_cut)
    s1p = _occ(vox, st_flags, fx + a1[0], fy + a1[1], fz + a1[2], y_cut)
    s2m = _occ(vox, st_flags, fx - a2[0], fy - a2[1], fz - a2[2], y_cut)
    s2p = _occ(vox, st_flags, fx + a2[0], fy + a2[1], fz + a2[2], y_cut)
    cmm = _occ(vox, st_flags, fx - a1[0] - a2[0], fy - a1[1] - a2[1], fz - a1[2] - a2[2], y_cut)
    cpm = _occ(vox, st_flags, fx + a1[0] - a2[0], fy + a1[1] - a2[1], fz + a1[2] - a2[2], y_cut)
    cmp_ = _occ(vox, st_flags, fx - a1[0] + a2[0], fy - a1[1] + a2[1], fz - a1[2] + a2[2], y_cut)
    cpp = _occ(vox, st_flags, fx + a1[0] + a2[0], fy + a1[1] + a2[1], fz + a1[2] + a2[2], y_cut)
    amm = _vao(s1m, s2m, cmm)
    apm = _vao(s1p, s2m, cpm)
    amp = _vao(s1m, s2p, cmp_)
    app = _vao(s1p, s2p, cpp)
    a = (amm * (1 - f1) + apm * f1) * (1 - f2) + (amp * (1 - f1) + app * f1) * f2
    return a / 3.0


@njit(cache=True, fastmath=True)
def _sky_color(dx, dy, dz, env):
    # env: [mode, sun_x, sun_y, sun_z, flat_r, flat_g, flat_b, ...]
    mode = int(env[0])
    if mode == 1:  # flat studio background
        return env[4], env[5], env[6]
    e = max(-1.0, min(1.0, dy))
    if mode == 3:  # night
        base_r = 0.02 + 0.03 * (1 - e)
        base_g = 0.03 + 0.04 * (1 - e)
        base_b = 0.08 + 0.08 * (1 - e)
        h = _hash3(int(dx * 900), int(dy * 900), int(dz * 900))
        if e > 0.05 and h > 0.9985:
            return 0.9, 0.9, 1.0
        return base_r, base_g, base_b
    if mode == 2:  # sunset
        hr, hg, hb = 1.0, 0.62, 0.38
        zr, zg, zb = 0.28, 0.36, 0.62
    else:
        hr, hg, hb = 0.78, 0.87, 1.0
        zr, zg, zb = 0.40, 0.62, 0.98
    k = max(0.0, e) ** 0.6
    r = hr * (1 - k) + zr * k
    g = hg * (1 - k) + zg * k
    b = hb * (1 - k) + zb * k
    if e < 0:
        f = min(1.0, -e * 3)
        r = r * (1 - f) + 0.55 * f
        g = g * (1 - f) + 0.62 * f
        b = b * (1 - f) + 0.72 * f
    sd = dx * env[1] + dy * env[2] + dz * env[3]
    if sd > 0.9995:
        return 1.6, 1.5, 1.3
    if sd > 0.97:
        glow = (sd - 0.97) / 0.03
        r += 0.25 * glow
        g += 0.2 * glow
        b += 0.1 * glow
    return r, g, b


@njit(cache=True, fastmath=True)
def _pixel(i, j, width, height, ss, cam, env, light_params, vox, y_cut, highlight,
           st_var_start, st_var_count, st_flags, st_height, st_emit, var_elem_start, var_elem_count,
           var_weight, el_A, el_b, el_from, el_to, el_face, el_flags, fc_tex, fc_uv, fc_rot, fc_tint, fc_cull,
           tex_off, tex_w, tex_h, tex_mode, tex_data, bio, tint_table, fixed_tints, block_light, sky_light,
           ent_A, ent_b, ent_from, ent_to, ent_face, ent_flags, ent_aabb):
    mode = int(cam[0])
    ex, ey, ez = cam[1], cam[2], cam[3]
    fwx, fwy, fwz = cam[4], cam[5], cam[6]
    rtx, rty, rtz = cam[7], cam[8], cam[9]
    upx, upy, upz = cam[10], cam[11], cam[12]
    aspect = width / height
    max_t = cam[15]
    sunx, suny, sunz = env[1], env[2], env[3]
    fog_dist = env[7]
    amb = light_params[0]
    sun_k = light_params[1]
    blk_k = light_params[5]
    do_shadow = light_params[9] > 0.5
    do_ao = light_params[10] > 0.5
    cr = 0.0
    cg = 0.0
    cb = 0.0
    dmin = INF
    for sj in range(ss):
        for si in range(ss):
            u = (i + (si + 0.5) / ss) / width * 2.0 - 1.0
            v = 1.0 - (j + (sj + 0.5) / ss) / height * 2.0
            if mode == 0:
                th = math.tan(cam[13] * 0.5)
                dx = fwx + (u * th * aspect) * rtx + (v * th) * upx
                dy = fwy + (u * th * aspect) * rty + (v * th) * upy
                dz = fwz + (u * th * aspect) * rtz + (v * th) * upz
                ln = math.sqrt(dx * dx + dy * dy + dz * dz)
                dx /= ln
                dy /= ln
                dz /= ln
                ox, oy, oz = ex, ey, ez
            else:
                hw = cam[13]
                hh = cam[14]
                ox = ex + u * hw * rtx + v * hh * upx
                oy = ey + u * hw * rty + v * hh * upy
                oz = ez + u * hw * rtz + v * hh * upz
                dx, dy, dz = fwx, fwy, fwz
            hit, t, r, g, b, nx, ny, nz, cx, cy, cz, sid, shade, aligned, ar, ag, ab, T, wdepth = _trace(
                vox, ox, oy, oz, dx, dy, dz, y_cut, max_t,
                st_var_start, st_var_count, st_flags, st_height, var_elem_start, var_elem_count, var_weight,
                el_A, el_b, el_from, el_to, el_face, el_flags, fc_tex, fc_uv, fc_rot, fc_tint, fc_cull,
                tex_off, tex_w, tex_h, tex_mode, tex_data, bio, tint_table, fixed_tints, False,
                block_light, sky_light, light_params, sunx, suny, sunz)
            if hit and T > 0.0:
                px = ox + dx * t
                py = oy + dy * t
                pz = oz + dz * t
                # light levels in the cell in front of the face
                fx = int(math.floor(px + nx * 0.5))
                fy = int(math.floor(py + ny * 0.5))
                fz = int(math.floor(pz + nz * 0.5))
                skyf = _mc_bright(_light_at(sky_light, fx, fy, fz))
                blk_level = _light_at(block_light, fx, fy, fz)
                emit = st_emit[sid] / 15.0
                fshade = 1.0
                if shade == 1:
                    if ny > 0.5:
                        fshade = 1.0
                    elif ny < -0.5:
                        fshade = 0.55
                    elif abs(nz) > 0.5:
                        fshade = 0.82
                    else:
                        fshade = 0.68
                ao = 1.0
                if do_ao and aligned:
                    ao = 0.52 + 0.48 * _ambient_occlusion(vox, st_flags, px, py, pz, nx, ny, nz, y_cut)
                direct = 0.0
                ndl = nx * sunx + ny * suny + nz * sunz
                if sun_k > 0 and ndl > 0:
                    vis = 1.0
                    if do_shadow:
                        sh = _trace(vox, px + nx * 1e-3, py + ny * 1e-3, pz + nz * 1e-3, sunx, suny, sunz,
                                    y_cut, max_t, st_var_start, st_var_count, st_flags, st_height,
                                    var_elem_start, var_elem_count, var_weight, el_A, el_b, el_from, el_to,
                                    el_face, el_flags, fc_tex, fc_uv, fc_rot, fc_tint, fc_cull, tex_off,
                                    tex_w, tex_h, tex_mode, tex_data, bio, tint_table, fixed_tints, True,
                                    block_light, sky_light, light_params, sunx, suny, sunz)
                        if sh[0]:
                            vis = 0.0
                        else:
                            vis = sh[17]
                    direct = sun_k * ndl * vis
                lr = (amb * light_params[6] * skyf * fshade * ao + direct * light_params[2])
                lg = (amb * light_params[7] * skyf * fshade * ao + direct * light_params[3])
                lb = (amb * light_params[8] * skyf * fshade * ao + direct * light_params[4])
                bl = (_mc_bright(blk_level) if blk_level > 0 else 0.0) * blk_k
                lr += bl * 1.0 * ao
                lg += bl * 0.82 * ao
                lb += bl * 0.6 * ao
                if emit > 0:
                    e2 = emit * 0.95
                    if lr < e2:
                        lr = e2
                    if lg < e2:
                        lg = e2
                    if lb < e2:
                        lb = e2
                r *= lr
                g *= lg
                b *= lb
                if highlight.shape[0] > 1 and highlight[cx, cy, cz] != 0:
                    r = r * 0.45 + 0.55 * 1.0
                    g = g * 0.45 + 0.55 * 0.15
                    b = b * 0.45 + 0.55 * 0.85
                if wdepth > 0:
                    k = math.exp(-wdepth * 0.28)
                    r = r * k + (1 - k) * 0.05
                    g = g * k + (1 - k) * 0.16 * (amb + sun_k)
                    b = b * k + (1 - k) * 0.28 * (amb + sun_k)
                r = ar + T * r
                g = ag + T * g
                b = ab + T * b
                dist = t
            else:
                sr, sg, sb = _sky_color(dx, dy, dz, env)
                if hit:
                    r, g, b = ar, ag, ab
                    dist = t
                else:
                    r = ar + T * sr
                    g = ag + T * sg
                    b = ab + T * sb
                    dist = INF
            if ent_A.shape[0] > 0:
                ehit, et, er, eg, eb, ea, enx, eny, enz, eflags = _hit_entities(
                    ox + env[8], oy + env[9], oz + env[10], dx, dy, dz, dist, ent_A, ent_b, ent_from, ent_to,
                    ent_face, ent_flags, ent_aabb, fc_tex, fc_uv, fc_rot, fc_tint, tex_off, tex_w, tex_h, tex_mode,
                    tex_data, fixed_tints)
                if ehit:
                    if (eflags & 8) != 0:
                        lr = lg = lb = 1.0  # text displays are readable (full bright)
                    else:
                        hx = ox + dx * et
                        hy = oy + dy * et
                        hz = oz + dz * et
                        lr, lg, lb = _simple_light(hx, hy, hz, enx, eny, enz, block_light, sky_light, light_params,
                                                   sunx, suny, sunz)
                    er *= lr
                    eg *= lg
                    eb *= lb
                    r = r * (1 - ea) + er * ea
                    g = g * (1 - ea) + eg * ea
                    b = b * (1 - ea) + eb * ea
                    if ea > 0.5:
                        dist = et
            if fog_dist > 0 and dist < INF:
                f = 1.0 - math.exp(-(dist / fog_dist) ** 2)
                sr, sg, sb = _sky_color(dx, max(dy, 0.02), dz, env)
                r = r * (1 - f) + sr * f
                g = g * (1 - f) + sg * f
                b = b * (1 - f) + sb * f
            cr += r
            cg += g
            cb += b
            if dist < dmin:
                dmin = dist
    n = ss * ss
    return cr / n, cg / n, cb / n, dmin


@njit(cache=True, nogil=True)
def render_rows(y0, y1, img, depth, width, height, ss, cam, env, light_params, vox, y_cut, highlight,
                st_var_start, st_var_count, st_flags, st_height, st_emit, var_elem_start, var_elem_count,
                var_weight, el_A, el_b, el_from, el_to, el_face, el_flags, fc_tex, fc_uv, fc_rot, fc_tint, fc_cull,
                tex_off, tex_w, tex_h, tex_mode, tex_data, bio, tint_table, fixed_tints, block_light, sky_light,
                ent_A, ent_b, ent_from, ent_to, ent_face, ent_flags, ent_aabb):
    """Render rows [y0, y1) into img/depth (called from several threads; releases the GIL)."""
    for j in range(y0, y1):
        for i in range(width):
            r, g, b, d = _pixel(i, j, width, height, ss, cam, env, light_params, vox, y_cut, highlight,
                                st_var_start, st_var_count, st_flags, st_height, st_emit, var_elem_start,
                                var_elem_count, var_weight, el_A, el_b, el_from, el_to, el_face, el_flags, fc_tex,
                                fc_uv, fc_rot, fc_tint, fc_cull, tex_off, tex_w, tex_h, tex_mode, tex_data, bio,
                                tint_table, fixed_tints, block_light, sky_light, ent_A, ent_b, ent_from, ent_to,
                                ent_face, ent_flags, ent_aabb)
            img[j, i, 0] = r
            img[j, i, 1] = g
            img[j, i, 2] = b
            depth[j, i] = d


def render_kernel(width, height, ss, cam, env, light_params, vox, y_cut, highlight, *tables):
    """cam: [mode(0 persp, 1 ortho), ex, ey, ez, fx, fy, fz, rx, ry, rz, ux, uy, uz, fov_or_halfw, halfh, max_t]
    env: [sky_mode, sun_x, sun_y, sun_z, flat_r, flat_g, flat_b, fog_dist, grid_origin_x, grid_origin_y, grid_origin_z]
    light_params: [ambient, sun_strength, sun_r, sun_g, sun_b, block_strength, amb_r, amb_g, amb_b, shadows, ao]
    """
    import os
    from concurrent.futures import ThreadPoolExecutor

    img = np.zeros((height, width, 3), np.float32)
    depth = np.full((height, width), np.float32(INF), np.float32)
    workers = max(1, min(32, os.cpu_count() or 1))
    band = max(1, min(16, height // (workers * 4) or 1))
    jobs = [(y, min(height, y + band)) for y in range(0, height, band)]

    def run(job):
        render_rows(job[0], job[1], img, depth, width, height, ss, cam, env, light_params, vox, y_cut, highlight,
                    *tables)

    # compile/load once in this thread before fanning out
    run(jobs[0])
    if len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(run, jobs[1:]))
    return img, depth
