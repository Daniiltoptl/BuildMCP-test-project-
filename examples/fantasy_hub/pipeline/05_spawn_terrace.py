import math
# raised round terrace south of the plaza: players appear here and look over the fountain at the tower
cx, cz, R = 0, 20, 6.5
wallmix = P.gradient([T.wall_base, T.wall], axis="y", start=80, end=82)
dark = "polished_deepslate"
for x in range(-8, 9):
    for z in range(12, 29):
        r = math.hypot(x - cx, z - cz)
        if r > R + 0.3:
            continue
        for y in (80, 81):
            S.put((x, y, z), wallmix)
        S.set(x, 82, z, "polished_andesite" if (r > R - 1.2 or r < 1.6) else "stone_bricks")
        S.clear((x, 83, z, x, 86, z))
# ring pattern on the floor and a dark rim course
for x in range(-8, 9):
    for z in range(12, 29):
        r = math.hypot(x - cx, z - cz)
        if abs(r - 3.8) < 0.5:
            S.set(x, 82, z, "polished_deepslate")
        if R - 0.7 < r <= R + 0.3:
            S.set(x, 81, z, "polished_deepslate")
# balustrade (open to the north and the south for the stairs)
for x in range(-8, 9):
    for z in range(12, 29):
        r = math.hypot(x - cx, z - cz)
        if R - 0.9 < r <= R + 0.3 and abs(x) > 2:
            S.set(x, 83, z, "polished_deepslate_wall")
# stairs down to the plaza (north) and to the garden path (south)
for x in range(-2, 3):
    S.set(x, 81, 12, "stone_brick_stairs[facing=south]")
    S.set(x, 80, 12, "stone_bricks")
    S.set(x, 81, 13, "stone_bricks")
    S.set(x, 82, 13, "stone_brick_stairs[facing=south]")
    S.set(x, 82, 27, "stone_brick_stairs[facing=north]")
    S.set(x, 81, 28, "stone_brick_stairs[facing=north]")
    S.set(x, 80, 28, "stone_bricks")
    S.clear((x, 83, 12, x, 85, 13))
# lamps on the balustrade corners
for x, z in ((-4, 15), (4, 15), (-4, 25), (4, 25)):
    S.set(x, 83, z, "polished_deepslate_wall")
    S.set(x, 84, z, "lantern[hanging=false]")
mark("spawn", (0, 83, 19), "spawn", yaw=180, pitch=10)
mark("anchor", (0, 83, 19), "anchor")