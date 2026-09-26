import math
# raised blackstone platform for the spawn with a wall railing, open to the north
x1, x2, z1, z2 = -4, 4, 16, 22
for x in range(x1, x2 + 1):
    for z in range(z1, z2 + 1):
        if (x in (x1, x2)) and (z in (z1, z2)):
            continue
        edge = x in (x1, x2) or z in (z1, z2)
        S.set(x, 81, z, "polished_blackstone" if edge else ("gilded_blackstone" if (x, z) == (0, 19) else
                                                             "polished_blackstone_bricks"))
        S.clear((x, 82, z, x, 86, z))
        y = 80
        while y > 72 and S.get(x, y, z) == "minecraft:air":  # solid under the platform, down to the rock
            S.set(x, y, z, "blackstone")
            y -= 1
for x in range(x1, x2 + 1):
    for z in range(z1, z2 + 1):
        on_edge = (x in (x1, x2) or z in (z1, z2)) and not ((x in (x1, x2)) and (z in (z1, z2)))
        if on_edge and not (z == z1 and -2 <= x <= 2):
            S.set(x, 82, z, "polished_blackstone_wall")
for x, z in [(x1 + 1, z1), (x2 - 1, z1), (x1, z2 - 1), (x2, z2 - 1)]:
    S.set(x, 83, z, "soul_lantern[hanging=false]")
for x in range(-2, 3):
    S.set(x, 81, z1 - 1, "polished_blackstone_brick_stairs[facing=south,half=bottom]")
    S.clear((x, 82, z1 - 1, x, 84, z1 - 1))

# braziers along the way and at the citadel door
for x, z in [(-3, 6), (3, 6), (-4, -8), (4, -8)]:
    props.lamp_post((x, S.top_y(x, z) or 80, z), style="brazier")
# mode banners on poles beside each portal
for name, col in {"pvp": "red", "anarchy": "purple"}.items():
    x, y, z = (int(v) for v in S.markers[name].pos)
    for side in (-1, 1):
        props.banner_pole((x, 80, z + 7 * side), color=col, height=6, facing="east" if x < 0 else "west")
# night: wash the citadel with light from hidden sources around its foot and under the balcony
for k in range(8):
    a = 2 * math.pi * k / 8
    x, z = round(math.cos(a) * 9.5), round(-15 + math.sin(a) * 9.5)
    y = (S.top_y(x, z) or 80) + 1
    if S.get(x, y, z) == "minecraft:air":
        S.set(x, y, z, "light[level=13]")
for k in range(6):
    a = 2 * math.pi * k / 6 + 0.3
    x, z = round(math.cos(a) * 8.5), round(-15 + math.sin(a) * 8.5)
    if S.get(x, 93, z) == "minecraft:air":
        S.set(x, 93, z, "light[level=12]")
# invisible light on the forecourt and at the portals
for x, y, z in [(-5, 82, -2), (5, 82, -2), (-12, 82, -6), (12, 82, -6)]:
    if S.get(x, y, z) == "minecraft:air":
        S.set(x, y, z, "light[level=10]")
finalize()