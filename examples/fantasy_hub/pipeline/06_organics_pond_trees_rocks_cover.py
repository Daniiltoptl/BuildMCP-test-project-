import math
mark("spawn", (0, 83, 19), "spawn", yaw=180, pitch=-21)  # looks up at the tower and the logo
top = Box(-56, 78, -60, 56, 84, 42)
paved_pat = ("stone_bricks|polished_andesite|andesite|cracked_stone_bricks|mossy_stone_bricks|chiseled_stone_bricks|"
             "polished_deepslate|stone_brick_stairs|cobblestone|mossy_cobblestone")
paved = S.mask(paved_pat, where=Box(-56, 80, -60, 56, 83, 42))
keep_clear = paved.dilate(2, horizontal=True)
# tower + terrace footprints
keep_clear = keep_clear | Mask.box(Box(-11, 78, -43, 11, 84, -21)) | Mask.box(Box(-8, 78, 11, 8, 84, 29))

# a pond in the south-west garden with a waterfall over the island edge
terrain.pond((-24, 80, 22), radius=5.5, depth=3, seed=4, lily=0.1)
terrain.waterfall((-38, 80, 30), direction="west", width=2, drop=34)

# hero trees: a giant oak east of the terrace, a willow at the pond
trees.tree((22, 80, 20), "oak_giant", height=21, seed=7)
trees.tree((-17, 80, 30), "willow", height=13, seed=3)
trees.tree((-33, 80, -24), "oak_giant", height=16, seed=12)
ground = S.surface(where=top, pattern="grass_block|moss_block|podzol|coarse_dirt")
avoid = keep_clear | Mask.box(Box(14, 78, 12, 30, 90, 28)) | Mask.box(Box(-31, 78, 14, -9, 90, 36))
trees.forest(ground, kinds=["oak", "birch", "oak", "bush"], count=16, min_dist=8, avoid=avoid, seed=5)

# rocks along the rim and at the tower foot
for i, (x, z) in enumerate([(40, -6), (-42, 4), (30, -36), (-26, -44), (12, 36), (44, 14), (-40, -18)]):
    y = S.top_y(x, z) or 80
    rocks.rock_cluster((x, y, z), size=3.2, count=4, seed=30 + i)
for i, (x, z) in enumerate([(-10, -26), (10, -27)]):
    rocks.boulder((x, 80, z), size=2.2, seed=40 + i)

# ground cover: grass, ferns and flower patches off the paving
ground = S.surface(where=top, pattern="grass_block|moss_block|podzol|coarse_dirt")
terrain.cover(ground, density=0.42, avoid=keep_clear, seed=9)