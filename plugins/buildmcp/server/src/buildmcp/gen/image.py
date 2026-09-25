"""Images into blocks: pixel art walls/floors (logos, banners, maps) and terrain from heightmaps."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..geo.mask import Mask
from ..paint.colors import image_to_blocks

RIGHT_OF_VIEWER = {"south": (1, 0), "north": (-1, 0), "east": (0, -1), "west": (0, 1)}


def _load(path_or_img, width: int | None, height: int | None) -> Image.Image:
    img = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(Path(path_or_img))
    img = img.convert("RGBA")
    if width or height:
        w, h = img.size
        if width and not height:
            height = max(1, round(h * width / w))
        if height and not width:
            width = max(1, round(w * height / h))
        img = img.resize((int(width), int(height)), Image.LANCZOS)
    return img


def pixel_art(scene, image, at, *, width: int | None = None, height: int | None = None, facing: str = "south",
              flat: bool = False, blocks: str = "concrete+wool+terracotta", dither: bool = False,
              alpha_threshold: int = 128) -> Mask:
    """Place an image as blocks.

    at: bottom-left corner as seen by the viewer (for a wall) or the north-west corner (flat).
    facing: side the wall picture is viewed from. flat=True lays it on the ground (north up).
    blocks: color sets joined with '+': concrete, wool, terracotta, glazed, stone, wood, natural, all.
    """
    img = _load(image, width, height)
    arr = np.asarray(img)
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    names = image_to_blocks(rgb, scene.version, blocks, dither=dither)
    h, w = names.shape
    x0, y0, z0 = (int(v) for v in at)
    rx, rz = RIGHT_OF_VIEWER[facing]
    pts = []
    for r in range(h):
        for c in range(w):
            if alpha[r, c] < alpha_threshold:
                continue
            if flat:
                p = (x0 + c, y0, z0 + r)
            else:
                p = (x0 + rx * c, y0 + (h - 1 - r), z0 + rz * c)
            scene.set(*p, names[r, c])
            pts.append(p)
    return Mask.from_points(pts) if pts else Mask.empty()


def heightmap(scene, image, at, *, width: int | None = None, max_height: int = 32, theme=None,
              invert: bool = False) -> "object":
    """Terrain from a grayscale heightmap image (white = high). ``at`` = north-west corner at base height."""
    from .terrain import Terrain, _columns_to_mask, paint_terrain, _theme

    img = _load(image, width, None).convert("L")
    a = np.asarray(img, dtype=float) / 255.0
    if invert:
        a = 1 - a
    x0, y0, z0 = (int(v) for v in at)
    top = (y0 + np.round(a.T * max_height)).astype(int)  # (x, z)
    bottom = np.full_like(top, y0 - 3)
    body = _columns_to_mask(top, bottom, x0, z0)
    ter = Terrain(body=body, surface=body.top(), heights=top, bottoms=bottom, x0=x0, z0=z0,
                  center=(x0 + top.shape[0] / 2, y0, z0 + top.shape[1] / 2), radius=(top.shape[0] / 2, top.shape[1] / 2))
    paint_terrain(scene, ter, _theme(theme))
    return ter
