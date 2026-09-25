"""Neighbor-aware block updates, computed the way the game would.

WorldEdit/FAWE pastes (and our bridge) place states exactly as given, without physics.
So fences must already know their connections, stairs their corner shapes, walls their
tall/low sides, leaves must be persistent, double plants need both halves, etc.
``finalize(scene)`` computes all of that. Run it after building, before export/paste
(the MCP layer does it automatically).
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from . import families as F
from .registry import format_state, parse_state

DIRS = {  # name: (dx, dy, dz)
    "north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0),
    "up": (0, 1, 0), "down": (0, -1, 0),
}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
H4 = ("north", "east", "south", "west")
CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
CCW = {v: k for k, v in CW.items()}

WALL_POST_OVERRIDE_SUFFIX = ("_sign", "_banner", "_pressure_plate", "torch")
WALL_TESTS = {  # (u1, v1, u2, v2) on the DOWN face (u = x, v = z), in 1/16 block
    "post": (7, 7, 9, 9), "north": (7, 0, 9, 9), "south": (7, 7, 9, 16), "west": (0, 7, 9, 9), "east": (7, 7, 16, 9),
}


class _Ctx:
    """Working copy of a region (with a 1-block margin) and state decoding caches."""

    def __init__(self, scene, box):
        self.scene = scene
        self.reg = scene.reg
        self.box = box.expand(1)
        self.ids = scene.ids(self.box)
        self.o = np.array(self.box.min)
        self._decoded: dict[int, tuple[str, dict]] = {}
        self.kind = scene.kind_lut()
        self.changes: dict[str, int] = {}

    def refresh_kind(self):
        self.kind = self.scene.kind_lut()

    def dec(self, idx: int) -> tuple[str, dict]:
        d = self._decoded.get(idx)
        if d is None:
            name, props, _ = parse_state(self.scene.palette[idx])
            d = (name, props)
            self._decoded[idx] = d
        return d

    def at(self, lx: int, ly: int, lz: int) -> int:
        sx, sy, sz = self.ids.shape
        if 0 <= lx < sx and 0 <= ly < sy and 0 <= lz < sz:
            return int(self.ids[lx, ly, lz])
        return 0

    def nb(self, lx: int, ly: int, lz: int, d: str) -> int:
        dx, dy, dz = DIRS[d]
        return self.at(lx + dx, ly + dy, lz + dz)

    def set(self, lx: int, ly: int, lz: int, state: str, rule: str) -> None:
        new_id = self.scene.id_of(state)
        if new_id == self.ids[lx, ly, lz]:
            return
        if len(self.kind) <= new_id:
            self.refresh_kind()
        self.ids[lx, ly, lz] = new_id
        w = self.o + np.array([lx, ly, lz]) - self.scene.origin
        self.scene.data[w[0], w[1], w[2]] = new_id
        self.changes[rule] = self.changes.get(rule, 0) + 1

    def positions(self, kinds: tuple[int, ...], inner: bool = True):
        mask = np.isin(self.kind[self.ids], kinds)
        if inner:
            mask[[0, -1], :, :] = False
            mask[:, [0, -1], :] = False
            mask[:, :, [0, -1]] = False
        return list(zip(*[a.tolist() for a in np.nonzero(mask)]))

    def state(self, idx: int) -> str:
        return self.scene.palette[idx]

    def name(self, idx: int) -> str:
        return self.dec(idx)[0]


def _with(name: str, props: dict, **changes) -> str:
    p = dict(props)
    p.update({k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in changes.items()})
    return format_state(name, p)


# ------------------------------------------------------------------ rules
def _leaves(c: _Ctx) -> None:
    """Leaves: persistent (never decay) and the distance to the nearest log the game would compute
    (logs 0, through any leaves, capped at 7), so pastes with and without block updates agree."""
    kind = c.kind[c.ids]
    leaf = kind == F.LEAVES
    if not leaf.any():
        return
    names = np.array([parse_state(st)[0].endswith(("_log", "_wood", "_stem", "_hyphae")) for st in c.scene.palette])
    log = names[c.ids]
    dist = np.full(c.ids.shape, 7, dtype=np.int8)
    dist[log] = 0
    for _ in range(7):
        nb = np.full(c.ids.shape, 7, dtype=np.int8)
        for axis in range(3):
            for shift in (1, -1):
                rolled = np.roll(dist, shift, axis=axis)
                edge = [slice(None)] * 3
                edge[axis] = 0 if shift == 1 else -1
                rolled[tuple(edge)] = 7
                nb = np.minimum(nb, rolled)
        new = np.where(leaf, np.minimum(7, nb + 1), dist).astype(np.int8)
        new[log] = 0
        if np.array_equal(new, dist):
            break
        dist = new
    for p in c.positions((F.LEAVES,)):
        name, props = c.dec(c.ids[p])
        d = str(int(dist[p]))
        if props.get("persistent") != "true" or props.get("distance") != d:
            c.set(*p, _with(name, props, persistent="true", distance=d), "leaves")


def _is_wall(c: _Ctx, idx: int) -> bool:
    return c.kind[idx] == F.WALL


def _gate_connects(c: _Ctx, idx: int, direction: str) -> bool:
    if c.kind[idx] != F.FENCE_GATE:
        return False
    facing = c.dec(idx)[1].get("facing", "north")
    axis = "z" if facing in ("north", "south") else "x"
    cw_axis = "z" if CW[direction] in ("north", "south") else "x"
    return axis == cw_axis


def _sturdy_toward(c: _Ctx, idx: int, direction: str) -> bool:
    """Is the neighbor (state ``idx``) solid on the face that looks back at us?"""
    if idx == 0:
        return False
    return F.connects_as_solid(c.reg, c.state(idx), OPP[direction])


def _fences_panes(c: _Ctx) -> None:
    cache: dict[tuple, str] = {}
    for p in c.positions((F.FENCE, F.PANE)):
        me = int(c.ids[p])
        nbs = tuple(c.nb(*p, d) for d in H4)
        key = (me, nbs)
        new = cache.get(key)
        if new is None:
            name, props = c.dec(me)
            kind = c.kind[me]
            wooden = name != "nether_brick_fence"
            conn = {}
            for d, n in zip(H4, nbs):
                nk = c.kind[n]
                if kind == F.FENCE:
                    same = nk == F.FENCE and ((c.name(n) != "nether_brick_fence") == wooden)
                    ok = same or _gate_connects(c, n, d) or _sturdy_toward(c, n, d)
                else:
                    ok = nk == F.PANE or nk == F.WALL or _sturdy_toward(c, n, d)
                conn[d] = "true" if ok else "false"
            new = _with(name, props, **conn)
            cache[key] = new
        c.set(*p, new, "connections")


def _walls(c: _Ctx) -> None:
    pos = c.positions((F.WALL,))
    pos.sort(key=lambda p: -p[1])  # top-down: a wall's post depends on the wall above
    for p in pos:
        me = int(c.ids[p])
        name, props = c.dec(me)
        conn = {}
        for d in H4:
            n = c.nb(*p, d)
            nk = c.kind[n]
            conn[d] = nk == F.WALL or nk == F.PANE or _gate_connects(c, n, d) or _sturdy_toward(c, n, d)
        above = c.nb(*p, "up")
        above_state = c.state(above)
        sides = {}
        for d in H4:
            if not conn[d]:
                sides[d] = "none"
            else:
                covered = above != 0 and c.reg.face_covers(above_state, "down", WALL_TESTS[d])
                sides[d] = "tall" if covered else "low"
        # shouldRaisePost
        up = False
        if c.kind[above] == F.WALL and c.dec(above)[1].get("up") == "true":
            up = True
        else:
            none = {d: sides[d] == "none" for d in H4}
            if (all(none.values()) or none["south"] != none["north"] or none["west"] != none["east"]):
                up = True
            elif (sides["north"] == "tall" and sides["south"] == "tall") or (sides["east"] == "tall" and sides["west"] == "tall"):
                up = False
            else:
                an = c.name(above) if above else ""
                up = an.endswith(WALL_POST_OVERRIDE_SUFFIX) or (
                    above != 0 and c.reg.face_covers(above_state, "down", WALL_TESTS["post"]))
        c.set(*p, _with(name, props, up=up, **sides), "connections")


def _gates(c: _Ctx) -> None:
    for p in c.positions((F.FENCE_GATE,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        facing = props.get("facing", "north")
        side = ("west", "east") if facing in ("north", "south") else ("north", "south")
        in_wall = any(_is_wall(c, c.nb(*p, d)) for d in side)
        c.set(*p, _with(name, props, in_wall=in_wall), "connections")


def _stairs(c: _Ctx) -> None:
    def is_stairs(i: int) -> bool:
        return c.kind[i] == F.STAIRS

    for p in c.positions((F.STAIRS,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        facing, half = props["facing"], props["half"]

        def can_take(face: str) -> bool:
            n = c.nb(*p, face)
            if not is_stairs(n):
                return True
            np_ = c.dec(n)[1]
            return np_["facing"] != facing or np_["half"] != half

        shape = "straight"
        front = c.nb(*p, facing)
        if is_stairs(front) and c.dec(front)[1]["half"] == half:
            f1 = c.dec(front)[1]["facing"]
            if _axis(f1) != _axis(facing) and can_take(OPP[f1]):
                shape = "outer_left" if f1 == CCW[facing] else "outer_right"
        if shape == "straight":
            back = c.nb(*p, OPP[facing])
            if is_stairs(back) and c.dec(back)[1]["half"] == half:
                f2 = c.dec(back)[1]["facing"]
                if _axis(f2) != _axis(facing) and can_take(f2):
                    shape = "inner_left" if f2 == CCW[facing] else "inner_right"
        if props.get("shape") != shape:
            c.set(*p, _with(name, props, shape=shape), "stairs_shape")


def _axis(d: str) -> str:
    return "z" if d in ("north", "south") else "x"


def _double_blocks(c: _Ctx) -> None:
    free = lambda i: c.kind[i] in (F.AIR, F.PLANT) or c.name(i) in ("water", "snow")  # noqa: E731
    for p in c.positions((F.DOUBLE_PLANT, F.DOOR)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        half = props.get("half")
        x, y, z = p
        if half == "lower":
            up = c.at(x, y + 1, z)
            un, uprops = c.dec(up) if up else ("air", {})
            if un != name:
                if up == 0 or free(up):
                    if y + 1 < c.ids.shape[1] - 1:
                        c.set(x, y + 1, z, _with(name, props, half="upper"), "double_blocks")
            elif c.kind[me] == F.DOOR:
                want = _with(name, {**uprops, **{k: v for k, v in props.items() if k != "half"}}, half="upper")
                c.set(x, y + 1, z, want, "double_blocks")
        elif half == "upper":
            below = c.at(x, y - 1, z)
            if c.name(below) != name or c.dec(below)[1].get("half") != "lower":
                c.set(x, y, z, "minecraft:air", "double_blocks")


def _beds(c: _Ctx) -> None:
    for p in c.positions((F.BED,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        facing = props.get("facing", "north")
        dx, _, dz = DIRS[facing]
        x, y, z = p
        if props.get("part") == "foot":
            h = c.at(x + dx, y, z + dz)
            if c.name(h) != name and (h == 0 or c.kind[h] == F.PLANT):
                c.set(x + dx, y, z + dz, _with(name, props, part="head"), "beds")
        else:
            f = c.at(x - dx, y, z - dz)
            if c.name(f) != name and (f == 0 or c.kind[f] == F.PLANT):
                c.set(x - dx, y, z - dz, _with(name, props, part="foot"), "beds")


_SPREADING = {"grass_block", "mycelium"}  # these turn into dirt when covered
_WATERY = {"bubble_column", "kelp", "kelp_plant", "seagrass", "tall_seagrass"}  # always full of water
_SHAPE_OCCLUDERS = {"dirt_path", "farmland"}  # partial blocks whose full bottom face blocks light


def _covers_grass(c: _Ctx, idx: int) -> bool:
    """Would this block above grass turn it into dirt (on a random tick, like the game)?"""
    if idx == 0:
        return False
    name, props = c.dec(idx)
    if name == "snow":
        return props.get("layers", "1") != "1"
    if name in ("water", "lava"):
        lvl = int(props.get("level", "0"))
        return lvl == 0 or lvl >= 8  # a source or a falling column is a full fluid block
    if name in _WATERY or props.get("waterlogged") == "true":
        return True
    if name.endswith("_slab"):
        return props.get("type") in ("bottom", "double")
    if name.endswith("_stairs"):
        return props.get("half") == "bottom"
    if name in _SHAPE_OCCLUDERS:
        return True
    try:
        return c.reg.info(name).filter_light >= 15
    except Exception:  # noqa: BLE001
        return False


def _grass_decay(c: _Ctx) -> None:
    """Grass and mycelium under an opaque block, a bottom slab/stairs, 2+ snow layers or water become
    dirt in the game after a few random ticks; do it now so the paste looks the same an hour later."""
    pal = c.scene.palette
    cand = [i for i, st in enumerate(pal) if parse_state(st)[0] in _SPREADING]
    if not cand:
        return
    mask = np.isin(c.ids, cand)
    mask[[0, -1], :, :] = False
    mask[:, [0, -1], :] = False
    mask[:, :, [0, -1]] = False
    cache: dict[int, bool] = {}
    for p in zip(*[a.tolist() for a in np.nonzero(mask)]):
        above = c.nb(*p, "up")
        hit = cache.get(above)
        if hit is None:
            hit = cache[above] = _covers_grass(c, above)
        if hit:
            c.set(*p, "minecraft:dirt", "grass_decay")


_SNOWY = {"grass_block", "podzol", "mycelium"}


def _snowy(c: _Ctx) -> None:
    ids = c.ids
    pal = c.scene.palette
    cand = [i for i, s in enumerate(pal) if parse_state(s)[0] in _SNOWY]
    if not cand:
        return
    mask = np.isin(ids, cand)
    mask[[0, -1], :, :] = False
    mask[:, [0, -1], :] = False
    mask[:, :, [0, -1]] = False
    for p in zip(*[a.tolist() for a in np.nonzero(mask)]):
        me = int(ids[p])
        name, props = c.dec(me)
        above = c.name(c.nb(*p, "up"))
        snowy = above in ("snow", "snow_block", "powder_snow")
        if (props.get("snowy") == "true") != snowy:
            c.set(*p, _with(name, props, snowy=snowy), "snowy")


def _lanterns(c: _Ctx) -> None:
    for p in c.positions((F.LANTERN,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        above, below = c.nb(*p, "up"), c.nb(*p, "down")
        up_ok = above != 0 and c.reg.center_support(c.state(above), "down")
        down_ok = below != 0 and c.reg.center_support(c.state(below), "up")
        hanging = props.get("hanging") == "true"
        if hanging and not up_ok and down_ok:
            c.set(*p, _with(name, props, hanging=False), "lanterns")
        elif not hanging and not down_ok and up_ok:
            c.set(*p, _with(name, props, hanging=True), "lanterns")


def _mushrooms(c: _Ctx) -> None:
    for p in c.positions((F.MUSHROOM_BLOCK,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        faces = {d: c.name(c.nb(*p, d)) != name for d in DIRS}
        c.set(*p, _with(name, props, **faces), "mushroom_faces")


def _dripstone(c: _Ctx) -> None:
    def dir_of(i: int) -> str | None:
        if c.name(i) != "pointed_dripstone":
            return None
        return c.dec(i)[1].get("vertical_direction")

    for p in c.positions((F.DRIPSTONE,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        vd = props.get("vertical_direction", "up")
        tip_dir = "up" if vd == "up" else "down"
        nxt = c.nb(*p, tip_dir)
        if dir_of(nxt) == ("down" if vd == "up" else "up"):
            th = "tip_merge"
        elif dir_of(nxt) != vd:
            th = "tip"
        else:
            nth = c.dec(nxt)[1].get("thickness")
            if nth in ("tip", "tip_merge"):
                th = "frustum"
            else:
                behind = c.nb(*p, OPP[tip_dir])
                th = "base" if dir_of(behind) != vd else "middle"
        if props.get("thickness") != th:
            c.set(*p, _with(name, props, thickness=th), "dripstone")


def _hanging_plants(c: _Ctx) -> None:
    for p in c.positions((F.HANGING_PLANT,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        head = F.HANGING_PLANT_HEADS.get(name, name)
        body = F.HANGING_PLANT_BODY[head]
        grow = "down" if F.HANGING_PLANT_DIR[head] < 0 else "up"
        nxt = c.name(c.nb(*p, grow))
        is_body = nxt in (head, body)
        want = body if is_body else head
        if want != name:
            if want == head:
                new = c.reg.canonical(head)
                if "berries" in props:
                    new = c.reg.with_props(new, berries=props["berries"])
            else:
                new = c.reg.canonical(body)
                if "berries" in props and "berries" in dict(c.reg.info(body).default_props()):
                    new = c.reg.with_props(new, berries=props["berries"])
            c.set(*p, new, "hanging_plants")


def _vines(c: _Ctx) -> None:
    for p in c.positions((F.VINE,)):
        me = int(c.ids[p])
        name, props = c.dec(me)
        faces = [d for d in DIRS if props.get(d) == "true"]
        keep = {}
        above = c.nb(*p, "up")
        for d in DIRS:
            if d not in props:
                continue
            if props[d] != "true":
                keep[d] = False
                continue
            n = c.nb(*p, d)
            ok = n != 0 and c.reg.face_sturdy(c.state(n), OPP[d])
            if not ok and name == "vine" and d != "up" and c.name(above) == "vine" and c.dec(above)[1].get(d) == "true":
                ok = True
            keep[d] = ok
        if not any(keep.values()):
            if faces:
                c.set(*p, "minecraft:air", "vines_removed")
            continue
        if any(keep[d] != (props.get(d) == "true") for d in keep):
            c.set(*p, _with(name, props, **keep), "vines")


_GRAVITY_SUBST = {"sand": "sandstone", "red_sand": "red_sandstone", "gravel": "andesite",
                  "suspicious_sand": "sandstone", "suspicious_gravel": "andesite"}


def _gravity(c: _Ctx) -> None:
    """Sand/gravel/concrete powder with nothing below would fall: swap for a stable look-alike."""
    for i, st in enumerate(c.scene.palette):
        name = parse_state(st)[0]
        if name in _GRAVITY_SUBST or name.endswith("_concrete_powder"):
            sub = _GRAVITY_SUBST.get(name) or name.replace("_concrete_powder", "_concrete")
            mask = c.ids == i
            if not mask.any():
                continue
            for p in zip(*[a.tolist() for a in np.nonzero(mask)]):
                below = c.nb(*p, "down")
                if c.kind[below] in (F.AIR, F.LIQUID, F.PLANT, F.DOUBLE_PLANT, F.VINE):
                    c.set(*p, "minecraft:" + sub, "gravity_fixed")


# Order matters: a wall's tall sides and post follow the collision shape of the block above it
# (a fence's arms, stairs' corners, a lantern's hanging state), so walls go last.
RULES: dict[str, Callable[[_Ctx], None]] = {
    "gravity": _gravity,
    "leaves": _leaves,
    "double_blocks": _double_blocks,
    "beds": _beds,
    "mushrooms": _mushrooms,
    "dripstone": _dripstone,
    "hanging_plants": _hanging_plants,
    "vines": _vines,
    "grass_decay": _grass_decay,
    "snowy": _snowy,
    "fences": _fences_panes,
    "gates": _gates,
    "stairs": _stairs,
    "lanterns": _lanterns,
    "walls": _walls,
}


def finalize(scene, where=None, rules: list[str] | None = None) -> dict[str, int]:
    """Apply game-like neighbor updates in ``where`` (default: whole scene). Returns change counts."""
    from ..geo.box import Box
    from ..geo.mask import as_mask

    if where is None:
        box = scene.bbox()
    else:
        box = as_mask(where).bbox
    if box is None:
        return {}
    scene.ensure(Box.of(box).expand(1))
    ctx = _Ctx(scene, Box.of(box))
    for name in rules or list(RULES):
        RULES[name](ctx)
        ctx.refresh_kind()
    scene.dirty_version += 1
    return ctx.changes
