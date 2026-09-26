import math
# East side of the forum: a green pergola walk (white columns, dark timber, azalea greenery with glow
# berries) and behind it a formal garden: a long reflecting canal between two rows of cypresses, lit by
# sea pickles at night, spilling over the island edge as a waterfall.
Y = 80
def rnd(x, z, s):
    return noise.hash01(x, 0, z, s)

# ---- pergola walk along the forum
for x in range(10, 19):
    for z in range(-5, 10):
        S.clear(Box(x, Y + 1, z, x, Y + 3, z))
        S.put((x, Y, z), T.path)
arch.pergola((14, Y, -4), (14, Y, 8), width=5, height=5, greenery=0.55, seed=5)
props.bench((16, Y, -1), facing="west", length=2)
props.bench((16, Y, 5), facing="west", length=2)
for z in (-3, 3, 9):          # potted shrubs between the columns
    if S.get(16, Y + 1, z) == "minecraft:air":
        S.set(16, Y + 1, z, "potted_flowering_azalea_bush")

# ---- reflecting canal: x 21..23, z -4..8, flush with the lawn, a low quartz curb
CX1, CX2, CZ1, CZ2 = 21, 23, -4, 8
for x in range(CX1 - 1, CX2 + 2):
    for z in range(CZ1 - 1, CZ2 + 2):
        S.clear(Box(x, Y + 1, z, x, Y + 3, z))
        inside = CX1 <= x <= CX2 and CZ1 <= z <= CZ2
        if inside:
            S.set(x, Y - 2, z, "sandstone")
            S.set(x, Y - 1, z, "prismarine_bricks" if (x + z) % 2 else "dark_prismarine")
            S.set(x, Y, z, "water")
        else:
            S.set(x, Y, z, "smooth_quartz")
            S.set(x, Y + 1, z, "smooth_quartz_slab[type=bottom]")
for (x, z) in ((22, -2), (22, 2), (22, 6)):      # glowing sea pickles on the canal floor
    S.set(x, Y - 1, z, "sand")
    S.set(x, Y, z, "sea_pickle[pickles=4,waterlogged=true]")
# gravel walks around the canal, lawn beyond
for x in range(CX1 - 3, CX2 + 4):
    for z in range(CZ1 - 3, CZ2 + 3):
        if (CX1 - 1 <= x <= CX2 + 1 and CZ1 - 1 <= z <= CZ2 + 1):
            continue
        if S.get(x, Y, z) in ("minecraft:grass_block", "minecraft:coarse_dirt", "minecraft:moss_block",
                              "minecraft:rooted_dirt", "minecraft:dirt"):
            if x in (CX1 - 2, CX2 + 2) or z in (CZ1 - 2, CZ2 + 2):
                S.set(x, Y, z, "sand" if rnd(x, z, 3) < 0.7 else "gravel")
                S.clear(Box(x, Y + 1, z, x, Y + 2, z))
# a small nymphaeum at the north end: a quartz basin with a lion-less spout wall
for x in range(CX1 - 1, CX2 + 2):
    S.set(x, Y + 1, CZ1 - 2, "quartz_bricks")
    S.set(x, Y + 2, CZ1 - 2, "quartz_bricks")
    S.set(x, Y + 3, CZ1 - 2, "smooth_quartz_slab[type=bottom]" if x != 22 else "chiseled_quartz_block")
S.set(22, Y + 4, CZ1 - 2, "smooth_quartz_slab[type=bottom]")
# the spout: a source on the curb under a quartz lip pours over into the canal (a stable state: the
# flow above the canal water does not spread any further)
S.set(22, Y + 2, CZ1 - 1, "quartz_stairs[facing=north,half=top]")
S.set(22, Y + 1, CZ1 - 1, "water")
S.set(22, Y + 1, CZ1, "water[level=1]")

# ---- the canal spills east through a stone channel that runs out over the rim and pours off the edge
edge_x = None
for x in range(CX2 + 1, 36):
    g = S.top_y(x, 6, "!#air|!#plants|!#replaceable|!#liquid")
    if g is None or g < Y - 8:
        edge_x = x
        break
    for zz in range(5, 9):
        S.clear(Box(x, Y + 1, zz, x, Y + 3, zz))
        for y in range(g + 1, Y):
            S.set(x, y, zz, "sandstone")
        S.set(x, Y - 1, zz, "smooth_sandstone")
        if zz in (6, 7):
            S.set(x, Y, zz, "water")
        else:
            S.set(x, Y, zz, "smooth_sandstone")
            S.set(x, Y + 1, zz, "smooth_sandstone_slab[type=bottom]")
print("channel ends at x", edge_x)
if edge_x is not None:
    for zz in (5, 8):                       # the spout: a lip of stairs at the end of the channel walls
        S.set(edge_x - 1, Y + 1, zz, "smooth_sandstone_stairs[facing=west,half=bottom]")
    terrain.waterfall((edge_x - 1, Y, 6), direction="east", width=2, drop=40)

# ---- cypress avenue along the canal, low boxwood hedges at their feet
cyp = []
for i, z in enumerate(range(CZ1 - 1, CZ2 + 2, 4)):
    for x in (CX1 - 3, CX2 + 3):
        r = trees.tree((x, Y, z), "cypress", height=11 + 3 * rnd(x, z, 5), seed=31 + i * 7 + x)
        cyp.append((x, z))
print(len(cyp), "cypresses")