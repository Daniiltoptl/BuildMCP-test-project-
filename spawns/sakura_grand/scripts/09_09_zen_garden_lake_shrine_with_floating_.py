hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz"); Ht = hm["Ht"]; water = hm["water"]; N = 216
RED="red_nether_bricks"; RS="red_nether_brick_stairs"; DT="deepslate_tiles"; DSL="deepslate_tile_slab"
rg = np.random.default_rng(12)
def gy(x, z): return int(S.top_y(int(x), int(z)) or Ht[int(x) + N, int(z) + N])
def toro(x, z, y):
    S.set(x,y,z,"chiseled_polished_blackstone"); S.set(x,y+1,z,"polished_blackstone_wall")
    S.set(x,y+2,z,"polished_blackstone_slab[type=top]"); S.set(x,y+3,z,"ochre_froglight")
    for f,(dx,dz) in (("north",(0,-1)),("south",(0,1)),("west",(-1,0)),("east",(1,0))):
        S.set(x+dx,y+3,z+dz,f"dark_oak_trapdoor[facing={f},open=true,half=bottom]")
    S.fill((x-1,y+4,z-1,x+1,y+4,z+1), f"{DSL}[type=bottom]"); S.set(x,y+4,z,DT); S.set(x,y+5,z,"polished_blackstone_wall")
def flat(x1, z1, x2, z2, y, pal):
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            g = int(Ht[x + N, z + N])
            if g < y: S.fill((x, g, z, x, y - 1, z), "dirt")
    S.fill((x1, y + 1, z1, x2, y + 10, z2), "air"); S.fill((x1, y, z1, x2, y, z2), pal)
def pavilion(cx, cz, y0, h, post="stripped_dark_oak_log[axis=y]", floor="spruce_planks", half=3, ov=2):
    S.fill((cx-half-1, y0, cz-half-1, cx+half+1, y0, cz+half+1), "spruce_slab[type=bottom]")
    S.fill((cx-half, y0, cz-half, cx+half, y0, cz+half), floor)
    for dx in (-half, half):
        for dz in (-half, half):
            S.fill((cx+dx, y0+1, cz+dz, cx+dx, y0+h, cz+dz), post)
    yb = y0 + h
    S.fill((cx-half, yb, cz-half, cx+half, yb, cz+half), "dark_oak_planks"); S.fill((cx-half+1, yb, cz-half+1, cx+half-1, yb, cz+half-1), "air")
    arch.roof((cx-half, y0+1, cz-half, cx+half, yb, cz+half), style="asian", material="deepslate_tiles", overhang=ov, pitch=0.8)
    S.set(cx, yb, cz, "chain[axis=y]"); S.set(cx, yb-1, cz, "chain[axis=y]"); S.set(cx, yb-2, cz, "ochre_froglight")
    S.set(cx, yb+1, cz, "chain[axis=y]")
# ================= ZEN GARDEN (ground block 66)
GZ = 66
flat(91, 98, 116, 120, GZ, "moss_block")
S.fill((92, GZ, 99, 115, GZ, 119), "polished_andesite")
isl = [(98, 105, 2.6), (108, 113, 3.0), (105, 103, 1.8)]
for x in range(93, 115):
    for z in range(100, 119):
        d = min(math.hypot(x - a, z - b) - r for a, b, r in isl)
        if d <= 0: blk = "moss_block"
        elif d < 6.5: blk = "calcite" if int(d + 0.5) % 2 == 0 else "white_concrete_powder"
        else: blk = "calcite" if z % 2 == 0 else "white_concrete_powder"
        S.set(x, GZ, z, blk)
for i, (a, b, r) in enumerate(isl):
    rocks.boulder((a, GZ, b), size=r * 0.75, seed=20 + i, sink=0.2)
    if i < 2: S.set(a + 2, GZ + 1, b - 1, "azalea")
for (x, z) in ((92, 99), (115, 99), (92, 119), (115, 119)): toro(x, z, GZ + 1)
flat(81, 104, 90, 114, GZ, "moss_block")
pavilion(86, 109, GZ + 1, 5)
props.bench((86, GZ + 2, 109), facing="east", length=3)
S.fill((90, GZ, 108, 91, GZ, 110), "polished_andesite")
def bamboo(cells, seed, base_y=None):
    rr = np.random.default_rng(seed)
    for (x, z) in cells:
        if rr.random() < 0.3: continue
        y = gy(x, z)
        if not str(S.get(x, y + 1, z)).endswith("air") or water[x + N, z + N]: continue
        S.set(x, y, z, "podzol")
        h = int(rr.integers(7, 15))
        for k in range(h):
            lv = "large" if k >= h - 2 else "small" if k >= h - 5 else "none"
            S.set(x, y + 1 + k, z, f"bamboo[age=1,leaves={lv},stage=0]")
bamboo([(x, z) for x in range(117, 124) for z in range(97, 122)], 3)
bamboo([(x, z) for x in range(90, 118) for z in range(121, 127)], 4)
mark("zen", (89, GZ + 1, 104), "warp", yaw=300)
# ================= LAKE SHRINE
ix, iz, iy = -118, 120, 65
S.fill((ix-3, iy+1, iz-3, ix+3, iy+1, iz+3), "stone_bricks"); S.fill((ix-4, iy+1, iz-1, ix+4, iy+1, iz+1), "stone_brick_slab[type=bottom]", only="air")
S.fill((ix+4, iy+1, iz-1, ix+4, iy+1, iz+1), "stone_brick_stairs[facing=west,half=bottom]")
for dx in (-2, 2):
    for dz in (-2, 2): S.fill((ix+dx, iy+2, iz+dz, ix+dx, iy+5, iz+dz), RED)
S.fill((ix-2, iy+2, iz-1, ix-2, iy+5, iz+1), "smooth_quartz"); S.fill((ix-1, iy+2, iz-2, ix+1, iy+5, iz-2), "smooth_quartz"); S.fill((ix-1, iy+2, iz+2, ix+1, iy+5, iz+2), "smooth_quartz")
S.fill((ix-2, iy+5, iz-2, ix+2, iy+5, iz+2), RED); S.fill((ix-1, iy+5, iz-1, ix+1, iy+5, iz+1), "air")
S.set(ix-1, iy+2, iz, "gold_block"); S.set(ix-1, iy+3, iz, "ochre_froglight"); S.set(ix-1, iy+4, iz, "red_candle[candles=3,lit=true]") if False else None
arch.roof((ix-2, iy+2, iz-2, ix+2, iy+5, iz+2), style="asian", material="deepslate_tiles", overhang=2, pitch=0.9)
A = (-90, gy(-90, 113), 113); B = (-110, iy, 119)
paths.bridge(A, B, width=3, style="asian", arch=2.5)
arch.torii((-87, gy(-87, 112), 112), "east", width=7, height=7)
tx, tz = -118, 138
bed = gy(tx, tz)
arch.torii((tx, bed, tz), "south", width=13, height=64 - bed + 12)
toro(ix + 3, iz + 3, iy + 2); toro(ix + 3, iz - 3, iy + 2)
mark("lake", (-92, gy(-92, 112) + 1, 112), "warp", yaw=80)
# ================= ONSEN (ground block 69)
ox, oz, oy = -110, -108, 69
for x in range(ox - 10, ox + 11):
    for z in range(oz - 10, oz + 11):
        d = math.hypot(x - ox, z - oz) + 1.3 * float(noise.fbm(np.array([x]), np.array([z]), 0, scale=7, seed=5)[0])
        if d < 6.3:
            S.fill((x, oy - 3, z, x, oy - 2, z), "smooth_basalt"); S.set(x, oy - 2, z, "calcite" if (x + z) % 3 else "sea_lantern")
            S.fill((x, oy - 1, z, x, oy, z), "water")
            S.fill((x, oy + 1, z, x, oy + 4, z), "air")
        elif d < 8.2:
            S.set(x, oy, z, ["stone", "andesite", "mossy_cobblestone", "cobblestone", "tuff"][int(rg.integers(5))])
            if rg.random() < 0.45: S.set(x, oy + 1, z, ["andesite", "mossy_cobblestone", "stone", "cobblestone_slab[type=bottom]", "mossy_cobblestone_slab[type=bottom]"][int(rg.integers(5))])
S.fill((ox + 6, oy + 1, oz - 1, ox + 9, oy + 1, oz + 1), "air"); S.fill((ox + 6, oy, oz - 1, ox + 11, oy, oz + 1), "spruce_planks")
flat(-127, -120, -117, -112, oy, "polished_andesite")
arch.house((-126, oy + 1, -119, -119, oy + 5, -113), door_side="east", roof_style="asian", seed=7, chimney=False)
for k in range(-150, 40, 4):
    a = math.radians(k + 180)
    x, z = int(round(ox + 11.5 * math.cos(a))), int(round(oz + 11.5 * math.sin(a)))
    y = gy(x, z)
    if str(S.get(x, y + 1, z)).endswith("air"): S.fill((x, y + 1, z, x, y + 3, z), "bamboo_fence")
toro(ox + 10, oz + 3, oy + 1); toro(ox + 10, oz - 3, oy + 1); toro(ox - 3, oz + 10, oy + 1)
mark("onsen", (ox + 10, oy + 1, oz), "warp", yaw=90)
# ================= WATERFALL CLIFF
px, pz = 121, -121
xs = np.arange(96, 172); zs = np.arange(-172, -96)
X, Z = np.meshgrid(xs, zs, indexing="ij")
s = ((X - px) - (Z - pz)) / math.sqrt(2); p = ((X - px) + (Z - pz)) / math.sqrt(2)
nz = noise.fbm(X, Z, 0, scale=9, octaves=2, seed=44)
def ss(e0, e1, v):
    t = np.clip((v - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)
Hc = 64 + 33 * ss(10.0, 13.5, s + 1.6 * nz) * ss(27, 14, np.abs(p) + 3 * nz) * ss(52, 40, s)
inb = np.hypot(X, Z) <= 214
H0 = Ht[X + N, Z + N]
H1 = np.where(inb, np.maximum(H0, np.round(Hc)), H0).astype(int)
rockp = ["stone", "stone", "andesite", "andesite", "tuff", "cobblestone", "mossy_cobblestone", "deepslate"]
TOP = int(H1[(np.abs(p) < 3) & (s > 14) & (s < 18)].max())
ncol = 0
for i in range(X.shape[0]):
    for k in range(X.shape[1]):
        if H1[i, k] > H0[i, k]:
            x, z = int(X[i, k]), int(Z[i, k])
            for y in range(int(H0[i, k]), int(H1[i, k]) + 1):
                S.set(x, y, z, rockp[int(rg.integers(len(rockp)))])
            S.set(x, int(H1[i, k]), z, "moss_block" if rg.random() < 0.6 else "grass_block")
            ncol += 1
# water: channel on top and falling sheet in front of the face
nfall = 0
for i in range(X.shape[0]):
    for k in range(X.shape[1]):
        x, z = int(X[i, k]), int(Z[i, k])
        if abs(p[i, k]) > 2.6: continue
        if 12.5 < s[i, k] < 24 and H1[i, k] >= TOP - 3:
            S.fill((x, int(H1[i, k]) + 1, z, x, TOP + 3, z), "air")
            S.fill((x, min(int(H1[i, k]), TOP - 2), z, x, TOP - 2, z), "stone"); S.fill((x, TOP - 1, z, x, max(TOP - 1, int(H1[i, k])), z), "air")
            S.set(x, TOP - 1, z, "water")
for i in range(1, X.shape[0] - 1):
    for k in range(1, X.shape[1] - 1):
        x, z = int(X[i, k]), int(Z[i, k])
        if abs(p[i, k]) > 2.6 or not (8 < s[i, k] < 14): continue
        if str(S.get(x, TOP - 1, z)).endswith("air") and ("water" in str(S.get(x + 1, TOP - 1, z)) or "water" in str(S.get(x, TOP - 1, z - 1))):
            y = TOP - 1
            while y > 63 and (str(S.get(x, y, z)).endswith("air") or "water" in str(S.get(x, y, z))):
                S.set(x, y, z, "water[level=8]" if y < TOP - 1 else "water[level=1]"); y -= 1; nfall += 1
print("cliff cols", ncol, "TOP", TOP, "fall cells", nfall)
for (bx_, bz_, sz_) in ((112, -128, 2.6), (128, -112, 2.4), (109, -119, 1.8), (124, -109, 1.6)):
    rocks.boulder((bx_, gy(bx_, bz_), bz_), size=sz_, seed=bx_)
mark("waterfall", (104, gy(104, -113) + 1, -113), "warp", yaw=235)
