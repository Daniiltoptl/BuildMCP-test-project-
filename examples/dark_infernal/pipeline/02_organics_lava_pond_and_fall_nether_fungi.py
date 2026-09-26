import math
top = Box(-32, 76, -32, 32, 84, 28)
paved = S.mask("polished_blackstone_bricks|cracked_polished_blackstone_bricks|polished_blackstone|gilded_blackstone|"
               "soul_soil|blackstone|basalt|#stairs|#slabs", where=Box(-32, 80, -32, 32, 81, 28))
keep = paved.dilate(1, horizontal=True) | Mask.box(Box(-10, 78, -26, 10, 125, -5))  # citadel and forecourt
keep = keep | Mask.box(Box(-9, 78, -3, 9, 100, 26))  # the processional way and the platform stay open
sx, sy, sz = S.markers["spawn"].pos
for name in ("pvp", "anarchy"):
    x, y, z = (int(v) for v in S.markers[name].pos)
    keep = keep | Mask.box(Box(x - 4, 78, z - 4, x + 4, 95, z + 4))
    for t in np.linspace(0, 1, 24):  # sight lines from the spawn to the portals
        px, pz = round(sx + (x - sx) * t), round(sz + (z - sz) * t)
        keep = keep | Mask.box(Box(px - 5, 78, pz - 5, px + 5, 95, pz + 5))

# a lava pool west of the way and a lavafall pouring off the east rim
terrain.pond((-13, 80, 9), radius=4.5, depth=3, seed=6, lily=0)
edge_x = next(x for x in range(20, 40) if (S.top_y(x, 4) or 0) < 77)
terrain.waterfall((edge_x - 1, 80, 4), direction="east", width=2, drop=34, liquid="lava")
# basalt spikes on the rim: dark silhouettes around the citadel
for i, (x, z, h, lean) in enumerate([(-24, -12, 10, (-0.2, 0.0)), (24, -14, 11, (0.2, -0.05)),
                                     (-10, -25, 9, (0.0, -0.2)), (11, -25, 10, (0.05, -0.2)),
                                     (-25, 8, 8, (-0.2, 0.1)), (25, 9, 9, (0.2, 0.1))]):
    rocks.spike((x, S.top_y(x, z) or 80, z), height=h, radius=1.9, lean=lean, seed=40 + i)
# giant nether fungi as a backdrop behind the portals and the citadel, dead trees on the rim
for i, (x, z, h) in enumerate([(-23, -3, 13), (23, -2, 12), (-14, -22, 12), (15, -23, 13)]):
    trees.tree((x, S.top_y(x, z) or 80, z), "fungus_giant", height=h, seed=11 + i)
ground = S.surface(where=top, pattern="crimson_nylium|warped_nylium|netherrack|soul_soil")
trees.forest(ground, kinds=["dead", "fungus_giant", "dead"], count=6, min_dist=8, avoid=keep, seed=8)
for i, (x, z) in enumerate([(-22, 12), (21, 13), (-3, -27)]):
    rocks.boulder((x, S.top_y(x, z) or 80, z), size=1.8, seed=20 + i)
ground = S.surface(where=top, pattern="crimson_nylium|warped_nylium|netherrack|soul_soil")
terrain.cover(ground, density=0.4, avoid=keep, seed=9)
# drop tiny wood fragments a tree left hanging over the rim (a root cut off by the terrain)
from scipy import ndimage
bb = S.bbox()
ids = S.ids(bb)
solid_ids = [i for i, st in enumerate(S.palette) if i and not st.startswith(("minecraft:lava", "minecraft:water"))]
solid = np.isin(ids, solid_ids)
lab, n = ndimage.label(solid, structure=np.ones((3, 3, 3), bool))
sizes = np.bincount(lab.ravel())
for x, y, z in np.argwhere(solid & (sizes[lab] <= 2)).tolist():
    if any(k in S.palette[ids[x, y, z]] for k in ("_wood", "_log", "_stem", "hyphae")):
        S.set(x + bb.x1, y + bb.y1, z + bb.z1, "air")
