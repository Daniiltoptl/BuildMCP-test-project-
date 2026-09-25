"""Compile block states into flat numeric tables for the ray tracer.

Every visible block state becomes one or more *variants* (weighted random models, like
the game's randomly rotated grass/stone), each a list of *elements* (boxes from the
block model JSON). Each element stores the affine map world-local -> element space
(block-state x/y rotation, element rotation and rescale) so the tracer can intersect it
as an axis-aligned box and compute exact texture coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..blocks.registry import parse_state
from .assets import AssetStore
from .biomes import FIXED_TINTS, FOLIAGE_TINTED, GRASS_TINTED, WATER_TINTED

# face index order used everywhere in the renderer
FACES = ("down", "up", "north", "south", "west", "east")
FACE_IDX = {f: i for i, f in enumerate(FACES)}
FACE_NORMALS = np.array([[0, -1, 0], [0, 1, 0], [0, 0, -1], [0, 0, 1], [-1, 0, 0], [1, 0, 0]], dtype=np.float64)

INVISIBLE = {"air", "cave_air", "void_air", "barrier", "light", "structure_void", "moving_piston"}

# state flags
F_OCC = 1  # full opaque cube: blocks light, occludes AO
F_SELF_CULL = 2  # faces between identical blocks are hidden (glass, ice)
F_WATER = 4
F_LAVA = 8
F_INVISIBLE = 16
F_LIQUID = 32

# texture modes
T_OPAQUE, T_CUTOUT, T_TRANSLUCENT = 0, 1, 2


@dataclass
class Tables:
    st_var_start: np.ndarray
    st_var_count: np.ndarray
    st_flags: np.ndarray
    st_emit: np.ndarray
    st_filter: np.ndarray
    st_height: np.ndarray  # liquid surface height (0..1)
    var_elem_start: np.ndarray
    var_elem_count: np.ndarray
    var_weight: np.ndarray  # cumulative weight within the state's variants (0..1]
    el_A: np.ndarray
    el_b: np.ndarray
    el_from: np.ndarray
    el_to: np.ndarray
    el_face: np.ndarray
    el_flags: np.ndarray  # bit0 shade, bit1 uvlock, bit2 liquid
    fc_tex: np.ndarray
    fc_uv: np.ndarray
    fc_rot: np.ndarray
    fc_tint: np.ndarray
    fc_cull: np.ndarray
    tex_off: np.ndarray
    tex_w: np.ndarray
    tex_h: np.ndarray
    tex_mode: np.ndarray
    tex_data: np.ndarray
    fixed_tints: np.ndarray
    ents: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


# ------------------------------------------------------------------ math helpers
def _rot_matrix(axis: str, deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def state_rotation(x_deg: float, y_deg: float) -> np.ndarray:
    """Game convention: rotateYXZ(-y, -x): x first, then y (clockwise seen from above)."""
    return _rot_matrix("y", -y_deg) @ _rot_matrix("x", -x_deg)


def element_affine(el: dict, rs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A, b such that p_elem = A @ p_worldlocal + b (all in block units 0..1)."""
    c = np.array([0.5, 0.5, 0.5])
    r = el.get("rotation")
    if r and float(r.get("angle", 0)) != 0:
        axis = r.get("axis", "y")
        ang = float(r["angle"])
        o = np.array(r.get("origin", [8, 8, 8]), dtype=np.float64) / 16.0
        re = _rot_matrix(axis, ang)
        s = np.ones(3)
        if r.get("rescale"):
            k = 1.0 / math.cos(math.radians(abs(ang)))
            for i, ax in enumerate("xyz"):
                if ax != axis:
                    s[i] = k
        # p_model = o + Re S (p_elem - o)  =>  p_elem = o + S^-1 Re^-1 (p_model - o)
        m_inv = np.diag(1.0 / s) @ re.T
        o_e = o
    else:
        m_inv = np.eye(3)
        o_e = c
    # p_worldlocal = c + Rs (p_model - c)  =>  p_model = c + Rs^T (p_wl - c)
    a_mat = m_inv @ rs.T
    b_vec = o_e + m_inv @ (c - rs.T @ c - o_e)
    return a_mat, b_vec


# ------------------------------------------------------------------ compiler
class _Builder:
    def __init__(self, assets: AssetStore):
        self.assets = assets
        self.textures: list[np.ndarray] = []
        self.tex_index: dict[str, int] = {}
        self.tex_modes: list[int] = []
        self.var_elem_start: list[int] = []
        self.var_elem_count: list[int] = []
        self.var_weight: list[float] = []
        self.el_A: list[np.ndarray] = []
        self.el_b: list[np.ndarray] = []
        self.el_from: list[np.ndarray] = []
        self.el_to: list[np.ndarray] = []
        self.el_face: list[list[int]] = []
        self.el_flags: list[int] = []
        self.fc_tex: list[int] = []
        self.fc_uv: list[list[float]] = []
        self.fc_rot: list[int] = []
        self.fc_tint: list[int] = []
        self.fc_cull: list[int] = []
        self.fixed_tints: list[tuple[float, float, float]] = []
        self.fixed_index: dict[int, int] = {}
        self.model_cache: dict[str, tuple[list, dict]] = {}
        self.warnings: list[str] = []
        self._placeholder = self._make_placeholder()

    def _make_placeholder(self) -> int:
        a = np.zeros((16, 16, 4), np.uint8)
        a[..., 3] = 255
        a[::2, ::2, 0] = 255
        a[1::2, 1::2, 0] = 255
        a[::2, ::2, 2] = 255
        a[1::2, 1::2, 2] = 255
        return self._add_texture("__missing__", a)

    def _add_texture(self, key: str, arr: np.ndarray) -> int:
        idx = len(self.textures)
        self.textures.append(np.ascontiguousarray(arr, dtype=np.uint8))
        alpha = arr[..., 3]
        if alpha.min() == 255:
            mode = T_OPAQUE
        elif np.any((alpha > 8) & (alpha < 247)):
            mode = T_TRANSLUCENT
        else:
            mode = T_CUTOUT
        self.tex_modes.append(mode)
        self.tex_index[key] = idx
        return idx

    def texture(self, ref: str) -> int:
        ref = ref.removeprefix("minecraft:")
        if ref in self.tex_index:
            return self.tex_index[ref]
        arr = self.assets.texture(ref)
        if arr is None:
            self.warnings.append(f"missing texture {ref}")
            self.tex_index[ref] = self._placeholder
            return self._placeholder
        return self._add_texture(ref, arr)

    def fixed_tint(self, color: int) -> int:
        if color not in self.fixed_index:
            self.fixed_index[color] = len(self.fixed_tints)
            self.fixed_tints.append((((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255))
        return 4 + self.fixed_index[color]

    # -------------------------------------------------------------- models
    def resolve_model(self, ref: str) -> tuple[list, dict]:
        ref = ref.removeprefix("minecraft:")
        if "/" not in ref:
            ref = "block/" + ref
        hit = self.model_cache.get(ref)
        if hit is not None:
            return hit
        chain = []
        cur = ref
        for _ in range(16):
            m = self.assets.model(cur)
            if m is None:
                break
            chain.append(m)
            parent = m.get("parent")
            if not parent or parent.startswith("builtin/"):
                break
            cur = parent.removeprefix("minecraft:")
        textures: dict = {}
        elements = None
        for m in reversed(chain):
            textures.update(m.get("textures", {}))
        for m in chain:
            if "elements" in m:
                elements = m["elements"]
                break
        res = (elements or [], textures)
        self.model_cache[ref] = res
        return res

    @staticmethod
    def resolve_tex(name: str, textures: dict) -> str | None:
        seen = 0
        while name.startswith("#") and seen < 12:
            name = textures.get(name[1:], "")
            seen += 1
        if not name or name.startswith("#"):
            return None
        return name

    def add_elements(self, elements: list, textures: dict, x: float, y: float, uvlock: bool, tint_kind: int,
                     liquid: bool = False) -> int:
        rs = state_rotation(x, y)
        count = 0
        for el in elements:
            a_mat, b_vec = element_affine(el, rs)
            fr = np.array(el.get("from", [0, 0, 0]), dtype=np.float64) / 16.0
            to = np.array(el.get("to", [16, 16, 16]), dtype=np.float64) / 16.0
            faces = el.get("faces", {})
            face_ids = [-1] * 6
            for fname, fdata in faces.items():
                if fname not in FACE_IDX:
                    continue
                tex = self.resolve_tex(fdata.get("texture", ""), textures)
                if tex is None:
                    continue
                tid = self.texture(tex)
                uv = fdata.get("uv")
                if uv is None:
                    uv = _default_uv(fname, fr * 16, to * 16)
                tint = 0
                if "tintindex" in fdata:
                    tint = tint_kind
                cull = FACE_IDX.get(fdata.get("cullface", ""), -1)
                if cull >= 0:  # cull direction in world space (after the block-state rotation)
                    wn = rs @ FACE_NORMALS[cull]
                    cull = int(np.argmax(FACE_NORMALS @ wn))
                face_ids[FACE_IDX[fname]] = len(self.fc_tex)
                self.fc_tex.append(tid)
                self.fc_uv.append([float(v) for v in uv])
                self.fc_rot.append(int(fdata.get("rotation", 0)) // 90 % 4)
                self.fc_tint.append(tint)
                self.fc_cull.append(cull)
            if all(f < 0 for f in face_ids):
                continue
            self.el_A.append(a_mat)
            self.el_b.append(b_vec)
            self.el_from.append(fr)
            self.el_to.append(to)
            self.el_face.append(face_ids)
            flags = (1 if el.get("shade", True) else 0) | (2 if uvlock else 0) | (4 if liquid else 0)
            self.el_flags.append(flags)
            count += 1
        return count

    def add_variant(self, parts: list[tuple[list, dict, float, float, bool]], weight: float, tint_kind: int,
                    liquid: bool = False) -> None:
        start = len(self.el_A)
        n = 0
        for elements, textures, x, y, uvlock in parts:
            n += self.add_elements(elements, textures, x, y, uvlock, tint_kind, liquid)
        self.var_elem_start.append(start)
        self.var_elem_count.append(n)
        self.var_weight.append(weight)


def _default_uv(face: str, fr: np.ndarray, to: np.ndarray) -> list[float]:
    x1, y1, z1 = fr
    x2, y2, z2 = to
    return {
        "up": [x1, z1, x2, z2],
        "down": [x1, 16 - z2, x2, 16 - z1],
        "north": [16 - x2, 16 - y2, 16 - x1, 16 - y1],
        "south": [x1, 16 - y2, x2, 16 - y1],
        "west": [z1, 16 - y2, z2, 16 - y1],
        "east": [16 - z2, 16 - y2, 16 - z1, 16 - y1],
    }[face]


def _match_when(when: dict, props: dict) -> bool:
    if "OR" in when:
        return any(_match_when(w, props) for w in when["OR"])
    if "AND" in when:
        return all(_match_when(w, props) for w in when["AND"])
    for k, v in when.items():
        allowed = str(v).lower().split("|")
        if props.get(k, "") not in allowed:
            return False
    return True


def _variant_choices(bs: dict, props: dict) -> list[list[tuple[dict, float]]] | None:
    """For a blockstate JSON: list of 'part choice lists'. Variants -> one part with weighted
    choices; multipart -> one entry per matching part (first weighted choice)."""
    if "variants" in bs:
        best = None
        for key, val in bs["variants"].items():
            if key in ("", "normal"):
                cond = {}
            else:
                cond = dict(kv.split("=", 1) for kv in key.split(",") if "=" in kv)
            if all(props.get(k) == v for k, v in cond.items()):
                best = val
                break
        if best is None:
            return None
        opts = best if isinstance(best, list) else [best]
        return [[(o, float(o.get("weight", 1))) for o in opts]]
    if "multipart" in bs:
        parts = []
        for part in bs["multipart"]:
            when = part.get("when")
            if when is None or _match_when(when, props):
                ap = part["apply"]
                opts = ap if isinstance(ap, list) else [ap]
                parts.append([(opts[0], 1.0)])
        return parts
    return None


def _tint_kind(builder: _Builder, name: str) -> int:
    if name in GRASS_TINTED:
        return 1
    if name in FOLIAGE_TINTED:
        return 2
    if name in WATER_TINTED:
        return 3
    if name in FIXED_TINTS:
        return builder.fixed_tint(FIXED_TINTS[name])
    return 0


def compile_palette(palette: list[str], registry, assets: AssetStore, extra=None) -> Tables:
    """Compile every state of a scene palette. ``extra(builder)`` may append more (display entities)
    and returns their element arrays (stored in ``Tables.ents``)."""
    from . import special

    b = _Builder(assets)
    n = len(palette)
    st_var_start = np.zeros(n, np.int32)
    st_var_count = np.zeros(n, np.int32)
    st_flags = np.zeros(n, np.int32)
    st_emit = np.zeros(n, np.uint8)
    st_filter = np.zeros(n, np.uint8)
    st_height = np.ones(n, np.float32)
    for sid, state in enumerate(palette):
        name, props, _ = parse_state(state)
        st_var_start[sid] = len(b.var_elem_start)
        info = registry.info(name) if name in registry else None
        if info is not None:
            st_emit[sid] = info.light if name != "light" else int(props.get("level", "15"))
            st_filter[sid] = min(15, info.filter_light)
        if name in INVISIBLE:
            st_flags[sid] = F_INVISIBLE
            continue
        tint = _tint_kind(b, name)
        if name in ("water", "lava"):
            level = int(props.get("level", "0"))
            h = 8.0 / 9.0 if level == 0 else max(0.1, (8 - min(level, 7)) / 9.0)
            st_height[sid] = h
            tex = "block/water_still" if name == "water" else "block/lava_still"
            el = {"from": [0, 0, 0], "to": [16, 16 * h, 16],
                  "faces": {f: {"texture": "#t", "tintindex": 0 if name == "water" else None} for f in FACES}}
            for f in FACES:
                if name != "water":
                    el["faces"][f].pop("tintindex")
            b.add_variant([([el], {"t": tex}, 0, 0, True)], 1.0, tint, liquid=True)
            st_var_count[sid] = 1
            st_flags[sid] = F_LIQUID | (F_WATER if name == "water" else F_LAVA)
            continue
        bs = assets.blockstate(name)
        choices = _variant_choices(bs, props) if bs is not None else None
        parts_models: list[list[tuple[dict, float]]] = choices or []
        added = 0
        if parts_models and len(parts_models) == 1 and len(parts_models[0]) > 1:
            # weighted random variants
            opts = parts_models[0]
            total = sum(w for _, w in opts)
            acc = 0.0
            for opt, w in opts:
                elements, textures = b.resolve_model(opt["model"])
                acc += w / total
                b.add_variant([(elements, textures, float(opt.get("x", 0)), float(opt.get("y", 0)),
                                bool(opt.get("uvlock", False)))], acc, tint)
                added += 1
        elif parts_models:
            parts = []
            for choice in parts_models:
                opt = choice[0][0]
                elements, textures = b.resolve_model(opt["model"])
                parts.append((elements, textures, float(opt.get("x", 0)), float(opt.get("y", 0)),
                              bool(opt.get("uvlock", False))))
            if any(p[0] for p in parts):
                b.add_variant(parts, 1.0, tint)
                added = 1
        if added and b.var_elem_count[-1] == 0:
            b.var_elem_start.pop()
            b.var_elem_count.pop()
            b.var_weight.pop()
            added -= 1
        if added == 0:
            proxy = special.proxy(name, props)
            if proxy is not None:
                elements, textures, yrot = proxy
                b.add_variant([(elements, textures, 0.0, yrot, False)], 1.0, tint)
                added = 1
            else:
                st_flags[sid] |= F_INVISIBLE
                if bs is None:
                    b.warnings.append(f"no model for {name}")
        st_var_count[sid] = added
        if added and registry is not None and name in registry and registry.is_full_cube(state):
            # opaque full cube: some element is the whole cube with 6 opaque faces (overlays like
            # the grass side don't matter)
            s0, c0 = b.var_elem_start[-1], b.var_elem_count[-1]

            def solid_elem(e):
                return (np.allclose(b.el_from[e], 0) and np.allclose(b.el_to[e], 1)
                        and all(f >= 0 and b.tex_modes[b.fc_tex[f]] == T_OPAQUE for f in b.el_face[e]))

            full = any(np.allclose(b.el_from[e], 0) and np.allclose(b.el_to[e], 1) for e in range(s0, s0 + c0))
            if any(solid_elem(e) for e in range(s0, s0 + c0)) and not name.endswith("_leaves"):
                st_flags[sid] |= F_OCC
            elif full and not name.endswith("_leaves"):
                st_flags[sid] |= F_SELF_CULL

    ents = extra(b) if extra is not None else {}
    tex_w = np.array([t.shape[1] for t in b.textures], np.int32)
    tex_h = np.array([t.shape[0] for t in b.textures], np.int32)
    sizes = tex_w.astype(np.int64) * tex_h * 4
    tex_off = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int64)
    tex_data = np.concatenate([t.reshape(-1) for t in b.textures]).astype(np.uint8)
    fixed = np.array(b.fixed_tints if b.fixed_tints else [(1.0, 1.0, 1.0)], np.float32)

    def arr(lst, dtype, shape):
        return np.array(lst, dtype=dtype).reshape(shape) if lst else np.zeros(shape, dtype)

    return Tables(
        st_var_start=st_var_start, st_var_count=st_var_count, st_flags=st_flags, st_emit=st_emit,
        st_filter=st_filter, st_height=st_height,
        var_elem_start=arr(b.var_elem_start, np.int32, (-1,) if b.var_elem_start else (0,)),
        var_elem_count=arr(b.var_elem_count, np.int32, (-1,) if b.var_elem_count else (0,)),
        var_weight=arr(b.var_weight, np.float32, (-1,) if b.var_weight else (0,)),
        el_A=arr(b.el_A, np.float64, (-1, 3, 3) if b.el_A else (0, 3, 3)),
        el_b=arr(b.el_b, np.float64, (-1, 3) if b.el_b else (0, 3)),
        el_from=arr(b.el_from, np.float64, (-1, 3) if b.el_from else (0, 3)),
        el_to=arr(b.el_to, np.float64, (-1, 3) if b.el_to else (0, 3)),
        el_face=arr(b.el_face, np.int32, (-1, 6) if b.el_face else (0, 6)),
        el_flags=arr(b.el_flags, np.int32, (-1,) if b.el_flags else (0,)),
        fc_tex=arr(b.fc_tex, np.int32, (-1,) if b.fc_tex else (0,)),
        fc_uv=arr(b.fc_uv, np.float64, (-1, 4) if b.fc_uv else (0, 4)),
        fc_rot=arr(b.fc_rot, np.int32, (-1,) if b.fc_rot else (0,)),
        fc_tint=arr(b.fc_tint, np.int32, (-1,) if b.fc_tint else (0,)),
        fc_cull=arr(b.fc_cull, np.int32, (-1,) if b.fc_cull else (0,)),
        tex_off=tex_off, tex_w=tex_w, tex_h=tex_h, tex_mode=np.array(b.tex_modes, np.int32), tex_data=tex_data,
        fixed_tints=fixed, ents=ents, warnings=b.warnings,
    )
