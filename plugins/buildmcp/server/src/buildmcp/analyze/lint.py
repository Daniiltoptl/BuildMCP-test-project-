"""Quality and correctness checks for a scene (things that look amateur or break in game)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import ndimage

from ..blocks import families as F
from ..geo.box import Box
from ..geo.mask import as_mask


# plants that hang from the block above instead of standing on the ground
HANGING = ("minecraft:hanging_roots", "minecraft:spore_blossom", "minecraft:pale_hanging_moss")


@dataclass
class Issue:
    severity: str  # error | warning | hint
    kind: str
    message: str
    box: tuple[int, int, int, int, int, int] | None = None
    count: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def _region(scene, where):
    if where is None:
        b = scene.bbox()
    else:
        b = as_mask(where).bbox
    return b


def _box_of_cells(xs, ys, zs, o) -> tuple[int, ...]:
    return (int(xs.min() + o[0]), int(ys.min() + o[1]), int(zs.min() + o[2]),
            int(xs.max() + o[0]), int(ys.max() + o[1]), int(zs.max() + o[2]))


def lint(scene, where=None, flat_area: int = 90, max_issues: int = 60) -> list[Issue]:
    b = _region(scene, where)
    if b is None:
        return []
    box = b.expand(1)
    ids = scene.ids(box)
    o = np.array(box.min)
    kind = scene.kind_lut()[ids]
    issues: list[Issue] = []
    air = kind == F.AIR
    liquid = kind == F.LIQUID
    below_id = np.zeros_like(ids)
    below_id[:, 1:, :] = ids[:, :-1, :]
    below_kind = scene.kind_lut()[below_id]
    below_air = (below_kind == F.AIR) | (below_kind == F.LIQUID)

    # --- plants & attachables without support
    needs_ground = np.isin(kind, [F.PLANT, F.DOUBLE_PLANT, F.CARPET, F.SNOW_LAYER, F.PRESSURE_PLATE, F.SIGN,
                                  F.BANNER, F.TORCH, F.HEAD])
    plants_no_ground = needs_ground & below_air
    # lower halves of double plants only (upper halves stand on the lower)
    if plants_no_ground.any():
        xs, ys, zs = np.nonzero(plants_no_ground)
        keep = []
        for x, y, z in zip(xs, ys, zs):
            st = scene.palette[ids[x, y, z]]
            if "half=upper" in st or "hanging=true" in st:
                continue
            if st.startswith(("minecraft:lily_pad", "minecraft:seagrass", "minecraft:kelp", "minecraft:sea_pickle")):
                continue
            if st.startswith(HANGING) and ids[x, y + 1, z] != 0:
                continue  # hangs from the block above
            keep.append((x, y, z))
        if keep:
            k = np.array(keep)
            issues.append(Issue("warning", "floating_attachments",
                                f"{len(keep)} plants/carpets/torches/signs have nothing under them (they pop off in game).",
                                _box_of_cells(k[:, 0], k[:, 1], k[:, 2], o), len(keep)))

    # --- gravity blocks over air
    # (pointed dripstone hangs from the block above, so it is not a falling block here)
    grav_ids = [i for i, s in enumerate(scene.palette)
                if s.removeprefix("minecraft:").split("[", 1)[0] in F.GRAVITY_BLOCKS
                and not s.startswith("minecraft:pointed_dripstone")]
    if grav_ids:
        g = np.isin(ids, grav_ids) & below_air
        g[:, 0, :] = False
        if g.any():
            xs, ys, zs = np.nonzero(g)
            issues.append(Issue("error", "unsupported_gravity",
                                f"{len(xs)} sand/gravel/concrete powder blocks have air below (they will fall).",
                                _box_of_cells(xs, ys, zs, o), len(xs)))

    # --- non-persistent leaves
    leaf_ids = [i for i, s in enumerate(scene.palette) if "_leaves[" in s and "persistent=false" in s]
    if leaf_ids:
        lf = np.isin(ids, leaf_ids)
        if lf.any():
            xs, ys, zs = np.nonzero(lf)
            issues.append(Issue("error", "leaves_decay",
                                f"{len(xs)} leaves are not persistent (they decay). finalize() fixes this.",
                                _box_of_cells(xs, ys, zs, o), len(xs)))

    # --- water/lava that will spread
    if liquid.any():
        flow = np.zeros_like(liquid)
        for axis, step in ((0, 1), (0, -1), (2, 1), (2, -1), (1, -1)):
            nb = np.roll(air, -step, axis=axis)
            flow |= liquid & nb
        flow[[0, -1], :, :] = False
        flow[:, :, [0, -1]] = False
        flow[:, 0, :] = False
        if flow.any():
            xs, ys, zs = np.nonzero(flow)
            issues.append(Issue("warning", "liquid_spreads",
                                f"{len(xs)} water/lava cells touch air at the side or below — they will flow once updated. "
                                "Fine for waterfalls, otherwise wall them in.",
                                _box_of_cells(xs, ys, zs, o), len(xs)))

    # --- tiny floating fragments (stray blocks)
    solid = ~air & ~liquid
    lab, n = ndimage.label(solid, structure=ndimage.generate_binary_structure(3, 3))
    if n > 1:
        sizes = ndimage.sum(solid, lab, index=np.arange(1, n + 1))
        small = [i + 1 for i, s in enumerate(sizes) if s <= 2]
        if small and len(small) < n:
            sel = np.isin(lab, small)
            # ignore hanging lights/chains and entity-like decorations
            deco = np.isin(kind, [F.LANTERN, F.CHAIN, F.HEAD, F.BANNER, F.WALL_BANNER, F.VINE])
            sel &= ~deco
            if sel.any():
                xs, ys, zs = np.nonzero(sel)
                issues.append(Issue("hint", "stray_blocks",
                                    f"{len(xs)} isolated 1-2 block fragments float unattached (leftovers?).",
                                    _box_of_cells(xs, ys, zs, o), len(xs)))

    # --- large flat single-block faces (the #1 amateur tell)
    issues.extend(_flat_faces(scene, ids, kind, o, flat_area))

    # --- entity budget
    n_display = sum(1 for e in scene.entities if e.id.endswith("_display"))
    if n_display > 400:
        issues.append(Issue("warning", "entity_budget",
                            f"{n_display} display entities — more than ~400 costs client FPS at spawn.", None, n_display))

    order = {"error": 0, "warning": 1, "hint": 2}
    issues.sort(key=lambda i: (order[i.severity], -i.count))
    return issues[:max_issues]


def _flat_faces(scene, ids, kind, o, min_area: int) -> list[Issue]:
    out: list[Issue] = []
    solid = np.isin(kind, [F.FULL, F.LOG])
    air = kind == F.AIR
    for axis, name in ((0, "x"), (2, "z"), (1, "y")):
        for step in (1, -1):
            exposed = solid & np.roll(air, -step, axis=axis)
            if axis == 1 and step == 1:
                continue  # tops of floors/terrain are expected to be large
            if not exposed.any():
                continue
            vals = np.where(exposed, ids.astype(np.int64) + 1, 0)
            for plane in range(vals.shape[axis]):
                if axis == 1 and plane <= 1:
                    continue  # underside of the lowest layer (ground) is never seen
                sl = np.take(vals, plane, axis=axis)
                if not sl.any():
                    continue
                for bid in np.unique(sl[sl > 0]):
                    m = sl == bid
                    if m.sum() < min_area:
                        continue
                    lab, n = ndimage.label(m)
                    if n == 0:
                        continue
                    sizes = ndimage.sum(m, lab, index=np.arange(1, n + 1))
                    for li, sz in enumerate(sizes):
                        if sz < min_area:
                            continue
                        us, vs = np.nonzero(lab == li + 1)
                        coords = [None, None, None]
                        others = [a for a in range(3) if a != axis]
                        coords[axis] = np.array([plane])
                        coords[others[0]] = us
                        coords[others[1]] = vs
                        bx = (int(coords[0].min() + o[0]), int(coords[1].min() + o[1]), int(coords[2].min() + o[2]),
                              int(coords[0].max() + o[0]), int(coords[1].max() + o[1]), int(coords[2].max() + o[2]))
                        block = scene.palette[int(bid) - 1].removeprefix("minecraft:").split("[", 1)[0]
                        facing = {(0, 1): "east", (0, -1): "west", (2, 1): "south", (2, -1): "north", (1, -1): "down"}[(axis, step)]
                        out.append(Issue(
                            "hint", "flat_face",
                            f"Flat {int(sz)}-block face of plain {block} facing {facing}. Add depth (pillars, "
                            "beams, stairs/slab trims, insets) and texture (mix 2-4 similar blocks, gradient to the ground).",
                            bx, int(sz)))
    out.sort(key=lambda i: -i.count)
    return out[:12]


def format_issues(issues: list[Issue]) -> str:
    if not issues:
        return "No issues found."
    lines = []
    for i in issues:
        where = f" @ {i.box}" if i.box else ""
        lines.append(f"[{i.severity}] {i.kind}: {i.message}{where}")
    return "\n".join(lines)
