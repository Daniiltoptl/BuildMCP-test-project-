hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz")
Ht, water, sdp, pisl = hm["Ht"], hm["water"], hm["sd_pond"], hm["pisl"]
N = 216
rg = np.random.default_rng(5)
STONE = ["stone", "stone", "andesite", "andesite", "mossy_cobblestone", "cobblestone", "tuff", "mossy_stone_bricks"]
def is_w(x, z): return bool(water[int(round(x)) + N, int(round(z)) + N])
def stone(cx, cz, r):
    n = 0
    for x in range(int(cx - r - 2), int(cx + r + 3)):
        for z in range(int(cx * 0 + cz - r - 2), int(cz + r + 3)):
            if not is_w(x, z): continue
            d = math.hypot(x - cx, z - cz) + 0.35 * float(noise.fbm(np.array([x]), np.array([z]), 0, scale=3, seed=3)[0])
            bed = int(Ht[x + N, z + N])
            if d <= r:
                for y in range(bed + 1, 65): S.set(x, y, z, STONE[int(rg.integers(len(STONE)))])
                n += 1
            elif d <= r + 0.9:
                for y in range(bed + 1, 63): S.set(x, y, z, STONE[int(rg.integers(len(STONE)))])
    return n
def route(p0, p1, jit=1.1):
    """stones between two land points; only cells in water are filled"""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    v = p1 - p0; L = float(np.hypot(*v)); u = v / L; nrm = np.array([-u[1], u[0]])
    k = max(1, int(round(L / 4.3)))
    out = []
    for i in range(k):
        t = (i + 0.5) / k
        c = p0 + v * t + nrm * rg.uniform(-jit, jit)
        out.append((float(c[0]), float(c[1]), float(rg.uniform(1.25, 1.85))))
    return out
def edge(ax, az, r0, r1, cond):
    """first radius along a ray where cond(x,z) holds"""
    for r in np.arange(r0, r1, 0.25 if r1 > r0 else -0.25):
        if cond(ax * r, az * r): return float(r)
    return float(r1)
total = 0
# cardinal east/west + four off-axis routes straight across
for ang in (0, 180, 28, 152, 208, 332, 62, 118, 242, 298):
    a = math.radians(ang); ax, az = math.cos(a), math.sin(a)
    r_out = edge(ax, az, 80, 112, lambda x, z: not is_w(x, z))
    for (cx, cz, r) in route((ax * 78.4, az * 78.4), (ax * (r_out - 0.2), az * (r_out - 0.2))):
        total += stone(cx, cz, r)
# diagonals via the islands
for (ix, iz) in ((63, 63), (-63, 63), (-63, -63), (63, -63)):
    a = math.atan2(iz, ix); ax, az = math.cos(a), math.sin(a)
    ri = math.hypot(ix, iz)
    r_in = edge(ax, az, ri, 78, lambda x, z: is_w(x, z))
    r_o = edge(ax, az, ri, 112, lambda x, z: is_w(x, z))
    r_sh = edge(ax, az, r_o + 1, 114, lambda x, z: not is_w(x, z))
    for (cx, cz, r) in route((ax * 78.4, az * 78.4), (ax * (r_in + 0.3), az * (r_in + 0.3)), 0.6) + route((ax * (r_o - 0.3), az * (r_o - 0.3)), (ax * (r_sh - 0.2), az * (r_sh - 0.2)), 0.6):
        total += stone(cx, cz, r)
print("stone cells", total)

# red arched bridges on the north and south avenue
RED = "red_nether_bricks"; RW = "red_nether_brick_wall"
def bridge(sgn):
    z0 = 78
    zs = int(edge(0, 1, 80, 116, lambda x, z: not is_w(0, sgn * z) and not is_w(5, sgn * z) and not is_w(-5, sgn * z))) + 2
    L = zs - z0
    for i in range(L + 1):
        z = sgn * (z0 + i); t = i / L
        h2 = int(round(2 * 4.0 * math.sin(math.pi * t)))
        full, half = h2 // 2, h2 % 2
        ytop = 64 + full
        for x in range(-5, 6):
            edge_ = abs(x) == 5
            S.fill((x, max(64, ytop - 1), z, x, ytop, z), RED if edge_ or (i % 6 == 0) else "mangrove_planks")
            if ytop - 2 >= 64: S.set(x, ytop - 2, z, f"red_nether_brick_slab[type=top]" if not edge_ else RED)
            if half: S.set(x, ytop + 1, z, "red_nether_brick_slab[type=bottom]" if edge_ or (i % 6 == 0) else "mangrove_slab[type=bottom]")
        for x in (-5, 5):
            yb = ytop + 1 + half
            if half: S.set(x, ytop + 1, z, RED)
            post = (i % 6 == 0)
            S.set(x, yb, z, RED if post else RW)
            if post:
                S.set(x, yb + 1, z, RW); S.set(x, yb + 2, z, "ochre_froglight"); S.set(x, yb + 3, z, "deepslate_tile_slab[type=bottom]")
            else:
                S.set(x, yb + 1, z, "red_nether_brick_slab[type=bottom]")
        if i in (L // 3, 2 * L // 3):       # piers
            for x in (-5, -4, 4, 5):
                for zz in (z, z + sgn):
                    bed = int(Ht[x + N, zz + N])
                    S.fill((x, bed + 1, zz, x, ytop - 2, zz), "polished_blackstone_bricks")
    return zs
zs_s = bridge(1); zs_n = bridge(-1)
print("bridge ends", zs_s, zs_n)

# lily pads and underwater glow
xs = np.arange(-N, N + 1); X, Z = np.meshgrid(xs, xs, indexing="ij")
wm = Mask((-N, 63, -N), (water & (sdp < 0))[:, None, :])
open_w = S.mask("water", wm)
lil = Mask.from_points(open_w.sample(count=900, min_dist=2, seed=4)).translate(0, 1, 0) if hasattr(Mask, "translate") else None
nl = 0
for (x, y, z) in open_w.sample(count=900, min_dist=2, seed=4):
    if abs(x) <= 7 and abs(z) > 70: continue
    if str(S.get(x, 64, z)).endswith("air") and float(noise.fbm(np.array([x]), np.array([z]), 0, scale=14, seed=8)[0]) > 0.05:
        S.set(x, 64, z, "lily_pad"); nl += 1
ng = 0
for (x, y, z) in open_w.sample(count=400, min_dist=9, seed=6):
    bed = int(Ht[x + N, z + N])
    if S.get(x, bed + 1, z).endswith("water"):
        S.set(x, bed, z, "sea_lantern"); ng += 1
        if rg.random() < 0.6: S.set(x, bed + 1, z, f"sea_pickle[pickles={int(rg.integers(2, 5))},waterlogged=true]")
print("lilies", nl, "glow", ng)
