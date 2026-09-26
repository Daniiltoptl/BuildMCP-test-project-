import math
# stone platform for the spawn with a spruce railing, open to the north
x1, x2, z1, z2 = -4, 4, 16, 22
for x in range(x1, x2 + 1):
    for z in range(z1, z2 + 1):
        if (x in (x1, x2)) and (z in (z1, z2)):
            continue
        edge = x in (x1, x2) or z in (z1, z2)
        S.set(x, 81, z, "polished_andesite" if edge else ("chiseled_stone_bricks" if (x, z) == (0, 19) else "stone_bricks"))
        S.clear((x, 82, z, x, 86, z))
        y = 80
        while y > 72 and S.get(x, y, z) == "minecraft:air":  # solid under the platform, down to the rock
            S.set(x, y, z, "cobblestone")
            y -= 1
for x in range(x1, x2 + 1):
    for z in range(z1, z2 + 1):
        on_edge = (x in (x1, x2) or z in (z1, z2)) and not ((x in (x1, x2)) and (z in (z1, z2)))
        if on_edge and not (z == z1 and -2 <= x <= 2):
            S.set(x, 82, z, "spruce_fence")
for x, z in [(x1 + 1, z1), (x2 - 1, z1), (x1, z2 - 1), (x2, z2 - 1)]:
    S.set(x, 82, z, "spruce_log")
    S.set(x, 83, z, "lantern[hanging=false]")
for x in range(-2, 3):
    S.set(x, 81, z1 - 1, "stone_brick_stairs[facing=south,half=bottom]")
    S.clear((x, 82, z1 - 1, x, 84, z1 - 1))

# campfires in stone bowls along the road and at the longhouse porch
for x, z in [(-6, 4), (6, 4), (-8, -4), (8, -4)]:  # at the yard corners, clear of the porch in view
    props.lamp_post((x, S.top_y(x, z) or 80, z), style="brazier")
# mode banners on poles beside each portal
for name, col in {"survival": "light_blue", "hardcore": "white"}.items():
    x, y, z = (int(v) for v in S.markers[name].pos)
    for side in (-1, 1):
        props.banner_pole((x, 80, z + 7 * side), color=col, height=6, facing="east" if x < 0 else "west")
# night: warm light around the tower foot and the yard (the tower windows glow on their own)
for k in range(8):
    a = 2 * math.pi * k / 8
    x, z = round(10 + math.cos(a) * 7), round(-21 + math.sin(a) * 7)
    y = (S.top_y(x, z) or 80) + 1
    if S.get(x, y, z) == "minecraft:air":
        S.set(x, y, z, "light[level=12]")
for x, y, z in [(-4, 82, 1), (4, 82, 1), (-12, 82, -4), (12, 82, -4)]:
    if S.get(x, y, z) == "minecraft:air":
        S.set(x, y, z, "light[level=10]")
finalize()