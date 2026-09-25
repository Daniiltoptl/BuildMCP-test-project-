"""Entities and block entities: holograms (text displays), block/item displays, signs,
banners, player heads with custom textures.

Text is stored as JSON text components; ``io`` converts them to the right NBT form for
the target version when exporting (1.21.5+ uses NBT components).
"""

from __future__ import annotations

import json
import math
from typing import Sequence

import nbtlib

from ..scene import Entity

COLORS = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan",
          "purple", "blue", "brown", "green", "red", "black")


def component(text: str, color: str | None = None, bold: bool = False, italic: bool = False,
              extra: list | None = None) -> str:
    """JSON text component string, e.g. component("PvP", "gold", bold=True)."""
    c: dict = {"text": text}
    if color:
        c["color"] = color
    if bold:
        c["bold"] = True
    if italic:
        c["italic"] = True
    if extra:
        c["extra"] = [json.loads(e) if isinstance(e, str) and e.startswith("{") else e for e in extra]
    return json.dumps(c, ensure_ascii=False)


def _floats(v) -> nbtlib.List:
    return nbtlib.List[nbtlib.Float]([nbtlib.Float(float(x)) for x in v])


def _quat(axis: Sequence[float], degrees: float) -> list[float]:
    ax = [float(a) for a in axis]
    n = math.sqrt(sum(a * a for a in ax)) or 1.0
    s = math.sin(math.radians(degrees) / 2)
    return [ax[0] / n * s, ax[1] / n * s, ax[2] / n * s, math.cos(math.radians(degrees) / 2)]


def transformation(scale: float | Sequence[float] = 1.0, translation: Sequence[float] = (0, 0, 0),
                   rotation: tuple[Sequence[float], float] | None = None) -> nbtlib.Compound:
    """Display transformation. rotation = (axis, degrees), applied around the origin."""
    s = [float(scale)] * 3 if isinstance(scale, (int, float)) else [float(v) for v in scale]
    left = _quat(*rotation) if rotation else [0.0, 0.0, 0.0, 1.0]
    return nbtlib.Compound({
        "translation": _floats(translation), "left_rotation": _floats(left), "scale": _floats(s),
        "right_rotation": _floats([0, 0, 0, 1]),
    })


def hologram(scene, pos: Sequence[float], lines: Sequence[str], *, billboard: str = "center", scale: float = 1.0,
             background: int | None = None, shadow: bool = True, see_through: bool = False,
             line_width: int = 200) -> Entity:
    """Floating text (text_display). ``lines`` are plain strings or JSON components from component().
    Plain strings support '&'-free simple text; use component() for colors."""
    parts = []
    for i, ln in enumerate(lines):
        c = json.loads(ln) if isinstance(ln, str) and ln.strip().startswith("{") else {"text": str(ln)}
        if i < len(lines) - 1:
            c = {"text": "", "extra": [c, {"text": "\n"}]}
        parts.append(c)
    text = json.dumps({"text": "", "extra": parts}, ensure_ascii=False)
    nbt = nbtlib.Compound({
        "text": nbtlib.String(text),
        "billboard": nbtlib.String(billboard),
        "shadow": nbtlib.Byte(1 if shadow else 0),
        "see_through": nbtlib.Byte(1 if see_through else 0),
        "line_width": nbtlib.Int(line_width),
        "transformation": transformation(scale),
    })
    if background is not None:
        nbt["background"] = nbtlib.Int(background if background < 2 ** 31 else background - 2 ** 32)
    return scene.add_entity("text_display", pos, nbt)


def block_display(scene, pos: Sequence[float], block: str, *, scale: float | Sequence[float] = 1.0,
                  rotation: tuple[Sequence[float], float] | None = None, translation=(0, 0, 0),
                  brightness: int | None = None, glow: bool = False) -> Entity:
    """A block rendered as an entity: any scale/rotation, no collision (detail, floating objects)."""
    from ..blocks.registry import parse_state

    name, props, _ = parse_state(scene.reg.canonical(block))
    bs = nbtlib.Compound({"Name": nbtlib.String("minecraft:" + name)})
    if props:
        bs["Properties"] = nbtlib.Compound({k: nbtlib.String(v) for k, v in props.items()})
    nbt = nbtlib.Compound({"block_state": bs, "transformation": transformation(scale, translation, rotation)})
    if brightness is not None:
        nbt["brightness"] = nbtlib.Compound({"sky": nbtlib.Int(brightness), "block": nbtlib.Int(brightness)})
    if glow:
        nbt["Glowing"] = nbtlib.Byte(1)
    return scene.add_entity("block_display", pos, nbt)


def item_display(scene, pos: Sequence[float], item: str, *, scale: float = 1.0,
                 rotation: tuple[Sequence[float], float] | None = None, billboard: str = "fixed",
                 display: str = "fixed") -> Entity:
    """An item rendered in the world (giant swords, crowns, trophies)."""
    iid = item if ":" in item else "minecraft:" + item
    nbt = nbtlib.Compound({
        "item": nbtlib.Compound({"id": nbtlib.String(iid), "count": nbtlib.Int(1)}),
        "item_display": nbtlib.String(display),
        "billboard": nbtlib.String(billboard),
        "transformation": transformation(scale, (0, 0, 0), rotation),
    })
    return scene.add_entity("item_display", pos, nbt)


def sign(scene, pos: Sequence[int], lines: Sequence[str], *, wood: str = "oak", facing: str | None = None,
         rotation: int = 0, color: str = "black", glowing: bool = False) -> None:
    """Standing sign (``rotation`` 0-15) or wall sign (``facing``) with up to 4 lines."""
    msgs = [json.dumps({"text": ln}, ensure_ascii=False) for ln in list(lines)[:4]]
    msgs += ['""'] * (4 - len(msgs))
    side = nbtlib.Compound({
        "messages": nbtlib.List[nbtlib.String]([nbtlib.String(m) for m in msgs]),
        "color": nbtlib.String(color), "has_glowing_text": nbtlib.Byte(1 if glowing else 0),
    })
    empty = nbtlib.Compound({
        "messages": nbtlib.List[nbtlib.String]([nbtlib.String('""')] * 4),
        "color": nbtlib.String("black"), "has_glowing_text": nbtlib.Byte(0),
    })
    nbt = nbtlib.Compound({"front_text": side, "back_text": empty, "is_waxed": nbtlib.Byte(1)})
    x, y, z = (int(v) for v in pos)
    state = f"{wood}_wall_sign[facing={facing}]" if facing else f"{wood}_sign[rotation={rotation}]"
    scene.set(x, y, z, state)
    scene.set_nbt(x, y, z, nbt)


def banner(scene, pos: Sequence[int], color: str = "red", patterns: Sequence[tuple[str, str]] = (), *,
           facing: str | None = None, rotation: int = 0) -> None:
    """Banner with patterns [(pattern, color)], e.g. [("stripe_center", "yellow"), ("border", "black")]."""
    x, y, z = (int(v) for v in pos)
    state = f"{color}_wall_banner[facing={facing}]" if facing else f"{color}_banner[rotation={rotation}]"
    scene.set(x, y, z, state)
    if patterns:
        pl = nbtlib.List[nbtlib.Compound]([
            nbtlib.Compound({"pattern": nbtlib.String("minecraft:" + p), "color": nbtlib.String(c)}) for p, c in patterns
        ])
        scene.set_nbt(x, y, z, nbtlib.Compound({"patterns": pl}))


def head(scene, pos: Sequence[int], texture: str | None = None, *, rotation: int = 0, facing: str | None = None,
         name: str | None = None) -> None:
    """Player head. ``texture`` = the base64 'textures' value (e.g. from minecraft-heads.com)."""
    x, y, z = (int(v) for v in pos)
    state = f"player_wall_head[facing={facing}]" if facing else f"player_head[rotation={rotation}]"
    scene.set(x, y, z, state)
    if texture or name:
        prof = nbtlib.Compound()
        if name:
            prof["name"] = nbtlib.String(name)
        if texture:
            prof["properties"] = nbtlib.List[nbtlib.Compound]([
                nbtlib.Compound({"name": nbtlib.String("textures"), "value": nbtlib.String(texture)})])
        scene.set_nbt(x, y, z, nbtlib.Compound({"profile": prof}))
