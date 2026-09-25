"""Display entities (block_display, item_display, text_display) as renderable elements.

Each entity becomes elements in *world* space: A, b map world coordinates to element
coordinates, like block elements do for block-local coordinates.
"""

from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..blocks.registry import format_state
from .models import FACES, _variant_choices, element_affine, state_rotation

TEXT_SCALE = 0.025  # blocks per font pixel (vanilla name tags / text displays)
NAMED_COLORS = {
    "black": "#000000", "dark_blue": "#0000AA", "dark_green": "#00AA00", "dark_aqua": "#00AAAA",
    "dark_red": "#AA0000", "dark_purple": "#AA00AA", "gold": "#FFAA00", "gray": "#AAAAAA", "dark_gray": "#555555",
    "blue": "#5555FF", "green": "#55FF55", "aqua": "#55FFFF", "red": "#FF5555", "light_purple": "#FF55FF",
    "yellow": "#FFFF55", "white": "#FFFFFF",
}


def _get(nbt, key, default=None):
    try:
        return nbt[key] if key in nbt else default
    except TypeError:
        return default


def _floats(v, n) -> list[float]:
    try:
        vals = [float(x) for x in v]
    except TypeError:
        return [0.0] * n
    return (vals + [0.0] * n)[:n]


def _quat_to_matrix(q) -> np.ndarray:
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _rotation_from(v) -> np.ndarray:
    if v is None:
        return np.eye(3)
    if hasattr(v, "keys") and "angle" in v:
        ang = float(v["angle"])
        ax = np.array(_floats(v["axis"], 3))
        ax = ax / (np.linalg.norm(ax) or 1.0)
        s = math.sin(ang / 2)
        return _quat_to_matrix((ax[0] * s, ax[1] * s, ax[2] * s, math.cos(ang / 2)))
    q = _floats(v, 4)
    if q == [0.0, 0.0, 0.0, 0.0]:
        return np.eye(3)
    return _quat_to_matrix(q)


def display_transform(nbt) -> tuple[np.ndarray, np.ndarray]:
    """(L 3x3, t 3) from the 'transformation' field (compound or 16-float matrix)."""
    tr = _get(nbt, "transformation")
    if tr is None:
        return np.eye(3), np.zeros(3)
    try:
        if not hasattr(tr, "keys"):
            m = np.array(_floats(tr, 16)).reshape(4, 4)
            return m[:3, :3], m[:3, 3]
    except Exception:  # noqa: BLE001
        return np.eye(3), np.zeros(3)
    t = np.array(_floats(_get(tr, "translation", [0, 0, 0]), 3))
    s = np.array(_floats(_get(tr, "scale", [1, 1, 1]), 3))
    left = _rotation_from(_get(tr, "left_rotation"))
    right = _rotation_from(_get(tr, "right_rotation"))
    return left @ np.diag(s) @ right, t


def entity_rotation(nbt, billboard: str, cam_forward, cam_right, cam_up) -> np.ndarray:
    """Rotation of the display's local frame into the world."""
    if billboard == "center":
        back = -np.asarray(cam_forward, float)
        return np.stack([np.asarray(cam_right, float), np.asarray(cam_up, float), back], axis=1)
    rot = _floats(_get(nbt, "Rotation", [0, 0]), 2)
    yaw, pitch = rot
    if billboard == "vertical":
        f = np.asarray(cam_forward, float)
        yaw = math.degrees(math.atan2(f[0], -f[2]))  # face the camera around Y
    if billboard == "horizontal":
        f = np.asarray(cam_forward, float)
        pitch = -math.degrees(math.asin(max(-1.0, min(1.0, f[1]))))
    ry = np.array([[math.cos(math.radians(-yaw)), 0, math.sin(math.radians(-yaw))], [0, 1, 0],
                   [-math.sin(math.radians(-yaw)), 0, math.cos(math.radians(-yaw))]])
    pa = math.radians(pitch)
    rx = np.array([[1, 0, 0], [0, math.cos(pa), -math.sin(pa)], [0, math.sin(pa), math.cos(pa)]])
    return ry @ rx


# ------------------------------------------------------------------ text
def _component_runs(comp, inherited=None) -> list[tuple[str, str, bool]]:
    """Flatten a text component into (text, color_hex, bold) runs."""
    inherited = inherited or {"color": "#FFFFFF", "bold": False}
    if isinstance(comp, str):
        s = comp.strip()
        if s.startswith(("{", "[", '"')):
            try:
                return _component_runs(json.loads(s), inherited)
            except json.JSONDecodeError:
                pass
        return [(comp, inherited["color"], inherited["bold"])]
    if isinstance(comp, list):
        out = []
        for c in comp:
            out.extend(_component_runs(c, inherited))
        return out
    if hasattr(comp, "keys"):
        color = str(comp.get("color", "")) if "color" in comp else ""
        style = dict(inherited)
        if color:
            style["color"] = NAMED_COLORS.get(color, color if color.startswith("#") else inherited["color"])
        if "bold" in comp:
            style["bold"] = bool(int(comp["bold"])) if not isinstance(comp["bold"], str) else comp["bold"] == "true"
        out = []
        if "text" in comp:
            out.append((str(comp["text"]), style["color"], style["bold"]))
        for c in comp.get("extra", []) or []:
            out.extend(_component_runs(c, style))
        return out
    return [(str(comp), inherited["color"], inherited["bold"])]


def _font(size: int, bold: bool):
    names = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf")
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_texture(nbt) -> np.ndarray:
    """RGBA image (1 texel = 1 font pixel at 4x supersampling -> scaled) for a text display."""
    text = _get(nbt, "text", '""')
    runs = _component_runs(text if isinstance(text, str) else _to_py(text))
    k = 4  # supersample: 4 texels per font pixel
    line_h = 10 * k
    lines: list[list[tuple[str, str, bool]]] = [[]]
    for s, col, bold in runs:
        parts = s.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lines.append([])
            if part:
                lines[-1].append((part, col, bold))
    fonts = {b: _font(8 * k, b) for b in (False, True)}
    widths = []
    for ln in lines:
        w = 0
        for s, _, b in ln:
            w += int(fonts[b].getlength(s))
        widths.append(w)
    width = max(widths + [k]) + 2 * k
    height = line_h * len(lines) + k
    bg = _get(nbt, "background", None)
    if bg is None:
        bg_rgba = (0, 0, 0, 64)
    else:
        v = int(bg) & 0xFFFFFFFF
        bg_rgba = ((v >> 16) & 255, (v >> 8) & 255, v & 255, (v >> 24) & 255)
    img = Image.new("RGBA", (width, height), bg_rgba)
    d = ImageDraw.Draw(img)
    for li, ln in enumerate(lines):
        x = (width - widths[li]) // 2
        y = li * line_h + k
        for s, col, b in ln:
            d.text((x + k // 2, y + k // 2), s, font=fonts[b], fill=(40, 40, 40, 255))  # shadow
            d.text((x, y), s, font=fonts[b], fill=col)
            x += int(fonts[b].getlength(s))
    return np.asarray(img, dtype=np.uint8).copy(), width / k, height / k


def _to_py(tag):
    if hasattr(tag, "keys"):
        return {str(k): _to_py(v) for k, v in tag.items()}
    if isinstance(tag, list):
        return [_to_py(v) for v in tag]
    return tag if isinstance(tag, (int, float)) else str(tag)


# ------------------------------------------------------------------ build
def _block_model_elements(builder, registry, state: str):
    """[(elements, textures, x, y, uvlock)] for a block state (first variant)."""
    from ..blocks.registry import parse_state

    name, props, _ = parse_state(registry.canonical(state))
    bs = builder.assets.blockstate(name)
    if bs is None:
        return []
    choices = _variant_choices(bs, props)
    parts = []
    for choice in choices or []:
        opt = choice[0][0]
        elements, textures = builder.resolve_model(opt["model"])
        parts.append((elements, textures, float(opt.get("x", 0)), float(opt.get("y", 0)), bool(opt.get("uvlock", False))))
    return parts


def build(builder, registry, entities, cam_forward, cam_right, cam_up) -> dict:
    """Append display-entity elements to the builder; returns arrays for the tracer."""
    A, B, FR, TO, FACE, FLAGS, AABB = [], [], [], [], [], [], []

    def add(el_A, el_b, fr, to, faces, flags, world_corners):
        A.append(el_A)
        B.append(el_b)
        FR.append(fr)
        TO.append(to)
        FACE.append(faces)
        FLAGS.append(flags)
        lo = world_corners.min(axis=0)
        hi = world_corners.max(axis=0)
        AABB.append(np.concatenate([lo, hi]))

    for ent in entities:
        eid = ent.id.removeprefix("minecraft:")
        if eid not in ("block_display", "item_display", "text_display"):
            continue
        nbt = ent.nbt
        billboard = str(_get(nbt, "billboard", "fixed"))
        L, t = display_transform(nbt)
        R = entity_rotation(nbt, billboard, cam_forward, cam_right, cam_up)
        pos = np.array(ent.pos, float)
        try:
            Linv = np.linalg.inv(L)
        except np.linalg.LinAlgError:
            continue
        # p_world = pos + R (L p_model + t)  =>  p_model = Linv (R^T (p_world - pos) - t)
        N = Linv @ R.T
        c0 = -Linv @ (R.T @ pos) - Linv @ t

        parts = []
        offset = np.zeros(3)
        if eid == "block_display":
            bs = _get(nbt, "block_state")
            if bs is None:
                continue
            name = str(_get(bs, "Name", "minecraft:air")).removeprefix("minecraft:")
            props = {str(k): str(v) for k, v in (_get(bs, "Properties", {}) or {}).items()}
            try:
                parts = _block_model_elements(builder, registry, format_state(name, props))
            except Exception:  # noqa: BLE001 - unknown block in NBT
                continue
        elif eid == "item_display":
            item = _get(nbt, "item")
            iid = str(_get(item, "id", "minecraft:air")).removeprefix("minecraft:") if item is not None else "air"
            offset = np.array([-0.5, -0.5, -0.5])  # items are centered on the entity
            if iid in registry:
                try:
                    parts = _block_model_elements(builder, registry, iid)
                except Exception:  # noqa: BLE001
                    parts = []
            if not parts:
                tex = f"item/{iid}"
                if builder.assets.texture(tex) is None:
                    tex = f"block/{iid}"
                el = {"from": [0, 0, 7.5], "to": [16, 16, 8.5],
                      "faces": {"north": {"texture": "#t"}, "south": {"texture": "#t"}}}
                parts = [([el], {"t": tex}, 0.0, 0.0, False)]
        else:  # text_display
            arr, w_px, h_px = text_texture(nbt)
            key = f"__text__{id(ent)}_{len(builder.textures)}"
            tid = builder._add_texture(key, arr)
            builder.tex_index[key] = tid
            w = w_px * TEXT_SCALE
            h = h_px * TEXT_SCALE
            face_ids = [-1] * 6
            for fname in ("south", "north"):
                face_ids[FACES.index(fname)] = len(builder.fc_tex)
                builder.fc_tex.append(tid)
                builder.fc_uv.append([0.0, 0.0, 16.0, 16.0] if fname == "south" else [16.0, 0.0, 0.0, 16.0])
                builder.fc_rot.append(0)
                builder.fc_tint.append(0)
                builder.fc_cull.append(-1)
            # quad in model space: x in [-w/2, w/2], y in [0, h], z = 0 (thin)
            fr = np.array([-w / 2, 0.0, -0.001])
            to = np.array([w / 2, h, 0.001])
            corners = np.array([[x, y, z] for x in (fr[0], to[0]) for y in (fr[1], to[1]) for z in (fr[2], to[2])])
            world = (R @ (L @ corners.T + t[:, None])).T + pos
            add(N, c0, fr, to, face_ids, 8, world)  # flag 8: unlit-ish text
            continue

        for elements, textures, x, y, uvlock in parts:
            start = len(builder.el_A)
            builder.add_elements(elements, textures, x, y, uvlock, 0)
            for e in range(start, len(builder.el_A)):
                el_A = builder.el_A[e]
                el_b = builder.el_b[e]
                # element <- model(block-local) <- world: p_model_local = p_model - offset
                A_full = el_A @ N
                b_full = el_A @ (c0 - offset) + el_b
                fr = builder.el_from[e]
                to = builder.el_to[e]
                # world AABB: transform element box corners back to world
                try:
                    Ainv = np.linalg.inv(A_full)
                except np.linalg.LinAlgError:
                    continue
                corners = np.array([[xx, yy, zz] for xx in (fr[0], to[0]) for yy in (fr[1], to[1]) for zz in (fr[2], to[2])])
                world = (Ainv @ (corners - b_full).T).T
                add(A_full, b_full, fr, to, builder.el_face[e], builder.el_flags[e], world)
            # these elements live only in the entity table
            del builder.el_A[start:], builder.el_b[start:], builder.el_from[start:], builder.el_to[start:]
            del builder.el_face[start:], builder.el_flags[start:]

    def arr(lst, shape, dtype):
        return np.array(lst, dtype=dtype).reshape(shape) if lst else np.zeros((0,) + shape[1:], dtype)

    return {
        "A": arr(A, (-1, 3, 3), np.float64), "b": arr(B, (-1, 3), np.float64),
        "from": arr(FR, (-1, 3), np.float64), "to": arr(TO, (-1, 3), np.float64),
        "face": arr(FACE, (-1, 6), np.int32), "flags": arr(FLAGS, (-1,), np.int32),
        "aabb": arr(AABB, (-1, 6), np.float64),
    }
