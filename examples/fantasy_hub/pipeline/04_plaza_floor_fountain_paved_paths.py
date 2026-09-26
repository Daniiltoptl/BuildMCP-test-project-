import math
paved = P.patches({"stone_bricks": 6, "polished_andesite": 2, "cracked_stone_bricks": 1, "mossy_stone_bricks": 1.5,
                   "andesite": 1}, size=4, seed=5)
edge = P.patches({"moss_block": 3, "coarse_dirt": 2, "mossy_cobblestone": 1}, size=3, seed=6)

# paved main axis (spawn -> plaza -> tower door) and paths to the portals
paths.path([(0, 80, 10), (0, 80, 24), (-3, 80, 36)], width=5, palette=paved, edge=edge, seed=21)
paths.path([(0, 80, -10), (0, 80, -25)], width=5, palette=paved, edge=edge, seed=22)
for name in ("survival", "skyblock", "pvp", "anarchy"):
    x, y, z = (int(v) for v in S.markers[name].pos)
    ang = math.atan2(z, x)
    start = (round(10 * math.cos(ang)), 80, round(10 * math.sin(ang)))
    mid = (x * 0.62, 80, z * 0.62 + 1)
    paths.path([start, mid, (x, 80, z)], width=4, palette=paved, edge=edge, seed=len(name) + 7)

# plaza floor (painted after the paths so their soft edges do not spill onto it)
field = P.patches({"stone_bricks": 7, "cracked_stone_bricks": 1, "mossy_stone_bricks": 1.2, "polished_andesite": 0.6},
                  size=5, seed=7)
for x in range(-13, 14):
    for z in range(-13, 14):
        r = math.hypot(x, z)
        if r > 12.6:
            continue
        a = (math.degrees(math.atan2(z, x)) + 360) % 360
        if r < 5.6:
            b = "polished_andesite"
        elif r < 10.2:
            b = "polished_andesite" if (a % 30) < 3.5 or abs(r - 7.9) < 0.5 else None
        elif r < 11.3:
            b = "polished_andesite"
        else:
            b = "stone_bricks"
        if b is None:
            S.put((x, 80, z), field)
        else:
            S.set(x, 80, z, b)
S.clear((-13, 81, -13, 13, 84, 13), only="#plants")
# portal pads: paved disc with a polished ring
for name in ("survival", "skyblock", "pvp", "anarchy"):
    x, y, z = (int(v) for v in S.markers[name].pos)
    for dx in range(-6, 7):
        for dz in range(-6, 7):
            r = math.hypot(dx, dz)
            if r <= 6.2:
                S.put((x + dx, 80, z + dz), "polished_andesite" if 5.2 < r else paved)
    S.clear((x - 6, 81, z - 6, x + 6, 83, z + 6), only="#plants")
# the plaza centerpiece: fountain with an amethyst crystal
# white marble against the grey tower behind it, so the two do not merge from the spawn
props.fountain((0, 80, 0), radius=4.5, tiers=2, centerpiece="crystal", material="smooth_quartz")