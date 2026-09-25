"""Block colors (from the real textures) for pixel art, image/model import and palette tools.

Colors are averaged from the block's textures (top and side), compared in CIE LAB.
"""

from __future__ import annotations

import functools

import numpy as np

EXCLUDE_WORDS = (
    "command_block", "structure", "jigsaw", "barrier", "light", "spawner", "infested", "tnt", "sculk_sensor",
    "sculk_shrieker", "test_", "reinforced_deepslate", "budding_amethyst", "_ore", "bedrock", "trial_spawner",
    "vault", "crafter", "dispenser", "dropper", "observer", "piston", "furnace", "smoker", "loom", "barrel",
    "beehive", "bee_nest", "target", "respawn_anchor", "lodestone", "chiseled_bookshelf", "bookshelf",
    "crafting_table", "fletching_table", "smithing_table", "cartography_table", "note_block", "jukebox",
    "redstone_lamp", "sponge", "slime_block", "honey_block", "frosted_ice", "suspicious", "creaking_heart",
)
GRAVITY_WORDS = ("sand", "gravel", "concrete_powder")

SETS = {
    "concrete": lambda n: n.endswith("_concrete"),
    "wool": lambda n: n.endswith("_wool"),
    "terracotta": lambda n: n.endswith("terracotta") and "glazed" not in n,
    "glazed": lambda n: n.endswith("glazed_terracotta"),
    "stone": lambda n: any(w in n for w in ("stone", "andesite", "diorite", "granite", "tuff", "deepslate", "calcite",
                                           "basalt", "blackstone", "bricks", "tiles", "cobble")),
    "wood": lambda n: n.endswith(("_planks", "_log", "_wood")),
    "natural": lambda n: any(w in n for w in ("dirt", "grass", "moss", "mud", "podzol", "clay", "snow", "ice",
                                             "stone", "andesite", "diorite", "granite", "tuff", "deepslate", "calcite")),
}


def _srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, float) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


@functools.lru_cache(maxsize=8)
def block_colors(version: str) -> dict[str, dict]:
    """{block: {"top": (r,g,b), "side": (r,g,b), "opaque": bool}} for full-cube blocks of a version."""
    from ..blocks.registry import get_registry
    from ..render.assets import AssetStore
    from ..render.models import F_OCC, compile_palette

    reg = get_registry(version)
    names = [n for n in reg.names() if reg.is_full_cube(n) and not any(w in n for w in EXCLUDE_WORDS)]
    palette = ["minecraft:air"] + [reg.canonical(n) for n in names]
    t = compile_palette(palette, reg, AssetStore.get(reg.version))
    out: dict[str, dict] = {}
    for sid, name in enumerate(names, start=1):
        if t.st_var_count[sid] == 0:
            continue
        e = t.var_elem_start[t.st_var_start[sid]]
        faces = t.el_face[e]

        def mean(face_idx):
            f = faces[face_idx]
            if f < 0:
                return None
            tid = t.fc_tex[f]
            off, w, h = t.tex_off[tid], t.tex_w[tid], t.tex_h[tid]
            px = t.tex_data[off:off + w * h * 4].reshape(h, w, 4).astype(float)
            a = px[..., 3] > 127
            if not a.any():
                return None
            rgb = px[..., :3][a].mean(axis=0)
            tint = t.fc_tint[f]
            if tint > 0:
                rgb = rgb * np.array({1: (0.57, 0.74, 0.35), 2: (0.47, 0.67, 0.18), 3: (0.25, 0.46, 0.89)}.get(
                    int(tint), (1, 1, 1)))
            return tuple(int(v) for v in rgb)

        top = mean(1)
        side = mean(3) or top
        if top is None or side is None:
            continue
        out[name] = {"top": top, "side": side, "opaque": bool(t.st_flags[sid] & F_OCC),
                     "gravity": any(w in name for w in GRAVITY_WORDS)}
    return out


def candidates(version: str, blocks: str | list | None = None, face: str = "side", allow_gravity: bool = False,
               opaque_only: bool = True) -> tuple[list[str], np.ndarray]:
    """(names, LAB array) of usable blocks. ``blocks``: set name(s) from SETS joined by '+', or a list of names."""
    cols = block_colors(version)
    if isinstance(blocks, (list, tuple)):
        names = [b.removeprefix("minecraft:") for b in blocks if b.removeprefix("minecraft:") in cols]
    else:
        sets = [s.strip() for s in (blocks or "concrete+wool+terracotta").split("+") if s.strip()]
        if "all" in sets:
            names = list(cols)
        else:
            names = [n for n in cols if any(SETS[s](n) for s in sets if s in SETS)]
    names = [n for n in names if (allow_gravity or not cols[n]["gravity"]) and (not opaque_only or cols[n]["opaque"])]
    if not names:
        raise ValueError("no candidate blocks")
    lab = _srgb_to_lab(np.array([cols[n][face] for n in names]))
    return names, lab


def nearest(version: str, rgb, blocks=None, face: str = "side", k: int = 1) -> list[str]:
    names, lab = candidates(version, blocks, face)
    target = _srgb_to_lab(np.array([rgb]))[0]
    d = np.linalg.norm(lab - target, axis=1)
    return [names[i] for i in np.argsort(d)[:k]]


def gradient_between(version: str, a: str, b: str, steps: int = 6, blocks="all", face: str = "side") -> list[str]:
    """Blocks forming a smooth color gradient from block a to block b (inclusive)."""
    cols = block_colors(version)
    a, b = a.removeprefix("minecraft:"), b.removeprefix("minecraft:")
    if a not in cols or b not in cols:
        raise ValueError("both ends must be full, opaque cube blocks")
    names, lab = candidates(version, blocks, face)
    la = _srgb_to_lab(np.array([cols[a][face]]))[0]
    lb = _srgb_to_lab(np.array([cols[b][face]]))[0]
    out = [a]
    for i in range(1, steps - 1):
        target = la + (lb - la) * i / (steps - 1)
        order = np.argsort(np.linalg.norm(lab - target, axis=1))
        for j in order:
            if names[j] not in out and names[j] != b:
                out.append(names[j])
                break
    out.append(b)
    return out


def similar(version: str, block: str, k: int = 8, blocks="all", face: str = "side") -> list[tuple[str, float]]:
    """Blocks closest in color to ``block`` (for texturing mixes)."""
    cols = block_colors(version)
    block = block.removeprefix("minecraft:")
    names, lab = candidates(version, blocks, face)
    target = _srgb_to_lab(np.array([cols[block][face]]))[0]
    d = np.linalg.norm(lab - target, axis=1)
    order = [i for i in np.argsort(d) if names[i] != block][:k]
    return [(names[i], round(float(d[i]), 1)) for i in order]


def image_to_blocks(img_rgb: np.ndarray, version: str, blocks=None, dither: bool = True, face: str = "side") -> np.ndarray:
    """Map an RGB image (H, W, 3) to block names (H, W) with optional Floyd-Steinberg dithering in LAB."""
    names, lab = candidates(version, blocks, face)
    img = _srgb_to_lab(img_rgb.astype(float))
    h, w = img.shape[:2]
    out = np.empty((h, w), dtype=object)
    work = img.copy()
    for y in range(h):
        for x in range(w):
            px = work[y, x]
            d = ((lab - px) ** 2).sum(axis=1)
            i = int(np.argmin(d))
            out[y, x] = names[i]
            if dither:
                err = px - lab[i]
                if x + 1 < w:
                    work[y, x + 1] += err * 7 / 16
                if y + 1 < h:
                    if x > 0:
                        work[y + 1, x - 1] += err * 3 / 16
                    work[y + 1, x] += err * 5 / 16
                    if x + 1 < w:
                        work[y + 1, x + 1] += err * 1 / 16
    return out
