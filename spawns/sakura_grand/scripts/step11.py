# 3D models: dragon sculpture on the trunk + display-entity props
hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz")
Ht, water, sdp = hm["Ht"], hm["water"], hm["sd_pond"]; N = 216
rg = np.random.default_rng(55)
Y0 = 65
def gy(x, z): return int(S.top_y(int(x), int(z)) or Ht[int(x) + N, int(z) + N])
def isair(x, y, z): return str(S.get(int(x), int(y), int(z))).endswith("air")
def roty(v, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)
NENT = [0]
def bd(cb, block, scale, yaw=0):
    """block display whose scaled box is centred on cb (x, z) with its bottom at cb.y"""
    sx, sy, sz = (scale,) * 3 if isinstance(scale, (int, float)) else scale
    off = roty((sx / 2, 0, sz / 2), yaw)
    E.block_display((cb[0], cb[1], cb[2]), block, scale=(sx, sy, sz), rotation=((0, 1, 0), yaw) if yaw else None,
                    translation=(-off[0], 0, -off[2]))
    NENT[0] += 1
def part(base, yaw, off, block, scale):
    o = roty((off[0], 0, off[2]), yaw)
    bd((base[0] + o[0], base[1] + off[1], base[2] + o[2]), block, scale, yaw)

# ---------------------------------------------------------------- DRAGON (blocks)
SM = trees._segments_mask
def tr(y): return 10.5 - (y - 68) * (4.3 / 54)
n = 110; pts = []; rad_b = []
for i in range(n + 1):
    t = i / n
    y = 70 + 21 * t
    th = math.pi / 2 - 2.5 * math.pi * (1 - t)
    rad = tr(y) + 1.0
    if t > 0.86:
        k = (t - 0.86) / 0.14
        rad += 7.5 * k ** 1.5; y += 2.0 * k
    pts.append(np.array([0.5 + (y - 68) * 0.03 + rad * math.cos(th), y, 0.5 - (y - 68) * 0.02 + rad * math.sin(th)]))
    tt = min(1.0, t / 0.28); rad_b.append(0.7 + 1.9 * tt * tt * (3 - 2 * tt))
segs = [(pts[i], pts[i + 1], rad_b[i], rad_b[i + 1]) for i in range(n)]
body = SM(segs)
legs = []
for t in (0.34, 0.5, 0.66, 0.8):
    i = int(t * n); p = pts[i]
    inward = np.array([0.5 - p[0], 0, 0.5 - p[2]]); inward /= np.linalg.norm(inward)
    side = np.array([-inward[2], 0, inward[0]])
    for sgn in (-1, 1):
        a = p + side * sgn * 1.6
        b = a + np.array([0, -3.2, 0]) + inward * 0.8 + side * sgn * 1.2
        legs.append((a, b, 1.1, 0.8))
        S.set(int(b[0]), int(b[1]) - 1, int(b[2]), "bone_block") if isair(b[0], b[1] - 1, b[2]) else None
H = pts[-1]
Hc = H + np.array([0, 0.8, 2.4])
head = (sdf.ellipsoid(tuple(Hc), (2.8, 2.4, 3.6)) | sdf.ellipsoid(tuple(Hc + np.array([0, -0.5, 3.4])), (1.9, 1.5, 2.6))).mask()
jaw = sdf.ellipsoid(tuple(Hc + np.array([0, -2.7, 2.6])), (1.6, 0.8, 3.0)).mask()
SKIN = P.patches({"red_concrete": 5, "red_terracotta": 2, "nether_wart_block": 2, "red_nether_bricks": 1}, size=2, seed=2)
S.put(body | SM(legs), SKIN, only="air")
S.put(head, SKIN, only="air"); S.put(jaw, "red_terracotta", only="air")
# golden spine and mane
for i in range(8, n - 4, 2):
    p = pts[i]; out = np.array([p[0] - 0.5, 0, p[2] - 0.5]); out /= np.linalg.norm(out)
    q = p + np.array([0, rad_b[i] + 0.5, 0]) + out * 0.6
    c = (int(math.floor(q[0])), int(math.floor(q[1])), int(math.floor(q[2])))
    if isair(*c):
        S.set(*c, "gold_block")
        if i % 6 == 0 and isair(c[0], c[1] + 1, c[2]): S.set(c[0], c[1] + 1, c[2], "gold_block")
hx, hy, hz = (int(math.floor(v)) for v in Hc)
for dz in range(-3, 1):
    S.set(hx, hy + 3, hz + dz, "gold_block")
for sgn in (-1, 1):                                   # horns, eyes, whiskers
    for k in range(5):
        q = Hc + np.array([sgn * (1.4 + 0.35 * k), 2.2 + 0.8 * k, -0.8 - 0.75 * k])
        S.set(int(math.floor(q[0])), int(math.floor(q[1])), int(math.floor(q[2])), "bone_block")
    S.set(int(math.floor(Hc[0] + sgn * 2.6)), hy + 1, hz + 2, "ochre_froglight")
    S.set(int(math.floor(Hc[0] + sgn * 1.9)), hy - 1, hz + 6, "gold_block")
    for k in range(1, 4):
        S.set(int(math.floor(Hc[0] + sgn * (1.9 + 0.9 * k))), hy - 1 - (k // 2), hz + 6 + k // 2, "chain[axis=x]" if k < 3 else "gold_block")
for dx in (-1, 0, 1):
    S.set(hx + dx, hy - 2, hz + 5, "bone_block") if isair(hx + dx, hy - 2, hz + 5) else None
# the pearl the dragon guards
pearl = Hc + np.array([0, -1.6, 7.5])
S.put(sdf.sphere(tuple(pearl), 1.7).mask(), "pearlescent_froglight", only="air")
S.set(int(pearl[0]), int(pearl[1]) + 2, int(pearl[2]), "gold_block")
print("dragon body", body.count, "head at", [round(float(v), 1) for v in Hc])

# ---------------------------------------------------------------- BELL (40,40)
bc = (40.5, 40.5)
for (y, s) in ((68.3, (2.7, 0.5, 2.7)), (68.8, (2.3, 2.6, 2.3)), (71.4, (1.6, 0.5, 1.6))):
    bd((bc[0], y, bc[1]), "waxed_exposed_copper", s)
bd((bc[0], 71.9, bc[1]), "gold_block", (0.5, 0.35, 0.5))
bd((bc[0], 69.6, bc[1]), "waxed_exposed_cut_copper", (2.36, 0.3, 2.36))
S.fill((40, 72, 40, 40, 72, 40), "chain[axis=y]")
bd((36.6, 69.6, 40.5), "stripped_spruce_log[axis=x]", (3.0, 0.55, 0.55))
for x in (36, 37): S.fill((x, 70, 40, x, 73, 40), "chain[axis=y]")

# ---------------------------------------------------------------- LANTERN RACKS in the four empty big frames
def qpost(p1, p2, t, s): return (p1, p2) if s > 0 else (-(p2 + t - 1), -(p1 + t - 1))
def qv(q, t, s): return q if s > 0 else -(q + t - 1)
quads = [(1, -1), (1, 1), (-1, 1), (-1, -1)]
for i, (sx, sz) in enumerate(quads):
    ax = "z" if i % 2 == 0 else "x"
    su, sv = (sz, sx) if ax == "z" else (sx, sz)
    a, b = qpost(19, 40, 3, su); v = qv(58, 3, sv) + 1
    u1, u2 = a + 5, b - 3
    def P3(u, y): return (u, y, v) if ax == "x" else (v, y, u)
    logax = "x" if ax == "x" else "z"
    for u in (u1, u2): S.fill(P3(u, Y0) + P3(u, Y0 + 8), "stripped_dark_oak_log[axis=y]")
    for yb in (Y0 + 8, Y0 + 5):
        S.fill(P3(u1, yb) + P3(u2, yb), f"stripped_dark_oak_log[axis={logax}]")
    S.fill(P3(u1 - 1, Y0 + 9) + P3(u2 + 1, Y0 + 9), "deepslate_tile_slab[type=bottom]")
    for row, yb in enumerate((Y0 + 8, Y0 + 5)):
        for j, u in enumerate(range(u1 + 1, u2, 2)):
            c = P3(u, 0)
            col = "red_wool" if (j + row) % 3 else "white_wool"
            bd((c[0] + 0.5, yb - 1.15, c[2] + 0.5), col, (0.78, 1.0, 0.78))
            bd((c[0] + 0.5, yb - 0.17, c[2] + 0.5), "black_concrete", (0.46, 0.17, 0.46))
            bd((c[0] + 0.5, yb - 1.27, c[2] + 0.5), "black_concrete", (0.46, 0.12, 0.46))
            S.set(*P3(u, yb - 1), "light[level=11]")

# ---------------------------------------------------------------- KITSUNE guardian statues
def kitsune(x, z, yaw, y=None):
    y = gy(x, z) + 1 if y is None else y
    S.set(x, y, z, "polished_blackstone_bricks"); S.set(x, y + 1, z, "chiseled_polished_blackstone")
    b = (x + 0.5, y + 2, z + 0.5)
    part(b, yaw, (0, 0.0, 0.0), "calcite", (0.7, 0.95, 0.6))
    part(b, yaw, (0, 0.62, 0.02), "red_wool", (0.76, 0.2, 0.66))
    part(b, yaw, (0, 0.95, 0.12), "calcite", (0.56, 0.5, 0.56))
    part(b, yaw, (0, 0.98, 0.5), "calcite", (0.26, 0.2, 0.3))
    part(b, yaw, (0.18, 1.45, 0.05), "calcite", (0.14, 0.3, 0.1))
    part(b, yaw, (-0.18, 1.45, 0.05), "calcite", (0.14, 0.3, 0.1))
    part(b, yaw, (0, 0.1, -0.45), "calcite", (0.3, 1.0, 0.3))
    part(b, yaw, (0, 1.1, -0.45), "red_wool", (0.22, 0.25, 0.22))
for (x, z, yaw) in ((7, 109, 180), (-7, 109, 180), (7, -105, 0), (-7, -105, 0), (-116, -10, 90), (-116, 2, 90)):
    kitsune(x, z, yaw)
for (x, z, yaw) in ((12, 39, 0), (-12, 39, 0), (12, -39, 180), (-12, -39, 180)):
    kitsune(x, z, yaw, Y0)

# ---------------------------------------------------------------- WAGASA umbrellas with benches
def wagasa(x, z, y, facing):
    c = (x + 0.5, z + 0.5)
    bd((c[0], y, c[1]), "stripped_dark_oak_log", (0.14, 2.9, 0.14))
    bd((c[0], y + 2.75, c[1]), "red_carpet", (3.6, 1.0, 3.6))
    bd((c[0], y + 2.92, c[1]), "red_carpet", (2.2, 1.0, 2.2))
    bd((c[0], y + 3.08, c[1]), "red_carpet", (0.9, 1.0, 0.9))
    bd((c[0], y + 3.1, c[1]), "gold_block", (0.16, 0.3, 0.16))
    dx, dz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[facing]
    props.bench((x - dx - (1 if dz else 0), y - 1, z - dz - (1 if dx else 0)), facing=facing, length=3)
for (x, z, y, f) in ((52, -20, Y0, "west"), (-52, 22, Y0, "east"), (22, 52, Y0, "north"), (-22, -52, Y0, "south")):
    wagasa(x, z, y, f)
for (x, z, f) in ((143, 3, "north"), (89, 117, "north"), (-94, 106, "west"), (-100, -103, "west")):
    wagasa(x, z, gy(x, z) + 1, f)

# ---------------------------------------------------------------- BONSAI on stone pedestals
def bonsai(x, z, y, k):
    S.set(x, y, z, "chiseled_polished_blackstone")
    c = (x + 0.5, z + 0.5)
    bd((c[0], y + 1, c[1]), "terracotta", (0.6, 0.22, 0.6))
    bd((c[0], y + 1.22, c[1]), "spruce_log", (0.16, 0.5, 0.16))
    leaf = "flowering_azalea_leaves" if k % 2 else "azalea_leaves"
    bd((c[0] - 0.12, y + 1.6, c[1] + 0.05), leaf, (0.62, 0.34, 0.5))
    bd((c[0] + 0.2, y + 1.82, c[1] - 0.1), leaf, (0.42, 0.28, 0.4))
for k, (x, z) in enumerate(((14, 47), (-14, 47), (14, -47), (-14, -47), (47, 14), (-47, -14), (47, -14), (-47, 14))):
    if isair(x, Y0, z) or "petals" in str(S.get(x, Y0, z)): bonsai(x, z, Y0, k)

# ---------------------------------------------------------------- KOI in the pond
pond = Mask((-N, 63, -N), (water & (sdp < -2))[:, None, :])
nk = 0
for (x, y, z) in S.mask("water", pond).sample(count=200, min_dist=6, seed=12):
    if nk >= 30 or not isair(x, 64, z) or math.hypot(x, z) > 97: continue
    q = float(rg.uniform(0, 360))
    E.item_display((x + 0.5, 63.93, z + 0.5), ["tropical_fish", "salmon", "tropical_fish", "cod"][nk % 4], scale=float(rg.uniform(1.4, 2.1)),
                   rotation=((1, 0, 0), 90 if nk % 2 else -90)); nk += 1; NENT[0] += 1

# ---------------------------------------------------------------- KATANA racks
def rack(x0, z, y):
    for x in (x0, x0 + 3):
        S.set(x, y, z, "dark_oak_fence"); S.set(x, y + 1, z, "dark_oak_fence"); S.set(x, y + 2, z, "dark_oak_fence")
    S.fill((x0, y + 3, z, x0 + 3, y + 3, z), "dark_oak_slab[type=bottom]")
    for k, it in enumerate(("netherite_sword", "iron_sword", "golden_sword")):
        E.item_display((x0 + 2.0, y + 0.55 + 0.8 * k, z + 0.5), it, scale=2.2, rotation=((0, 0, 1), -45)); NENT[0] += 1
rack(-28, -51, Y0); rack(25, 51, Y0)

# ---------------------------------------------------------------- GIANT KATANA in the rock on the NW pond island
ty = gy(-64, -64)
base = (-63.5, ty - 0.6, -63.5)
tilt = 9.0
c_, s_ = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
def kpart(h, block, sc):
    lx, ly, lz = -sc[0] / 2, h, -sc[2] / 2
    E.block_display(base, block, scale=sc, rotation=((0, 0, 1), tilt), translation=(lx * c_ - ly * s_, lx * s_ + ly * c_, lz)); NENT[0] += 1
kpart(0.0, "iron_block", (0.5, 6.2, 0.14))
kpart(6.2, "gold_block", (1.3, 0.28, 0.5))
kpart(6.48, "black_wool", (0.32, 1.7, 0.32))
kpart(8.18, "gold_block", (0.44, 0.3, 0.44))

# ---------------------------------------------------------------- mini shrine (hokora) with a little spirit, on the dais
mx, mz, my = -9, 26, 68
S.fill((mx - 1, my, mz - 1, mx + 1, my, mz + 1), "polished_blackstone_brick_slab[type=bottom]")
S.set(mx, my, mz, "chiseled_polished_blackstone")
b = (mx + 0.5, my + 1, mz + 0.5)
bd((b[0], b[1], b[2]), "red_nether_bricks", (1.3, 0.25, 1.1))
for sx in (-0.55, 0.55): bd((b[0] + sx, b[1] + 0.25, b[2]), "red_nether_bricks", (0.2, 1.0, 1.0))
bd((b[0], b[1] + 0.25, b[2] - 0.42), "red_nether_bricks", (1.1, 1.0, 0.16))
bd((b[0], b[1] + 1.25, b[2]), "deepslate_tiles", (1.9, 0.22, 1.6))
bd((b[0], b[1] + 1.47, b[2]), "deepslate_tiles", (1.3, 0.2, 1.2))
bd((b[0], b[1] + 1.67, b[2]), "gold_block", (0.2, 0.25, 0.2))
bd((b[0], b[1] + 0.25, b[2] + 0.05), "amethyst_block", (0.5, 0.5, 0.45))
for sx in (-0.13, 0.13): bd((b[0] + sx, b[1] + 0.5, b[2] + 0.29), "ochre_froglight", (0.1, 0.1, 0.04))
for sx in (-0.2, 0.2): bd((b[0] + sx, b[1] + 0.75, b[2] + 0.05), "amethyst_block", (0.12, 0.2, 0.12))
S.set(mx, my + 1, mz, "light[level=9]")
print("display entities", NENT[0])
