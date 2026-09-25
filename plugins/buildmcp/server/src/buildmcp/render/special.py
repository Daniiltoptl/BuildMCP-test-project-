"""Approximate geometry for blocks the game draws with entity renderers (no JSON model):
chests, signs, banners, beds, heads, shulker boxes, decorated pots, bells, portals.
Returns (elements, textures, y_rotation_degrees) in block-model JSON format.
"""

from __future__ import annotations

WOODS = ("pale_oak", "dark_oak", "oak", "spruce", "birch", "jungle", "acacia", "mangrove", "cherry", "bamboo",
         "crimson", "warped")
COLORS = ("light_blue", "light_gray", "white", "orange", "magenta", "yellow", "lime", "pink", "gray", "cyan",
          "purple", "blue", "brown", "green", "red", "black")

FACING_Y = {"south": 180.0, "west": 270.0, "north": 0.0, "east": 90.0}


def _box(fr, to, tex="#t", faces=("down", "up", "north", "south", "west", "east")) -> dict:
    return {"from": list(fr), "to": list(to), "faces": {f: {"texture": tex} for f in faces}}


def _wood_of(name: str) -> str:
    for w in WOODS:
        if name.startswith(w + "_"):
            return w
    return "oak"


def _color_of(name: str) -> str:
    for c in COLORS:
        if name.startswith(c + "_"):
            return c
    return "white"


def _planks(wood: str) -> str:
    return f"block/{wood}_planks"


def proxy(name: str, props: dict) -> tuple[list, dict, float] | None:
    rot16 = float(props.get("rotation", "0")) * 22.5
    facing_y = FACING_Y.get(props.get("facing", "north"), 0.0)
    if name.endswith("_wall_hanging_sign"):
        t = {"t": _planks(_wood_of(name)), "c": "block/chain"}
        return [_box((1, 0, 7), (15, 10, 9)), _box((0, 14, 6), (16, 16, 10))], t, facing_y
    if name.endswith("_hanging_sign"):
        t = {"t": _planks(_wood_of(name))}
        return [_box((1, 0, 7), (15, 10, 9)), _box((3, 10, 7.5), (4, 16, 8.5)), _box((12, 10, 7.5), (13, 16, 8.5))], t, rot16
    if name.endswith("_wall_sign"):
        t = {"t": _planks(_wood_of(name))}
        return [_box((0, 4.5, 14.5), (16, 12.5, 16))], t, facing_y
    if name.endswith("_sign"):
        t = {"t": _planks(_wood_of(name))}
        return [_box((0, 7.5, 7.3), (16, 15.5, 8.7)), _box((7.3, 0, 7.3), (8.7, 7.5, 8.7))], t, rot16
    if name.endswith("_wall_banner"):
        t = {"t": f"block/{_color_of(name)}_wool", "p": _planks("dark_oak")}
        return [_box((1, -14, 14.6), (15, 13, 15.4)), _box((0, 13, 14), (16, 15, 16), "#p")], t, facing_y
    if name.endswith("_banner"):
        t = {"t": f"block/{_color_of(name)}_wool", "p": _planks("dark_oak")}
        return [_box((1, 2, 7.6), (15, 29, 8.4)), _box((7.4, 0, 7.4), (8.6, 31, 8.6), "#p"),
                _box((1, 29, 7.2), (15, 31, 8.8), "#p")], t, rot16
    if name.endswith("_bed"):
        t = {"t": f"block/{_color_of(name)}_wool", "p": _planks("oak")}
        return [_box((0, 3, 0), (16, 9, 16)), _box((0, 0, 0), (3, 3, 3), "#p"), _box((13, 0, 0), (16, 3, 3), "#p"),
                _box((0, 0, 13), (3, 3, 16), "#p"), _box((13, 0, 13), (16, 3, 16), "#p")], t, facing_y
    if name in ("chest", "trapped_chest") or name.endswith("copper_chest"):
        if name.endswith("copper_chest"):
            base = name.replace("waxed_", "").removesuffix("_chest")  # copper / exposed_copper / ...
            tex = "block/" + base.replace("copper", "cut_copper")
        else:
            tex = "block/oak_planks"
        return [_box((1, 0, 1), (15, 14, 15)), _box((7, 7, 0), (9, 11, 1), "#l")], \
            {"t": tex, "l": "block/iron_block"}, facing_y
    if name == "ender_chest":
        return [_box((1, 0, 1), (15, 14, 15)), _box((7, 7, 0), (9, 11, 1), "#l")], \
            {"t": "block/obsidian", "l": "block/gold_block"}, facing_y
    if name.endswith("shulker_box"):
        return [_box((0, 0, 0), (16, 16, 16))], {"t": f"block/{name}"}, 0.0
    skull_tex = {
        "skeleton": "block/bone_block_side", "wither_skeleton": "block/blackstone", "zombie": "block/green_terracotta",
        "creeper": "block/lime_concrete", "player": "block/brown_terracotta", "piglin": "block/pink_terracotta",
        "dragon": "block/black_concrete",
    }
    for kind, tex in skull_tex.items():
        if name in (f"{kind}_wall_skull", f"{kind}_wall_head"):
            return [_box((4, 4, 8), (12, 12, 16))], {"t": tex}, facing_y
        if name in (f"{kind}_skull", f"{kind}_head"):
            return [_box((4, 0, 4), (12, 8, 12))], {"t": tex}, rot16
    if name == "decorated_pot":
        return [_box((1, 0, 1), (15, 16, 15)), _box((4, 16, 4), (12, 20, 12))], {"t": "block/terracotta"}, facing_y
    if name == "conduit":
        return [_box((5, 5, 5), (11, 11, 11))], {"t": "block/prismarine_bricks"}, 0.0
    if name == "bell":
        return [_box((4, 3, 4), (12, 12, 12))], {"t": "block/gold_block"}, facing_y
    if name == "end_portal":
        return [_box((0, 0, 0), (16, 12, 16))], {"t": "block/black_concrete"}, 0.0
    if name == "end_gateway":
        return [_box((0, 0, 0), (16, 16, 16))], {"t": "block/black_concrete"}, 0.0
    if name.endswith("copper_golem_statue"):
        return [_box((4, 0, 4), (12, 14, 12))], {"t": "block/copper_block"}, facing_y
    return None
