import math
# wooden deck for the spawn over the south rim, on dark oak posts, with a railing and lanterns
x1, x2, z1, z2 = -4, 4, 16, 22
for x in range(x1, x2 + 1):
    for z in range(z1, z2 + 1):
        if (x in (x1, x2)) and (z in (z1, z2)):
            continue  # rounded corners
        edge = x in (x1, x2) or z in (z1, z2)
        S.set(x, 81, z, "stripped_dark_oak_wood" if edge else "dark_oak_planks")
        S.clear((x, 82, z, x, 86, z))
# posts from under the deck down to the ground where it reaches over the rim (open underneath)
for x in (x1 + 1, 0, x2 - 1):
    for z in (z1, z2 - 2, z2):
        y = 80
        while y > 72 and S.get(x, y, z) == "minecraft:air":
            S.set(x, y, z, "dark_oak_log")
            y -= 1
# railing on the deck edge, open to the north where the path comes in
for x in range(x1, x2 + 1):
    for z in range(z1, z2 + 1):
        on_edge = (x in (x1, x2) or z in (z1, z2)) and not ((x in (x1, x2)) and (z in (z1, z2)))
        if on_edge and not (z == z1 and -2 <= x <= 2):
            S.set(x, 82, z, "dark_oak_fence")
for x, z in [(x1 + 1, z1), (x2 - 1, z1), (x1, z2 - 1), (x2, z2 - 1)]:
    S.set(x, 83, z, "lantern[hanging=false]")
# step down from the deck to the path
for x in range(-2, 3):
    S.set(x, 81, z1 - 1, "dark_oak_stairs[facing=south,half=bottom]")
    S.clear((x, 82, z1 - 1, x, 84, z1 - 1))

# stone lanterns (toro) past the torii, leading to the courtyard, and at its far corners
for x, z in [(-4, 5), (4, 5), (-8, -11), (8, -11)]:
    props.lamp_post((x, S.top_y(x, z) or 80, z), style="stone_lantern")
# a bench by the pond facing the water
props.bench((-6, 80, 12), facing="west", length=3)

# night: soft invisible light at the pagoda door, under the torii, at the portals
for x, y, z in [(0, 82, -9), (0, 82, 11), (-3, 82, 1), (3, 82, 1), (-12, 82, -6), (12, 82, -6)]:
    if S.get(x, y, z) == "minecraft:air":
        S.set(x, y, z, "light[level=11]")
finalize()