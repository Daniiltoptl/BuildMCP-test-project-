import math
# Finishing touches: paths that tie the quarters together, a ruined colonnade in the north-west corner,
# a marble exedra bench looking over the edge in the south-east, boulders along the rim; then the
# game-like block updates (fences, walls, stairs, leaves) so the paste looks exactly like the render.
Y = 80
def rnd(x, z, s):
    return noise.hash01(x, 0, z, s)

# ---- paths: forum -> monopteros, pergola -> exedra
paths.path([(9, Y, -4), (11, Y, -8), (14, Y, -12)], width=2.4, seed=3)
paths.path([(14, Y, 9), (15, Y, 12), (15, Y, 14)], width=2.2, seed=4)

# ---- ruined colonnade in the north-west: two columns still carry a piece of the entablature, the
# third is broken, its drums lie in the grass
for i, x in enumerate((-19, -16, -13)):
    g = S.top_y(x, -22, "!#air|!#plants|!#replaceable|!#leaves|!#logs") or Y
    S.clear(Box(x - 1, g + 1, -23, x + 1, g + 3, -21))
    S.set(x, g, -22, "quartz_bricks")
    h = 7 if i < 2 else 3
    if h > 3:
        arch.roman_column((x, g + 1, -22), h)
    else:
        S.set(x, g + 1, -22, "quartz_bricks")
        S.set(x, g + 2, -22, "quartz_pillar[axis=y]")
        S.set(x, g + 3, -22, "quartz_slab[type=bottom]")
top = (S.top_y(-19, -22, "!#air|!#plants|!#replaceable|!#leaves|!#logs") or Y)
for x in range(-20, -14):
    S.set(x, top + 1, -22, "smooth_sandstone" if x not in (-20, -15) else "smooth_sandstone_slab[type=bottom]")
    if -20 < x < -15:
        S.set(x, top + 2, -22, "cut_sandstone" if x % 2 else "chiseled_sandstone")
for (x, z, b) in [(-12, -20, "quartz_pillar[axis=x]"), (-11, -20, "quartz_pillar[axis=x]"),
                  (-13, -19, "chiseled_quartz_block"), (-17, -20, "smooth_sandstone_slab[type=bottom]")]:
    g = S.top_y(x, z, "!#air|!#plants|!#replaceable|!#leaves|!#logs")
    if g is not None and g >= Y - 1:
        S.clear(Box(x, g + 1, z, x, g + 2, z))
        S.set(x, g + 1, z, b)

# ---- exedra: a curved marble bench round a small mosaic, facing the sky over the south-east rim
EX, EZ = 16, 16
ecx, ecz = EX + 0.5, EZ + 0.5
for x in range(EX - 5, EX + 6):
    for z in range(EZ - 5, EZ + 6):
        r = math.hypot(x + 0.5 - ecx, z + 0.5 - ecz)
        a = math.degrees(math.atan2(z + 0.5 - ecz, x + 0.5 - ecx))
        g = S.top_y(x, z, "!#air|!#plants|!#replaceable|!#leaves|!#logs")
        if g is None or r > 4.2:
            continue
        S.clear(Box(x, Y + 1, z, x, Y + 4, z))
        for y in range(g + 1, Y + 1):
            S.set(x, y, z, "sandstone")
        if r <= 2.4:
            S.set(x, Y, z, "chiseled_quartz_block" if r < 0.5 else ("orange_terracotta" if r < 1.5 else "red_terracotta"))
        else:
            S.set(x, Y, z, "smooth_sandstone")
            if 3.1 < r <= 4.2 and (a < -50 or a > 140):     # the bench runs round the north-west half
                dx, dz = ecx - (x + 0.5), ecz - (z + 0.5)
                face = ("east" if dx > 0 else "west") if abs(dx) > abs(dz) else ("south" if dz > 0 else "north")
                opp = {"east": "west", "west": "east", "north": "south", "south": "north"}[face]
                S.set(x, Y + 1, z, f"quartz_stairs[facing={opp},half=bottom]")
S.set(EX, Y + 1, EZ, "sandstone_wall")
S.set(EX, Y + 2, EZ, "lantern")

# ---- sandstone boulders on the rim
for i, (x, z, s) in enumerate([(-26, 4, 2.2), (27, -12, 2.0), (-8, 22, 1.8), (24, 14, 1.6), (-18, -28, 1.8)]):
    g = S.top_y(x, z, "!#air|!#plants|!#replaceable|!#leaves|!#logs")
    if g is not None:
        rocks.boulder((x, g, z), s, palette=P.mix({"sandstone": 3, "smooth_sandstone": 1, "terracotta": 0.6}, seed=i),
                      seed=60 + i)

finalize()
print(lint()[:1500] if isinstance(lint(), str) else "lint done")