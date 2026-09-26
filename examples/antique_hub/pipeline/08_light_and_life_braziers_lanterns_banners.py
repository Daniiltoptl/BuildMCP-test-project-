import math
# Warm light and life: braziers with rising smoke on the temple pedestals and at the top of the spawn
# stair, lanterns in the portico and around the fountain, red and gold standards on the temple, lights
# hidden in the arches of the colosseum, lanterns on the terrace balustrade, and the NPC hologram.
Y = 80

def brazier(x, y, z):
    """A bronze fire bowl (a cauldron with a campfire in it) on a slim post standing on (x, y - 1, z)."""
    S.set(x, y, z, "sandstone_wall")
    S.set(x, y + 1, z, "cauldron")
    S.set(x, y + 2, z, "campfire[lit=true]")

# temple stair pedestals (tops at y 85); lanterns on the posts at the head of the spawn stair
for x in (-6, 6):
    brazier(x, 86, -6)
for x in (-5, 5):
    S.set(x, Y + 5, 12, "lantern")

# lanterns on chains in the portico, either side of the NPC
for x in (-3, 3):
    S.set(x, 91, -12, "chain[axis=y]")
    S.set(x, 90, -12, "chain[axis=y]")
    S.set(x, 89, -12, "lantern[hanging=true]")

# red and gold standards hanging from the portico architrave
for x in (-4, 4):
    E.banner((x, 92, -7), "red", [("rhombus", "yellow"), ("circle", "red"), ("border", "yellow"),
                                   ("triangles_bottom", "yellow")], facing="south")

# four lamps on the corners of the fountain square
for x in (-5, 5):
    for z in (-2, 8):
        S.set(x, Y + 1, z, "sandstone_wall")
        S.set(x, Y + 2, z, "sandstone_wall")
        S.set(x, Y + 3, z, "lantern")

# lanterns on the posts of the terrace balustrade (round end)
for x in range(-8, 9):
    for z in range(17, 25):
        if S.get(x, Y + 3, z) == "minecraft:cut_sandstone" and S.get(x, Y + 4, z) == "minecraft:smooth_sandstone":
            S.set(x, Y + 5, z, "lantern")

# market stalls: a lantern under each awning
for z in (-11, -3, 5):
    S.set(-13, Y + 3, z, "lantern[hanging=true]")

# hidden lights in the ground arches of the colosseum (they glow at night)
CX, CZ, RO = -43.0, -4.0, 24.0
for x in range(-30, -14):
    for z in range(-22, 14):
        r = math.hypot(x + 0.5 - CX, z + 0.5 - CZ)
        if RO - 1.0 < r <= RO and S.get(x, Y + 3, z) == "minecraft:air" and S.get(x, Y + 4, z) == "minecraft:air" \
                and S.get(x, Y + 5, z) != "minecraft:air" and (x + z) % 3 == 0:
            S.set(x, Y + 3, z, "light[level=11]")

# soft light over the forum and the lawns at night (invisible light blocks)
for (x, z) in ((0, -3), (0, 9), (-7, 3), (7, 3), (-14, 3), (14, 3), (0, -22), (-16, -12), (16, -6), (20, 10)):
    y = (S.top_y(x, z, "!#air|!#plants|!#replaceable|!#leaves|!#logs") or Y) + 3
    if S.get(x, y, z) == "minecraft:air":
        S.set(x, y, z, "light[level=9]")

# a gilded inscription on the architrave, like the dedication on a Roman temple
insc = E.hologram((0.5, 92.08, -6.96), [E.component("ANARCHIA", color="gold", bold=True)], billboard="fixed",
                  scale=2.4, background=0, shadow=True)

# the NPC hologram, above the NPC's own name tag
E.hologram((0.5, 87.35, -14.5), [E.component("АНАРХИЯ", color="gold", bold=True),
                                  E.component("Нажми ПКМ, чтобы играть", color="gray")], scale=1.1)
print("ok")