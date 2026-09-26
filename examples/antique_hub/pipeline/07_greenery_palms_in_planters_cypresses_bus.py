import math
# Greenery: palms in raised planters at the corners of the forum and around the island, dark cypress
# pairs behind the temple and around the monopteros, azalea bushes at the feet of the ruins, grass and
# Mediterranean flowers on the lawns.
Y = 80
def rnd(x, z, s):
    return noise.hash01(x, 0, z, s)

def planter(x, z):
    """Raised square planter (smooth sandstone rim, soil inside); returns the soil cell."""
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            S.clear(Box(x + dx, Y + 1, z + dz, x + dx, Y + 3, z + dz))
            S.set(x + dx, Y + 1, z + dz, "rooted_dirt" if (dx, dz) == (0, 0) else
                  ("chiseled_sandstone" if dx and dz else "smooth_sandstone"))
    return (x, Y + 1, z)

palms = []
def palm(x, z, h, seed, in_planter=False):
    if in_planter:
        at = planter(x, z)
    else:
        g = S.top_y(x, z, "!#air|!#plants|!#replaceable|!#leaves|!#logs")
        if g is None:
            return
        at = (x, g, z)
    trees.tree(at, "palm", height=h, seed=seed)
    palms.append((x, z))

# forum corners (planters on the outer paving strips) and the sides of the spawn terrace
palm(-9, 9, 11, 3, True)
palm(9, 9, 12, 4, True)
palm(-9, -2, 10, 5, True)
palm(9, -2, 9.5, 6, True)
palm(-10, 21, 9, 9)
palm(12, 20, 10, 10)
# market and garden
palm(-18, 11, 11, 11)
palm(-21, -20, 12, 12)
palm(27, 1, 10, 13)
palm(25, -8, 9, 15)
print(len(palms), "palms")

# cypress pairs: behind the temple, around the monopteros, the north-west corner
cyp = [(-11, -25, 13), (11, -26, 14), (-22, -24, 10), (12, -10, 11), (24, -12, 12), (23, -24, 13),
       (13, -25, 10), (-16, -26, 11), (-10, -12, 12)]
for i, (x, z, h) in enumerate(cyp):
    g = S.top_y(x, z, "!#air|!#plants|!#replaceable|!#leaves|!#logs")
    if g is not None and g >= Y - 3 and S.get(x, g + 1, z) == "minecraft:air":
        trees.tree((x, g, z), "cypress", height=h, seed=50 + i)

# azalea bushes at the feet of walls and along the lawns
bushes = [(-19, -16), (-22, -12), (-24, -2), (-22, 8), (-16, 13), (8, 13), (-8, 13), (14, -8),
          (26, -3), (22, 11), (10, -24), (-9, -26), (5, -28), (-5, -28), (16, 10), (-14, 16), (14, 17)]
for i, (x, z) in enumerate(bushes):
    g = S.top_y(x, z, "!#air|!#plants|!#replaceable|!#leaves|!#logs")
    if g is not None and g >= Y - 3 and S.get(x, g, z) in ("minecraft:grass_block", "minecraft:moss_block",
                                                           "minecraft:coarse_dirt", "minecraft:rooted_dirt",
                                                           "minecraft:dirt"):
        trees.tree((x, g, z), "bush", seed=80 + i)

# lawn cover: grass tufts and flowers, kept off paths
lawn = S.mask("grass_block|moss_block").top()
n = terrain.cover(lawn, density=0.42, seed=21,
                  items={"short_grass": 10, "tall_grass": 2, "fern": 1, "allium": 0.7, "poppy": 0.6,
                         "oxeye_daisy": 0.7, "cornflower": 0.6, "azure_bluet": 0.5, "rose_bush": 0.35,
                         "lilac": 0.3, "peony": 0.25})
print(n, "plants")