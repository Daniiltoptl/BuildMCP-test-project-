import math
# West side of the forum: a fragment of a colosseum's outer ring. Its arcaded face looks at the forum:
# two tiers of see-through arches with engaged white columns, an attic with masts and red velarium
# sails, a broken south end. Shops sit in some of the ground arches, and a market street runs along its
# foot under red awning sails stretched from the first cornice to slim masts.
Y = 80
CX, CZ = -43.0, -4.0            # centre of the (imaginary) arena, off the island to the west
RO = 24.0                       # radius of the outer face; the wall is two blocks thick
TH0, TH1 = math.radians(-36), math.radians(35)
T1B, T2B, ATT, TOP = 81, 87, 93, 96     # tier bases, attic base, top course
BAY = 4.0


def rnd(x, y, z, s):
    return noise.hash01(x, y, z, s)


def polar(x, z):
    dx, dz = x + 0.5 - CX, z + 0.5 - CZ
    return math.hypot(dx, dz), math.atan2(dz, dx)


def at(r, th):
    return int(math.floor(CX + r * math.cos(th))), int(math.floor(CZ + r * math.sin(th)))


def ruin_top(u, x, z):
    """Full height in the middle; the north end is chipped, the south end falls to the first tier."""
    if u < 0.12:
        t = TOP - 4 + (u / 0.12) * 4
    elif u > 0.66:
        t = TOP - (u - 0.66) / 0.34 * 11
    else:
        return TOP
    return int(t - 2.2 * rnd(x, 0, z, 17))


def found(x, z):
    """Foundation from the terrain up to the paving level."""
    y = Y
    while y > 62 and S.get(x, y, z) in ("minecraft:air", "minecraft:short_grass", "minecraft:tall_grass"):
        S.set(x, y, z, "sandstone")
        y -= 1


# ---- clear the ground west of the forum
for x in range(-28, -9):
    for z in range(-22, 14):
        S.clear(Box(x, Y + 1, z, x, Y + 20, z))

# ---- the wall
ring = {}
for x in range(-30, -14):
    for z in range(-22, 14):
        r, th = polar(x, z)
        if RO - 2.0 < r <= RO and TH0 <= th <= TH1:
            ring[(x, z)] = th
for (x, z), th in ring.items():
    u = (th - TH0) / (TH1 - TH0)
    s = RO * (th - TH0)
    m = s % BAY
    pier = m < 1.25
    top = ruin_top(u, x, z)
    found(x, z)
    S.set(x, Y, z, "smooth_sandstone")
    for y in range(Y + 1, top + 1):
        blk = "cut_sandstone" if rnd(x, y, z, 5) < 0.5 else ("sandstone" if rnd(x, y, z, 6) < 0.65 else "smooth_sandstone")
        for base in (T1B, T2B):
            k = y - base
            if 0 <= k <= 2 and not pier:
                blk = "air"                    # the opening: three wide, three high ...
            elif k == 3 and not pier:          # ... under a round head: haunches and an open crown
                if m < 2.25:
                    blk = "smooth_sandstone_stairs[facing=north,half=top]"
                elif m >= 3.25:
                    blk = "smooth_sandstone_stairs[facing=south,half=top]"
                else:
                    blk = "air"
            elif k == 4 and 2.25 <= m < 3.25:
                blk = "chiseled_sandstone"     # keystone
            elif k == 5:
                blk = "smooth_sandstone"       # the band between the tiers
        if y >= ATT:
            blk = "cut_sandstone" if rnd(x, y, z, 7) < 0.5 else "sandstone"
            if y == ATT + 1 and 5.2 <= s % (2 * BAY) < 6.4:
                blk = "air"                    # small square windows in the attic, every other bay
            if y == TOP:
                blk = "smooth_sandstone"
        S.set(x, y, z, blk)
    if top < TOP and rnd(x, 1, z, 9) < 0.5 and S.get(x, top, z) != "minecraft:air":
        S.set(x, top + 1, z, "sandstone_slab[type=bottom]")     # crumbled edge

# ---- engaged columns at the piers, ledges along the bands and the top
piers = []
k = 0
while True:
    th = TH0 + (0.62 + BAY * k) / RO
    if th > TH1:
        break
    piers.append(th)
    k += 1
for th in piers:
    u = (th - TH0) / (TH1 - TH0)
    px, pz = at(RO + 0.5, th)
    wx, wz = at(RO - 0.5, th)
    top = ruin_top(u, wx, wz)
    if (px, pz) in ring:
        continue
    found(px, pz)
    S.set(px, Y, pz, "smooth_sandstone")
    for base in (T1B, T2B):
        if top < base + 4:
            continue
        for kk in range(5):
            S.set(px, base + kk, pz, "quartz_bricks" if kk == 0 else "chiseled_quartz_block" if kk == 4
                  else "quartz_pillar[axis=y]")
for x in range(-30, -12):
    for z in range(-22, 14):
        if (x, z) in ring:
            continue
        r, th = polar(x, z)
        if RO < r <= RO + 1.0 and TH0 <= th <= TH1:
            u = (th - TH0) / (TH1 - TH0)
            top = ruin_top(u, x, z)
            for yb in (T1B + 5, T2B + 5, TOP):
                if yb <= top + 1 and S.get(x, yb, z) == "minecraft:air":
                    S.set(x, yb, z, "smooth_sandstone_slab[type=top]")

# ---- velarium: masts on the attic, red sails reaching in over the arena
tops = []
for th in piers:
    u = (th - TH0) / (TH1 - TH0)
    if not 0.12 < u < 0.66:
        continue
    mx, mz = at(RO - 0.5, th)
    for y in range(TOP + 1, TOP + 6):
        S.set(mx, y, mz, "dark_oak_fence")
    tops.append((mx + 0.5, TOP + 5.6, mz + 0.5, th))
for (ax, ay, az, ta), (bx, by, bz, tb) in zip(tops, tops[1:]):
    ri = RO - 8.0
    props.sail([(ax, ay, az), (bx, by, bz),
                (CX + ri * math.cos(tb), TOP + 2.2, CZ + ri * math.sin(tb)),
                (CX + ri * math.cos(ta), TOP + 2.2, CZ + ri * math.sin(ta))], color="red", border=None, sag=1.1)
print(len(ring), "wall cells,", len(piers), "piers,", len(tops), "velarium masts")

# ---- shops in every other ground arch: a counter in the back half of the opening
goods = [["melon", "decorated_pot[facing=east]", "hay_block"], ["white_wool", "red_wool", "yellow_wool"],
         ["pumpkin", "barrel[facing=up]", "decorated_pot[facing=east]"], ["hay_block", "melon", "pumpkin"]]
shops = 0
for i, th0 in enumerate(piers[:-1]):
    th_mid = th0 + (BAY / 2) / RO
    u = (th_mid - TH0) / (TH1 - TH0)
    if i % 2 == 0 or u > 0.8:
        continue
    g = goods[shops % len(goods)]
    for j, off in enumerate((-1.0, 0.0, 1.0)):
        cx, cz = at(RO - 1.5, th_mid + off / RO)
        S.set(cx, T1B, cz, "barrel[facing=up]" if j != 1 else "dark_oak_slab[type=top]")
        S.set(cx, T1B + 1, cz, g[j])
    for rr in (RO - 0.5, RO - 1.5):          # hang it in the crown of the arch, inside the wall
        lx, lz = at(rr, th_mid)
        if (lx, lz) in ring and S.get(lx, T1B + 5, lz) != "minecraft:air":
            S.set(lx, T1B + 4, lz, "lantern[hanging=true]")
            break
    shops += 1

# ---- market street along the foot of the wall: paving, striped stalls, amphorae, crates
for x in range(-26, -9):
    for z in range(-20, 12):
        r, th = polar(x, z)
        if r > RO and S.get(x, Y + 1, z) == "minecraft:air" and S.get(x, Y, z) != "minecraft:air":
            S.put((x, Y, z), T.path)
for (z, col) in ((-11, "red"), (-3, "yellow"), (5, "red")):
    props.market_stall((-13, Y, z), facing="east", color=col)
for (x, z, b) in [(-15, -15, "decorated_pot[facing=east]"), (-14, -15, "decorated_pot[facing=east]"),
                  (-15, -14, "barrel[facing=up]"), (-16, -7, "decorated_pot[facing=east]"),
                  (-16, -6, "barrel[facing=up]"), (-16, 1, "composter[level=8]"), (-15, 1, "hay_block"),
                  (-14, 10, "decorated_pot[facing=north]"), (-15, 10, "barrel[facing=up]"),
                  (-11, -7, "decorated_pot[facing=east]"), (-11, 1, "decorated_pot[facing=east]")]:
    if S.get(x, Y + 1, z) == "minecraft:air":
        S.set(x, Y + 1, z, b)
for (x, z) in ((-15, -14), (-16, -6), (-15, 10)):
    S.set(x, Y + 2, z, "decorated_pot[facing=east]")
