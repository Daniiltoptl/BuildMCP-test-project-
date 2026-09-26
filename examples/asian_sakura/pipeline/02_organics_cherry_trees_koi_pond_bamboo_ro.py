import math
top = Box(-32, 76, -32, 32, 84, 28)
paved = S.mask("gravel|andesite|tuff|moss_block|polished_andesite|stone_bricks|smooth_stone|#stairs|#slabs",
               where=Box(-32, 80, -32, 32, 81, 28))
keep = paved.dilate(1, horizontal=True) | Mask.box(Box(-8, 78, -24, 8, 115, -8)) | Mask.box(Box(-5, 78, 9, 5, 92, 13))
# sight lines from the spawn to both portals stay open
sx, sy, sz = S.markers["spawn"].pos
for name in ("survival", "minigames"):
    x, y, z = (int(v) for v in S.markers[name].pos)
    keep = keep | Mask.box(Box(x - 4, 78, z - 4, x + 4, 92, z + 4))
    for t in np.linspace(0, 1, 24):
        px, pz = round(sx + (x - sx) * t), round(sz + (z - sz) * t)
        keep = keep | Mask.box(Box(px - 5, 78, pz - 5, px + 5, 92, pz + 5))
keep = keep | Mask.box(Box(-8, 78, 12, 8, 92, 26))  # the deck and its surroundings
keep = keep | Mask.box(Box(-9, 78, -3, 9, 92, 26))  # the whole alley stays open (crowns too)

# koi pond west of the alley
terrain.pond((-12, 80, 10), radius=4.5, depth=3, seed=6, lily=0.12)
# hero cherries: a pink backdrop behind both portals, two behind the pagoda, one past the pond
# (the torii frames the spawn view; crowns near the deck would cover it)
for i, (x, z, h) in enumerate([(-23, -2, 11), (23, -2, 11), (-13, -20, 12), (13, -21, 13), (-22, 12, 9)]):
    trees.tree((x, S.top_y(x, z) or 80, z), "cherry", height=h, seed=11 + i)
ground = S.surface(where=top, pattern="grass_block|moss_block|podzol")
trees.forest(ground, kinds=["cherry", "cherry", "bush"], count=9, min_dist=7, avoid=keep, seed=8)

# bamboo groves on the north rim behind the pagoda (grown columns: small leaves low, large at the top)
for i, (bx, bz) in enumerate([(-20, -14), (-22, -9), (19, -14), (22, -10), (-6, -25), (7, -25)]):
    for dx, dz in [(0, 0), (1, 0), (0, 1), (-1, 1), (1, 2)]:
        x, z = bx + dx, bz + dz
        y0 = S.top_y(x, z)
        if y0 is None or S.get(x, y0, z).split("[")[0] not in ("minecraft:grass_block", "minecraft:moss_block"):
            continue
        h = 6 + (i * 3 + dx * 2 + dz) % 5
        for k in range(1, h + 1):
            leaves = "large" if k > h - 2 else "small" if k > h - 4 else "none"
            S.set(x, y0 + k, z, f"bamboo[age=1,leaves={leaves},stage=0]")

# mossy boulders and a zen corner: raked gravel with three stones east of the alley
for i, (x, z) in enumerate([(-24, -2), (23, 6), (-4, -27), (18, -22)]):
    rocks.boulder((x, S.top_y(x, z) or 80, z), size=1.8, seed=20 + i)
for x in range(9, 16):
    for z in range(6, 12):
        if math.hypot(x - 12, z - 9) < 3.3:
            S.set(x, 80, z, "gravel")
            S.clear((x, 81, z, x, 83, z), only="#plants")
for i, (x, z, s) in enumerate([(11, 8, 1.2), (13, 10, 0.9), (13, 7, 0.7)]):
    rocks.boulder((x, 80, z), size=s, seed=30 + i)

# ground cover: grass, ferns, pink petals and flowers off the paths
ground = S.surface(where=top, pattern="grass_block|moss_block|podzol")
terrain.cover(ground, density=0.45, avoid=keep, seed=9)