import math
# North-east of the temple: a monopteros (round colonnade) under a verdigris copper dome with an
# oculus; an eternal flame burns in the middle and its smoke leaves through the oculus.
Y = 80
def rnd(x, y, z, s):
    return noise.hash01(x, y, z, s)

def face_out(dx, dz):
    return ("east" if dx > 0 else "west") if abs(dx) >= abs(dz) else ("south" if dz > 0 else "north")

# ======================= monopteros with a copper dome
MX, MZ = 18, -18
mcx, mcz = MX + 0.5, MZ + 0.5
for x in range(MX - 8, MX + 9):
    for z in range(MZ - 8, MZ + 9):
        r = math.hypot(x + 0.5 - mcx, z + 0.5 - mcz)
        if r > 6.4:
            continue
        S.clear(Box(x, Y + 1, z, x, Y + 16, z))
        y = Y
        while y > 60 and S.get(x, y, z) in ("minecraft:air", "minecraft:short_grass"):
            S.set(x, y, z, "sandstone")
            y -= 1
        S.set(x, Y, z, "sandstone")
        fo = face_out(mcx - (x + 0.5), mcz - (z + 0.5))    # stairs face the centre (you climb inwards)
        if r > 5.6:
            S.set(x, Y + 1, z, f"smooth_sandstone_stairs[facing={fo},half=bottom]")
        elif r > 4.8:
            S.set(x, Y + 1, z, "cut_sandstone")
            S.set(x, Y + 2, z, f"smooth_sandstone_stairs[facing={fo},half=bottom]")
        else:
            S.set(x, Y + 1, z, "cut_sandstone")
            S.set(x, Y + 2, z, "chiseled_quartz_block" if r < 0.8 else
                  ("smooth_quartz" if int(r) % 2 == 0 else "cut_sandstone"))
# eight columns on a ring
cols = []
for k in range(8):
    a = 2 * math.pi * k / 8 + math.pi / 8
    x = int(math.floor(mcx + 3.9 * math.cos(a)))
    z = int(math.floor(mcz + 3.9 * math.sin(a)))
    cols.append((x, z))
    arch.roman_column((x, Y + 3, z), 6)
# entablature ring, cornice, dome with an oculus, gold finial ring
for x in range(MX - 7, MX + 8):
    for z in range(MZ - 7, MZ + 8):
        r = math.hypot(x + 0.5 - mcx, z + 0.5 - mcz)
        if 2.6 < r <= 5.0:
            S.set(x, Y + 9, z, "smooth_quartz" if r > 4.2 else "smooth_sandstone")
            S.set(x, Y + 10, z, ("chiseled_sandstone" if rnd(x, 0, z, 3) < 0.3 else "cut_sandstone") if r > 4.2
                  else "smooth_sandstone")
        elif 5.0 < r <= 5.8:
            S.set(x, Y + 10, z, "smooth_sandstone_slab[type=top]")
dome = arch.dome_roof((mcx, Y + 11, mcz), 5.0, material="oxidized_cut_copper", base_y=Y + 11, height=4.5)
top = max(y for (x, y, z) in dome.points().tolist())
for (x, y, z) in dome.points().tolist():
    if math.hypot(x + 0.5 - mcx, z + 0.5 - mcz) < 1.0 and y >= top - 1:
        S.set(x, y, z, "air")                       # oculus
ox, oz = MX, MZ
for d, (dx, dz) in {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}.items():
    if S.get(ox + dx, top, oz + dz) != "minecraft:air":
        S.set(ox + dx, top, oz + dz, "gold_block")
# the ceiling under the dome is hollow; hide light in the dome shell
S.clear(Box(MX - 3, Y + 11, MZ - 3, MX + 3, top - 2, MZ + 3), only="oxidized_cut_copper|oxidized_cut_copper_stairs|oxidized_cut_copper_slab")
# eternal flame: a quartz altar with a campfire; the smoke rises through the oculus
S.set(MX, Y + 3, MZ, "chiseled_quartz_block")
S.set(MX, Y + 4, MZ, "hay_block")
S.set(MX, Y + 5, MZ, "campfire[lit=true,signal_fire=true]")
for d, (dx, dz) in {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}.items():
    S.set(MX + dx, Y + 3, MZ + dz, f"quartz_stairs[facing={ {'north': 'south', 'south': 'north', 'west': 'east', 'east': 'west'}[d] },half=bottom]")
    S.set(MX + dx, Y + 4, MZ + dz, f"smooth_quartz_slab[type=bottom]")
print("dome top", top, "columns", cols)