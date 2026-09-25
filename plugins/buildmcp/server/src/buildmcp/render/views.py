"""High-level rendering: cameras, lighting presets, overlays (grid, markers, legend), sheets.

Every view returns a PIL image. Coordinates are world coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..geo.box import Box
from .assets import AssetStore
from .biomes import biome_colors
from .light import compute_light
from .models import F_INVISIBLE, compile_palette
from .tracer import render_kernel

PAD = 2
TIMES = ("day", "sunset", "night")

LIGHTING = {
    # ambient, sun, sun rgb, block, ambient rgb, shadows, ao ; sky mode ; sun direction
    "day": ((0.92, 0.34, 1.0, 0.95, 0.85, 0.25, 0.86, 0.91, 1.0, 1, 1), 0, (0.36, 0.8, 0.48)),
    "sunset": ((0.62, 0.55, 1.0, 0.64, 0.4, 0.55, 0.8, 0.72, 0.9, 1, 1), 2, (-0.93, 0.26, 0.25)),
    "night": ((0.26, 0.0, 0.0, 0.0, 0.0, 1.25, 0.5, 0.62, 1.0, 0, 1), 3, (0.2, 0.9, 0.3)),
}


@dataclass
class Camera:
    mode: int  # 0 perspective, 1 orthographic
    eye: np.ndarray
    forward: np.ndarray
    right: np.ndarray
    up: np.ndarray
    fov: float = math.radians(70)
    half_w: float = 10.0
    half_h: float = 10.0

    def project(self, p, width: int, height: int) -> tuple[float, float, float] | None:
        """World point -> (px, py, depth) in image pixels, or None if behind the camera."""
        d = np.asarray(p, float) - self.eye
        z = float(d @ self.forward)
        x = float(d @ self.right)
        y = float(d @ self.up)
        if self.mode == 0:
            if z <= 0.05:
                return None
            th = math.tan(self.fov / 2)
            u = x / (z * th * (width / height))
            v = y / (z * th)
        else:
            u = x / self.half_w
            v = y / self.half_h
        return ((u + 1) / 2 * width, (1 - v) / 2 * height, z)


def _norm(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _basis(forward, world_up=(0, 1, 0)):
    f = _norm(forward)
    r = np.cross(f, world_up)
    if np.linalg.norm(r) < 1e-6:
        r = np.array([1.0, 0.0, 0.0])
    r = _norm(r)
    u = np.cross(r, f)
    return f, r, _norm(u)


def perspective(eye, target, fov_deg: float = 70.0) -> Camera:
    f, r, u = _basis(np.asarray(target, float) - np.asarray(eye, float))
    return Camera(0, np.asarray(eye, float), f, r, u, fov=math.radians(fov_deg))


def player_camera(pos, yaw: float, pitch: float = 0.0, fov_deg: float = 70.0, eye_height: float = 1.62) -> Camera:
    """Minecraft yaw/pitch: yaw 0 = south (+z), 90 = west, 180 = north, 270 = east; pitch > 0 looks down."""
    ya = math.radians(yaw)
    pa = math.radians(pitch)
    fwd = np.array([-math.sin(ya) * math.cos(pa), -math.sin(pa), math.cos(ya) * math.cos(pa)])
    eye = np.asarray(pos, float) + np.array([0, eye_height, 0])
    f, r, u = _basis(fwd)
    return Camera(0, eye, f, r, u, fov=math.radians(fov_deg))


def ortho_fit(box: Box, forward, width: int, height: int, up_hint=(0, 1, 0), margin: float = 0.05,
              right=None, up=None) -> Camera:
    if right is None or up is None:
        f, r, u = _basis(forward, up_hint)
    else:
        f, r, u = _norm(forward), _norm(right), _norm(up)
    corners = np.array([[x, y, z] for x in (box.x1, box.x2 + 1) for y in (box.y1, box.y2 + 1)
                        for z in (box.z1, box.z2 + 1)], float)
    c = corners.mean(axis=0)
    xs = (corners - c) @ r
    ys = (corners - c) @ u
    hw = max(abs(xs.min()), abs(xs.max())) * (1 + margin)
    hh = max(abs(ys.min()), abs(ys.max())) * (1 + margin)
    aspect = width / height
    if hw / hh > aspect:
        hh = hw / aspect
    else:
        hw = hh * aspect
    diag = float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0)))
    eye = c - f * (diag + 10)
    return Camera(1, eye, f, r, u, half_w=hw, half_h=hh)


ISO_DIRS = {"se": (1, 1), "sw": (-1, 1), "ne": (1, -1), "nw": (-1, -1)}


def iso_camera(box: Box, direction: str = "se", elevation: float = 32.0, width: int = 1280, height: int = 800) -> Camera:
    sx, sz = ISO_DIRS[direction]
    el = math.radians(elevation)
    to_cam = np.array([sx * math.cos(el) / math.sqrt(2), math.sin(el), sz * math.cos(el) / math.sqrt(2)])
    return ortho_fit(box, -to_cam, width, height)


def top_camera(box: Box, width: int, height: int) -> Camera:
    return ortho_fit(box, (0, -1, 0), width, height, right=(1, 0, 0), up=(0, 0, -1), margin=0.02)


def elevation_camera(box: Box, side: str, width: int, height: int) -> Camera:
    fwd = {"north": (0, 0, 1), "south": (0, 0, -1), "east": (-1, 0, 0), "west": (1, 0, 0)}[side]
    return ortho_fit(box, fwd, width, height, margin=0.04)


# ------------------------------------------------------------------ renderer
class Renderer:
    """Holds compiled tables for one scene; recompiles when the palette or blocks change."""

    def __init__(self, scene):
        self.scene = scene
        self.assets = AssetStore.get(scene.version)
        self._tables = None
        self._tables_key = None
        self._grid_key = None
        self._grid = None

    def tables(self, cam: "Camera | None" = None):
        ents = [e for e in self.scene.entities if e.id.endswith("_display")]
        cam_key = None
        if ents and cam is not None:
            cam_key = (tuple(np.round(cam.forward, 5)), tuple(np.round(cam.up, 5)))
        key = (len(self.scene.palette), tuple(self.scene.palette[-3:]), len(ents),
               hash(tuple((e.id, e.pos, str(e.nbt)) for e in ents)) if ents else 0, cam_key)
        if self._tables is None or self._tables_key != key:
            extra = None
            if ents:
                from . import entities as ent_mod

                fwd = cam.forward if cam is not None else np.array([0, 0, -1.0])
                rgt = cam.right if cam is not None else np.array([1.0, 0, 0])
                up = cam.up if cam is not None else np.array([0, 1.0, 0])
                extra = lambda b: ent_mod.build(b, self.scene.reg, ents, fwd, rgt, up)  # noqa: E731
            self._tables = compile_palette(self.scene.palette, self.scene.reg, self.assets, extra)
            self._tables_key = key
        return self._tables

    def grid(self, region: Box | None):
        scene = self.scene
        b = region if region is not None else scene.bbox()
        if b is None:
            b = Box(0, 0, 0, 0, 0, 0)
        key = (scene.dirty_version, b.as_tuple(), len(scene.palette))
        if self._grid is not None and self._grid_key == key:
            return self._grid
        gb = Box(b.x1 - PAD, b.y1 - PAD, b.z1 - PAD, b.x2 + PAD, b.y2 + PAD + 1, b.z2 + PAD)
        vox = scene.ids(gb)
        if region is not None:
            # everything outside the region is empty (so a sub-region renders alone)
            inner = np.zeros(vox.shape, bool)
            inner[PAD:-PAD - 1 or None, PAD:-PAD - 1 or None, PAD:-PAD or None] = True
            vox = np.where(inner, vox, 0).astype(np.uint16)
        t = self._tables if self._tables is not None else self.tables()
        bl, sl = compute_light(vox, t.st_flags, t.st_emit, t.st_filter)
        # biomes per column
        bio_names = scene.biome_palette
        gmap = self.assets.colormap("grass")
        fmap = self.assets.colormap("foliage")
        tint_table = np.stack([biome_colors(n, gmap, fmap) for n in bio_names]).astype(np.float32)
        bio = np.zeros((vox.shape[0], vox.shape[2]), np.int32)
        if scene.biomes.size:
            x0 = gb.x1 - int(scene.origin[0])
            z0 = gb.z1 - int(scene.origin[2])
            sx, sz = scene.biomes.shape
            for i in range(vox.shape[0]):
                xi = x0 + i
                if 0 <= xi < sx:
                    zlo = max(0, z0)
                    zhi = min(sz, z0 + vox.shape[2])
                    if zhi > zlo:
                        bio[i, zlo - z0:zhi - z0] = scene.biomes[xi, zlo:zhi]
        self._grid = (gb, np.ascontiguousarray(vox), bl, sl, bio, tint_table)
        self._grid_key = key
        return self._grid

    def render(self, cam: Camera, width: int = 1280, height: int = 800, time: str = "day", ss: int = 1,
               region: Box | None = None, y_cut: int | None = None, highlight=None, background=None,
               fog: float | None = None) -> tuple[Image.Image, np.ndarray]:
        t = self.tables(cam)
        gb, vox, bl, sl, bio, tint_table = self.grid(region)
        g0 = np.array(gb.min, float)
        lp, sky_mode, sun = LIGHTING[time]
        sun = _norm(sun)
        eye = cam.eye - g0
        max_t = 1e5
        cam_arr = np.array([cam.mode, *eye, *cam.forward, *cam.right, *cam.up,
                            cam.fov if cam.mode == 0 else cam.half_w, cam.half_h, max_t], dtype=np.float64)
        if fog is None:
            size = max(gb.size)
            fog = size * 2.2 if cam.mode == 0 else 0.0
        env = np.zeros(11, np.float64)
        env[8:11] = g0
        env[0] = sky_mode
        env[1:4] = sun
        if background is not None:
            env[0] = 1
            env[4:7] = background
        env[7] = fog
        ycut = 10**9 if y_cut is None else int(y_cut - gb.y1)
        hl = np.zeros((1, 1, 1), np.uint8)
        if highlight is not None:
            hl = highlight.to_box(gb).astype(np.uint8) if hasattr(highlight, "to_box") else highlight
        img, depth = render_kernel(
            int(width), int(height), int(ss), cam_arr, env, np.array(lp, np.float64), vox, ycut, hl,
            t.st_var_start, t.st_var_count, t.st_flags, t.st_height, t.st_emit, t.var_elem_start,
            t.var_elem_count, t.var_weight, t.el_A, t.el_b, t.el_from, t.el_to, t.el_face, t.el_flags,
            t.fc_tex, t.fc_uv, t.fc_rot, t.fc_tint, t.fc_cull, t.tex_off, t.tex_w, t.tex_h, t.tex_mode,
            t.tex_data, bio, tint_table, t.fixed_tints, bl, sl, *self._ent_arrays(t))
        return to_image(img), depth

    @staticmethod
    def _ent_arrays(t):
        e = t.ents
        if not e or e["A"].shape[0] == 0:
            return (np.zeros((0, 3, 3)), np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3)),
                    np.zeros((0, 6), np.int32), np.zeros(0, np.int32), np.zeros((0, 6)))
        return (e["A"], e["b"], e["from"], e["to"], e["face"], e["flags"], e["aabb"])


def to_image(img: np.ndarray) -> Image.Image:
    x = img.astype(np.float32)
    # soft shoulder above 0.8
    over = x > 0.8
    x[over] = 0.8 + 0.2 * (1 - np.exp(-(x[over] - 0.8) / 0.2))
    x = np.clip(x, 0, 1)
    return Image.fromarray((x * 255 + 0.5).astype(np.uint8), "RGB")


# ------------------------------------------------------------------ overlays
def _font(size: int):
    for name in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_label(draw: ImageDraw.ImageDraw, xy, text: str, size: int = 14, fill=(255, 255, 255), bg=(0, 0, 0, 170)):
    f = _font(size)
    x, y = xy
    bbox = draw.textbbox((x, y), text, font=f)
    pad = 3
    draw.rectangle((bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad), fill=bg)
    draw.text((x, y), text, font=f, fill=fill)


def overlay_grid_top(img: Image.Image, cam: Camera, box: Box, step: int | None = None) -> Image.Image:
    """Grid lines every ``step`` blocks with world coordinate labels (for top-down maps)."""
    w, h = img.size
    ext = max(box.size[0], box.size[2])
    if step is None:
        step = 4 if ext <= 48 else 8 if ext <= 110 else 16 if ext <= 260 else 32
    im = img.convert("RGBA")
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = box.y2 + 1
    x0 = (box.x1 // step) * step
    for x in range(x0, box.x2 + 2, step):
        p = cam.project((x, y, box.z1), w, h)
        if p is None:
            continue
        major = x % (step * 4) == 0
        d.line([(p[0], 0), (p[0], h)], fill=(255, 255, 255, 110 if major else 55), width=1)
        draw_label(d, (p[0] + 2, 2), str(x), size=11, bg=(0, 0, 0, 120))
    z0 = (box.z1 // step) * step
    for z in range(z0, box.z2 + 2, step):
        p = cam.project((box.x1, y, z), w, h)
        if p is None:
            continue
        major = z % (step * 4) == 0
        d.line([(0, p[1]), (w, p[1])], fill=(255, 255, 255, 110 if major else 55), width=1)
        draw_label(d, (2, p[1] + 2), str(z), size=11, bg=(0, 0, 0, 120))
    draw_label(d, (w - 150, h - 22), f"N up | grid {step}", size=12)
    return Image.alpha_composite(im, layer).convert("RGB")


MARKER_COLORS = {
    "spawn": (255, 215, 0), "npc": (80, 200, 255), "portal": (190, 90, 255), "hologram": (120, 255, 160),
    "viewpoint": (255, 120, 80), "warp": (255, 255, 255), "point": (230, 230, 230), "region": (255, 80, 80),
}


def overlay_markers(img: Image.Image, cam: Camera, markers, depth: np.ndarray | None = None) -> Image.Image:
    w, h = img.size
    im = img.convert("RGBA")
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for m in markers:
        p = cam.project((m.pos[0] + 0.5, m.pos[1] + 0.5, m.pos[2] + 0.5), w, h)
        if p is None or not (0 <= p[0] < w and 0 <= p[1] < h):
            continue
        col = MARKER_COLORS.get(m.kind, (230, 230, 230))
        r = 6
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=col + (230,), outline=(0, 0, 0, 255), width=2)
        if m.kind in ("spawn", "viewpoint", "npc"):
            ya = math.radians(m.yaw)
            tip = cam.project((m.pos[0] + 0.5 - math.sin(ya) * 3, m.pos[1] + 0.5, m.pos[2] + 0.5 + math.cos(ya) * 3), w, h)
            if tip is not None:
                d.line([(p[0], p[1]), (tip[0], tip[1])], fill=col + (255,), width=3)
        draw_label(d, (p[0] + 9, p[1] - 8), f"{m.name}", size=12)
    return Image.alpha_composite(im, layer).convert("RGB")


def legend(img: Image.Image, items: list[tuple[str, tuple[int, int, int], int]], title: str = "") -> Image.Image:
    """Add a side legend: [(label, rgb, count)]."""
    f = _font(13)
    row = 18
    wl = 260
    h = max(img.size[1], 30 + row * len(items))
    out = Image.new("RGB", (img.size[0] + wl, h), (24, 24, 28))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    x = img.size[0] + 10
    d.text((x, 8), title, font=_font(14), fill=(255, 255, 255))
    for i, (label, rgb, cnt) in enumerate(items):
        y = 30 + i * row
        d.rectangle((x, y, x + 14, y + 14), fill=rgb, outline=(0, 0, 0))
        d.text((x + 20, y), f"{label} ({cnt})", font=f, fill=(230, 230, 230))
    return out


def sheet(images: list[tuple[str, Image.Image]], cols: int = 2, pad: int = 6, bg=(20, 20, 24)) -> Image.Image:
    """Contact sheet with captions."""
    if not images:
        return Image.new("RGB", (10, 10), bg)
    w = max(im.size[0] for _, im in images)
    h = max(im.size[1] for _, im in images)
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * w + (cols + 1) * pad, rows * h + (rows + 1) * pad), bg)
    d = ImageDraw.Draw(out)
    for i, (cap, im) in enumerate(images):
        r, c = divmod(i, cols)
        x = pad + c * (w + pad)
        y = pad + r * (h + pad)
        out.paste(im, (x, y))
        if cap:
            draw_label(d, (x + 8, y + 8), cap, size=15)
    return out


def average_colors(renderer: Renderer) -> dict[int, tuple[int, int, int]]:
    """Mean top-face color per palette entry (for legends)."""
    t = renderer.tables()
    out = {}
    for sid in range(len(renderer.scene.palette)):
        if t.st_var_count[sid] == 0 or (t.st_flags[sid] & F_INVISIBLE):
            continue
        e = t.var_elem_start[t.st_var_start[sid]]
        f = t.el_face[e, 1] if t.el_face[e, 1] >= 0 else max(t.el_face[e])
        if f < 0:
            continue
        tid = t.fc_tex[f]
        off, w, h = t.tex_off[tid], t.tex_w[tid], t.tex_h[tid]
        px = t.tex_data[off:off + w * h * 4].reshape(h, w, 4)
        a = px[..., 3] > 0
        rgb = px[..., :3][a].mean(axis=0) if a.any() else np.array([128, 128, 128])
        out[sid] = tuple(int(v) for v in rgb)
    return out
