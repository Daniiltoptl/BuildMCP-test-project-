import math
top = Box(-32, 76, -32, 32, 84, 28)
paved = S.mask("stone_bricks|cobblestone|andesite|snow_block|packed_ice|polished_andesite|smooth_stone|stone|"
               "#stairs|#slabs", where=Box(-32, 80, -32, 32, 81, 28))
keep = paved.dilate(1, horizontal=True) | Mask.box(Box(-8, 78, -28, 15, 120, -5))  # longhouse and tower
keep = keep | Mask.box(Box(-8, 78, -2, 8, 100, 26))  # the road and the spawn platform stay open
sx, sy, sz = S.markers["spawn"].pos
for name in ("survival", "hardcore"):
    x, y, z = (int(v) for v in S.markers[name].pos)
    keep = keep | Mask.box(Box(x - 4, 78, z - 4, x + 4, 95, z + 4))
    for t in np.linspace(0, 1, 24):
        px, pz = round(sx + (x - sx) * t), round(sz + (z - sz) * t)
        keep = keep | Mask.box(Box(px - 5, 78, pz - 5, px + 5, 95, pz + 5))

# a frozen pond west of the road: water under a crust of ice with a few holes
pond = terrain.pond((-13, 80, 10), radius=4.5, depth=3, seed=6, lily=0)
for x, y, z in S.mask("water", where=Box(-19, 78, 4, -7, 80, 16)).top().points().tolist():
    if (x * 7 + z * 13) % 11:
        S.set(x, y, z, "ice")
# snowy pines: tall ones as a backdrop behind both portals and the longhouse, a grove on the rims
for i, (x, z, h) in enumerate([(-24, -1, 16), (24, 1, 15), (-12, -25, 17), (-4, -27, 14), (20, -22, 13)]):
    trees.tree((x, S.top_y(x, z) or 80, z), "pine", height=h, seed=11 + i)
ground = S.surface(where=top, pattern="snow_block|grass_block|podzol|coarse_dirt|stone|moss_block|powder_snow")
trees.forest(ground, kinds=["pine", "pine", "dead"], count=9, min_dist=6, avoid=keep, seed=8)
for i, (x, z) in enumerate([(-22, 12), (21, 12), (8, -27), (-25, -12)]):
    rocks.boulder((x, S.top_y(x, z) or 80, z), size=1.9, seed=20 + i)
# snow over everything that is not paved: layers, some ferns and berry bushes poking out
ground = S.surface(where=top, pattern="snow_block|grass_block|podzol|coarse_dirt|moss_block")
terrain.cover(ground, density=0.55, avoid=keep, seed=9)# a blanket of snow: one layer on every open patch of grass the cover left bare (no green squares)
for x, y, z in S.surface(where=top, pattern="grass_block|podzol|coarse_dirt|moss_block").points().tolist():
    if S.get(x, y + 1, z) == "minecraft:air":
        S.set(x, y + 1, z, "snow[layers=1]")
