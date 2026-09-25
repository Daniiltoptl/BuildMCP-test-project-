"""Version adaptation of NBT written by BuildMCP.

Scenes store text as JSON text-component strings (the pre-1.21.5 form). From 1.21.5
(DataVersion 4325) the game stores text components as NBT (compounds/strings), so on
export we convert text fields of signs, text displays and custom names.
"""

from __future__ import annotations

import json

import nbtlib

NBT_TEXT_DV = 4325  # 1.21.5


def json_to_nbt_component(value: str):
    """JSON text component string -> NBT component (String for plain text, Compound otherwise)."""
    try:
        obj = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return nbtlib.String(str(value))
    return _obj_to_nbt(obj)


def _obj_to_nbt(obj):
    if isinstance(obj, str):
        return nbtlib.String(obj)
    if isinstance(obj, list):
        items = [_as_compound(_obj_to_nbt(o)) for o in obj]
        return nbtlib.List[nbtlib.Compound](items) if items else nbtlib.List[nbtlib.String]([])
    if isinstance(obj, dict):
        c = nbtlib.Compound()
        for k, v in obj.items():
            if isinstance(v, bool):
                c[k] = nbtlib.Byte(1 if v else 0)
            elif isinstance(v, int):
                c[k] = nbtlib.Int(v)
            elif isinstance(v, float):
                c[k] = nbtlib.Double(v)
            elif k in ("extra", "with") and isinstance(v, list):
                c[k] = nbtlib.List[nbtlib.Compound]([_as_compound(_obj_to_nbt(o)) for o in v])
            else:
                c[k] = _obj_to_nbt(v)
        return c
    return nbtlib.String(str(obj))


def _as_compound(tag):
    if isinstance(tag, nbtlib.Compound):
        return tag
    return nbtlib.Compound({"text": tag if isinstance(tag, nbtlib.String) else nbtlib.String(str(tag))})


def adapt_entity(nbt: nbtlib.Compound, data_version: int) -> nbtlib.Compound:
    if data_version < NBT_TEXT_DV:
        return nbt
    out = nbtlib.Compound(nbt)
    for key in ("text", "CustomName"):
        v = out.get(key)
        if isinstance(v, nbtlib.String):
            out[key] = json_to_nbt_component(str(v))
    return out


def adapt_block_entity(be_id: str, nbt: nbtlib.Compound, data_version: int) -> nbtlib.Compound:
    if data_version < NBT_TEXT_DV:
        return nbt
    out = nbtlib.Compound(nbt)
    if be_id in ("minecraft:sign", "minecraft:hanging_sign"):
        for side in ("front_text", "back_text"):
            st = out.get(side)
            if isinstance(st, nbtlib.Compound) and "messages" in st:
                st = nbtlib.Compound(st)
                msgs = [json_to_nbt_component(str(m)) for m in st["messages"]]
                # NBT lists must be uniform: use compounds unless all are plain strings
                if all(isinstance(m, nbtlib.String) for m in msgs):
                    st["messages"] = nbtlib.List[nbtlib.String](msgs)
                else:
                    st["messages"] = nbtlib.List[nbtlib.Compound]([_as_compound(m) for m in msgs])
                out[side] = st
    v = out.get("CustomName")
    if isinstance(v, nbtlib.String):
        out["CustomName"] = json_to_nbt_component(str(v))
    return out
