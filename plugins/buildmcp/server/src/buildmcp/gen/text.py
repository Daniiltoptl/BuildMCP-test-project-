"""3D block text for logos and signs (built-in 5x7 pixel font with Latin, digits and Cyrillic,
or any TrueType font).

    text.text3d(S, "FUNWORLD", at=(0, 95, -30), facing="south", scale=2, depth=3,
                face=P.gradient(["yellow_concrete", "orange_concrete"], axis="y", start=110, end=95),
                outline="black_concrete")
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..geo.mask import Mask

_G = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#",
    "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.",
    "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####",
    "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####",
    "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": ".###.|..#..|..#..|..#..|..#..|..#..|.###.",
    "J": "..###|...#.|...#.|...#.|#..#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#",
    "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
    "N": "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
    "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#",
    "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.",
    "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.",
    "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
    "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.",
    "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####",
    "3": "####.|....#|....#|.###.|....#|....#|####.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.",
    "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": ".###.|#....|#....|####.|#...#|#...#|.###.",
    "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.",
    "9": ".###.|#...#|#...#|.####|....#|....#|.###.",
    "!": "#|#|#|#|#|.|#",
    ".": ".|.|.|.|.|.|#",
    ",": "..|..|..|..|..|.#|#.",
    ":": ".|#|.|.|.|#|.",
    "-": "....|....|....|####|....|....|....",
    "+": ".....|..#..|..#..|#####|..#..|..#..|.....",
    "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
    "'": "#|#|.|.|.|.|.",
    "/": "....#|...#.|...#.|..#..|.#...|.#...|#....",
    "&": ".##..|#..#.|#.#..|.#...|#.#.#|#..#.|.##.#",
    "|": "#|#|#|#|#|#|#",
    "*": ".....|#.#.#|.###.|#####|.###.|#.#.#|.....",
    "Б": "#####|#....|#....|####.|#...#|#...#|####.",
    "Г": "#####|#....|#....|#....|#....|#....|#....",
    "Д": "..##.|.#.#.|.#.#.|.#.#.|.#.#.|#####|#...#",
    "Ё": ".#.#.|#####|#....|####.|#....|#....|#####",
    "Ж": "#.#.#|#.#.#|.###.|..#..|.###.|#.#.#|#.#.#",
    "З": ".###.|#...#|....#|..##.|....#|#...#|.###.",
    "И": "#...#|#...#|#..##|#.#.#|##..#|#...#|#...#",
    "Й": ".#.#.|#...#|#..##|#.#.#|##..#|#...#|#...#",
    "Л": "..###|.#..#|.#..#|.#..#|.#..#|.#..#|#...#",
    "П": "#####|#...#|#...#|#...#|#...#|#...#|#...#",
    "У": "#...#|#...#|#...#|.####|....#|....#|.###.",
    "Ф": "..#..|.###.|#.#.#|#.#.#|#.#.#|.###.|..#..",
    "Ц": "#..#.|#..#.|#..#.|#..#.|#..#.|#####|....#",
    "Ч": "#...#|#...#|#...#|.####|....#|....#|....#",
    "Ш": "#...#|#...#|#.#.#|#.#.#|#.#.#|#.#.#|#####",
    "Щ": "#.#.#|#.#.#|#.#.#|#.#.#|#.#.#|#####|....#",
    "Ъ": "##...|.#...|.#...|.###.|.#..#|.#..#|.###.",
    "Ы": "#...#|#...#|#...#|###.#|#.#.#|#.#.#|###.#",
    "Ь": "#....|#....|#....|####.|#...#|#...#|####.",
    "Э": ".###.|#...#|....#|.####|....#|#...#|.###.",
    "Ю": "#..#.|#.#.#|#.#.#|###.#|#.#.#|#.#.#|#..#.",
    "Я": ".####|#...#|#...#|.####|..#.#|.#..#|#...#",
}
for _lat, _cyr in zip("AVEKMHOPCTX", "АВЕКМНОРСТХ"):
    _G[_cyr] = _G[_lat]
_SPACE = 3


def _glyph(ch: str) -> np.ndarray:
    g = _G.get(ch.upper())
    if g is None:
        g = _G["?"]
    rows = g.split("|")
    return np.array([[c == "#" for c in r] for r in rows], dtype=bool)


def pixel_text(text: str, spacing: int = 1, line_spacing: int = 2) -> np.ndarray:
    """2D boolean image (rows top->bottom) of text in the built-in 5x7 font; '\\n' for new lines."""
    lines = text.split("\n")
    rendered = []
    for ln in lines:
        cols = []
        for i, ch in enumerate(ln):
            if ch == " ":
                cols.append(np.zeros((7, _SPACE), bool))
            else:
                cols.append(_glyph(ch))
            if i < len(ln) - 1:
                cols.append(np.zeros((7, spacing), bool))
        rendered.append(np.concatenate(cols, axis=1) if cols else np.zeros((7, 1), bool))
    width = max(r.shape[1] for r in rendered)
    out = []
    for i, r in enumerate(rendered):
        pad = width - r.shape[1]
        out.append(np.pad(r, ((0, 0), (pad // 2, pad - pad // 2))))
        if i < len(rendered) - 1:
            out.append(np.zeros((line_spacing, width), bool))
    return np.concatenate(out, axis=0)


def ttf_text(text: str, height: int, font: str) -> np.ndarray:
    """2D boolean image of text rendered with a TrueType font at ``height`` pixels (letter height)."""
    f = ImageFont.truetype(font, int(height * 1.3))
    lines = text.split("\n")
    widths = [int(f.getlength(ln)) for ln in lines]
    W = max(widths) + 4
    H = int(height * 1.6) * len(lines) + 4
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text(((W - widths[i]) // 2, 2 + i * int(height * 1.6)), ln, font=f, fill=255)
    a = np.asarray(img) > 110
    ys, xs = np.nonzero(a)
    if len(ys) == 0:
        return np.zeros((1, 1), bool)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


RIGHT_OF_VIEWER = {"south": (1, 0), "north": (-1, 0), "east": (0, -1), "west": (0, 1)}  # facing -> (dx, dz)
BACK = {"south": (0, -1), "north": (0, 1), "east": (-1, 0), "west": (1, 0)}


def text3d(scene, text: str, at, *, facing: str = "south", scale: int = 1, depth: int = 2, face="gold_block",
           side=None, outline=None, outline_width: int = 1, outline_depth: int | None = None, shadow=None,
           font: str | None = None, font_height: int = 12, spacing: int = 1, horizontal: bool = False) -> dict:
    """Extruded block text.

    at: bottom-center of the text's front face. facing: side the text is read from.
    scale: blocks per font pixel. depth: extrusion (blocks, going away from the reader).
    face/side/outline/shadow: blocks or palettes (e.g. a vertical gradient for the face).
    font: None = built-in pixel font (5x7, supports Cyrillic); or a .ttf path/name with ``font_height``.
    horizontal: lay the text flat on the ground (readable from above, top of letters towards -facing).
    Returns masks: {"face", "outline", "all"}.
    """
    img = pixel_text(text, spacing) if font is None else ttf_text(text, font_height, font)
    if scale > 1:
        img = np.kron(img, np.ones((scale, scale), bool))
    h, w = img.shape
    x0, y0, z0 = (int(v) for v in at)
    rx, rz = RIGHT_OF_VIEWER[facing]
    bx, bz = BACK[facing]
    outline_img = None
    if outline is not None:
        from scipy import ndimage

        pad = outline_width
        big = np.pad(img, pad)
        dil = ndimage.binary_dilation(big, structure=np.ones((3, 3), bool), iterations=outline_width)
        outline_img = dil & ~big
        img_p = big
    else:
        img_p = img
        pad = 0
    H, W = img_p.shape

    def cells(mask2d, d0, d1):
        pts = []
        rows, cols = np.nonzero(mask2d)
        for r, c in zip(rows.tolist(), cols.tolist()):
            u = c - W // 2
            v = (H - 1 - r) - pad
            for d in range(d0, d1):
                if horizontal:
                    px = x0 + rx * u + bx * (H - 1 - r - pad)
                    pz = z0 + rz * u + bz * (H - 1 - r - pad)
                    pts.append((px, y0 + d, pz))
                else:
                    pts.append((x0 + rx * u + bx * d, y0 + v, z0 + rz * u + bz * d))
        return Mask.from_points(pts) if pts else Mask.empty()

    face_m = cells(img_p, 0, 1)
    body_m = cells(img_p, 1, depth) if depth > 1 else Mask.empty()
    scene.put(face_m, face)
    if body_m:
        scene.put(body_m, side if side is not None else face)
    out_m = Mask.empty()
    if outline_img is not None:
        od = depth if outline_depth is None else outline_depth
        out_m = cells(outline_img, 0 if od == depth else depth - od, depth)
        scene.put(out_m, outline)
    if shadow is not None:
        sh = np.zeros_like(img_p)
        sh[1:, 1:] = img_p[:-1, :-1]
        sh &= ~img_p
        if outline_img is not None:
            sh &= ~outline_img
        scene.put(cells(sh, depth - 1, depth), shadow)
    return {"face": face_m, "outline": out_m, "all": face_m | body_m | out_m, "size": (W, H)}
