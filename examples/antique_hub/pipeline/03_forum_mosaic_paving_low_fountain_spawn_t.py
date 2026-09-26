import math
# Forum between the spawn terrace and the temple: a low brimming fountain in the middle (its top stays
# under the line of sight from the spawn to the temple steps and the NPC), a mosaic carpet around it,
# a grand stair up to the spawn terrace, which has a sunburst mosaic in its floor and a balustrade.
Y = 80
FC = (0, 3)                        # fountain centre cell
FX, FZ1, FZ2 = 9, -4, 10           # forum paving: |x| <= 9, z -4..10
ROT = [["north", "east"], ["west", "south"]]

def glazed(kind, x, z):            # 2x2 rotated glazed tiles form one motif
    return f"{kind}[facing={ROT[x % 2][z % 2]}]"

def cheb(x, z):
    return max(abs(x - FC[0]), abs(z - FC[1]))

def rad(x, z):
    return math.hypot(x - FC[0], z - FC[1])

def flag(x, z, s):                 # stable per-cell noise
    return noise.hash01(x, 0, z, s)

def slabs(x, z):
    """Flagstones: cut sandstone with chiseled blocks where the 4-block joints cross."""
    if x % 4 == 0 and z % 4 == 0:
        return "chiseled_sandstone"
    if x % 4 == 0 or z % 4 == 0:
        return "smooth_sandstone"
    return "sandstone" if flag(x, z, 11) < 0.15 else "cut_sandstone"

# ---- forum paving
for x in range(-FX, FX + 1):
    for z in range(FZ1, FZ2 + 1):
        S.clear(Box(x, Y + 1, z, x, Y + 4, z))
        d, r = cheb(x, z), rad(x, z)
        if r <= 4.9:
            block = "smooth_sandstone"      # under the fountain
        elif d <= 4:
            block = "orange_terracotta"     # spandrels between the round fountain and the square
        elif d == 5:
            block = "red_terracotta"
        elif d == 6:
            block = glazed("orange_glazed_terracotta", x, z)
        elif d == 7:
            block = "red_terracotta"
        else:
            block = slabs(x, z)
        S.set(x, Y, z, block)
        for y in (Y - 1, Y - 2):
            if S.get(x, y, z) == "minecraft:air":
                S.set(x, y, z, "sandstone")
# a seam of chiseled blocks where the forum meets the temple steps
for x in range(-FX, FX + 1):
    if S.get(x, Y + 1, -5) == "minecraft:air":
        S.set(x, Y, -5, "cut_sandstone" if abs(x) % 2 else "chiseled_sandstone")

# ---- the fountain: a brimming pool, quartz rim with a step all around, a low bowl with four spouts
cx, cz = FC
for x in range(cx - 5, cx + 6):
    for z in range(cz - 5, cz + 6):
        r = rad(x, z)
        if r <= 3.2:
            S.set(x, Y - 1, z, "sandstone")
            S.set(x, Y, z, "sea_lantern" if 1.6 < r < 2.6 and (x + z) % 2 == 0 else
                  glazed("light_blue_glazed_terracotta", x, z))
            S.set(x, Y + 1, z, "water")
        elif r <= 4.2:
            S.set(x, Y, z, "quartz_bricks")
            S.set(x, Y + 1, z, "chiseled_quartz_block" if (x == cx or z == cz) else "smooth_quartz")
        elif r <= 4.9:
            dx, dz = cx - x, cz - z
            face = ("east" if dx > 0 else "west") if abs(dx) > abs(dz) else ("south" if dz > 0 else "north")
            S.set(x, Y + 1, z, f"quartz_stairs[facing={face},half=bottom]")
# bowl on a short pedestal: water on top reaches y 82.9, under the sight line to the temple steps
S.set(cx, Y, cz, "chiseled_quartz_block")
S.set(cx, Y + 1, cz, "chiseled_quartz_block")
for d, (dx, dz) in {"west": (1, 0), "east": (-1, 0), "north": (0, 1), "south": (0, -1)}.items():
    S.set(cx + dx, Y + 1, cz + dz, f"quartz_stairs[facing={d},half=top,waterlogged=true]")
    S.set(cx + dx, Y + 2, cz + dz, "water[level=1]")
    S.set(cx + 2 * dx, Y + 2, cz + 2 * dz, "water[level=2]")   # spills over the lip into the pool
for dx in (-1, 1):
    for dz in (-1, 1):
        S.set(cx + dx, Y + 1, cz + dz, "quartz_slab[type=top,waterlogged=true]")
S.set(cx, Y + 2, cz, "water")

# ---- grand stair up to the spawn terrace (floor y 82)
for x in range(-4, 5):
    S.set(x, Y + 1, 11, "smooth_sandstone_stairs[facing=south,half=bottom]")
    S.set(x, Y + 1, 12, "smooth_sandstone")
    S.set(x, Y + 2, 12, "smooth_sandstone_stairs[facing=south,half=bottom]")

# ---- spawn terrace: a rectangle with a round south end, standing on a sandstone plinth
TC = (0, 16)                       # rosette centre = spawn cell
def on_terrace(x, z):
    if -7 <= x <= 7 and 12 <= z <= 16:
        return not (-4 <= x <= 4 and z == 12)
    return z > 16 and math.hypot(x - TC[0], z - TC[1]) <= 7.5

cells = [(x, z) for x in range(-8, 9) for z in range(12, 25) if on_terrace(x, z)]
cellset = set(cells)
def edge(x, z):
    return any((x + dx, z + dz) not in cellset and not (-4 <= x + dx <= 4 and z + dz == 12)
               for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))

def rosette(x, z):
    """Compass star: four long orange arms, four short golden diagonals on a marble disc, a red ring."""
    dx, dz = x - TC[0], z - TC[1]
    r = math.hypot(dx, dz)
    if r < 0.5:
        return "chiseled_quartz_block"
    ax, az = abs(dx), abs(dz)
    along, perp = max(ax, az), min(ax, az)
    if r < 5.0 and perp <= max(0.0, 1.3 * (1 - along / 5.2)):
        return "orange_terracotta"
    if r < 4.6 and ax == az:
        return "yellow_terracotta"
    if r < 1.6:
        return "yellow_terracotta"
    if r < 5.0:
        return "calcite"
    if r < 5.9:
        return "red_terracotta"
    return slabs(x, z)

for (x, z) in cells:
    S.clear(Box(x, Y + 3, z, x, Y + 6, z))
    S.set(x, Y + 2, z, rosette(x, z) if not edge(x, z) else "cut_sandstone")
    # fill down to the ground; past the island edge the terrace is a cantilevered slab, not a pillar
    g = next((y for y in range(Y + 1, Y - 12, -1)
              if S.get(x, y, z) not in ("minecraft:air", "minecraft:short_grass", "minecraft:tall_grass")), None)
    bottom = g + 1 if g is not None and g >= Y - 8 else Y
    for y in range(bottom, Y + 2):
        S.put((x, y, z), P.gradient(["sandstone", "cut_sandstone", "smooth_sandstone"], axis="y",
                                    start=Y - 3, end=Y + 2, jitter=0.6) if y >= Y - 3 else "sandstone")
# plinth cornice around the outside of the terrace (upside-down stairs under the floor edge)
for (x, z) in cells:
    for d, (dx, dz) in {"west": (1, 0), "east": (-1, 0), "north": (0, 1), "south": (0, -1)}.items():
        n = (x + dx, z + dz)
        if n not in cellset and not (-4 <= n[0] <= 4 and n[1] in (11, 12)) and \
                S.get(n[0], Y + 2, n[1]) == "minecraft:air":
            S.set(n[0], Y + 2, n[1], f"smooth_sandstone_stairs[facing={d},half=top]")
# balustrade: posts at the corners and every ~30 degrees on the round end, sandstone walls between,
# a slab rail on top
posts = set()
for (x, z) in cells:
    if not edge(x, z):
        continue
    if (x in (-7, 7) and z in (12, 16)) or (abs(x) == 5 and z == 12):
        posts.add((x, z))
    elif z > 16:
        a = math.degrees(math.atan2(z - TC[1], x - TC[0]))
        if min(abs(a - k) for k in (30, 60, 90, 120, 150)) < 7:
            posts.add((x, z))
for (x, z) in cells:
    if not edge(x, z):
        continue
    S.set(x, Y + 3, z, "cut_sandstone" if (x, z) in posts else "sandstone_wall")
    S.set(x, Y + 4, z, "smooth_sandstone" if (x, z) in posts else "smooth_sandstone_slab[type=bottom]")
print(len(cells), "terrace cells;", len(posts), "posts")