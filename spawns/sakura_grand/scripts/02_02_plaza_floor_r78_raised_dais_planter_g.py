r = np.random.default_rng(42)
PR = 78
xs = np.arange(-80, 81)
X, Z = np.meshgrid(xs, xs, indexing="ij")
R = np.hypot(X, Z)
pts = []
for _ in range(120000):
    if len(pts) >= 205: break
    p = r.uniform(-PR, PR, 2)
    if np.hypot(*p) > PR: continue
    if len(pts) == 0 or np.min(np.hypot(*(np.array(pts) - p).T)) > 7.7: pts.append(p)
pts = np.array(pts)
dx = X[..., None] - pts[:, 0]; dz = Z[..., None] - pts[:, 1]
d = np.abs(dx) + np.abs(dz) + 0.35 * np.maximum(np.abs(dx), np.abs(dz))
idx = d.argmin(-1)
wcell = r.random(len(pts)) < 0.46
iswhite = wcell[idx]
plaza = R <= PR
curb = plaza & (R > 75.2)
dais = R <= 30
steps = (R > 30) & (R <= 37.5)
planter = R <= 18.5
white = plaza & iswhite & ~curb & ~steps & ~planter
dark = plaza & ~white & ~curb & ~steps & ~planter
def m2(a, y=64): return Mask((int(xs[0]), y, int(xs[0])), a[:, None, :])
DARK = P.patches({"polished_blackstone": 4, "blackstone": 3, "polished_deepslate": 2, "deepslate_tiles": 2,
                  "polished_blackstone_bricks": 2, "cobbled_deepslate": 1}, size=4, seed=3)
WHITE = P.patches({"white_concrete": 5, "snow_block": 4, "calcite": 1}, size=4, seed=4)
BR = P.mix({"polished_blackstone_bricks": 6, "cracked_polished_blackstone_bricks": 2, "deepslate_tiles": 1}, seed=5)
S.put(m2(dark & ~dais), DARK); S.put(m2(white & ~dais), WHITE); S.put(m2(curb), BR)
S.put(m2(plaza & (np.abs(R - 71.5) < 0.55)), "polished_deepslate")
S.put(m2(plaza & (np.abs(R - 40.0) < 0.55)), "chiseled_deepslate")
# raised dais with half-block steps
S.put(m2(R <= 37.5), "polished_blackstone")
hs = np.select([R <= 30, R <= 31.5, R <= 33, R <= 34.5, R <= 36, R <= 37.5], [6, 5, 4, 3, 2, 1], 0)
for k in range(3):
    y = 65 + k
    S.put(m2(hs >= 2 * (k + 1), y), BR)
    S.put(m2(hs == 2 * k + 1, y), "polished_blackstone_brick_slab[type=bottom]")
S.put(m2(dark & dais, 67), DARK); S.put(m2(white & dais, 67), WHITE)
S.put(m2(np.abs(R - 29.4) < 0.6, 67), "chiseled_polished_blackstone")
S.put(m2(R <= 18.5, 67), "dirt")
S.put(m2(R <= 17.0, 68), P.patches({"moss_block": 5, "podzol": 2, "grass_block": 2, "rooted_dirt": 1}, size=3, seed=6))
S.put(m2((R > 17.0) & (R <= 18.5), 68), P.mix({"polished_blackstone_bricks": 5, "cracked_polished_blackstone_bricks": 1}, seed=7))
for k in range(20):
    a = k * math.pi / 10
    S.set(int(round(17.8 * math.cos(a))), 68, int(round(17.8 * math.sin(a))), "chiseled_polished_blackstone")

rng = np.random.default_rng(8)
G, SM, CL, DR = trees._grow, trees._segments_mask, trees._cluster, trees._droop
base = np.array([0.5, 68.0, 0.5])
trunk, top = G(base, np.array([0.03, 1.0, -0.02]), 54.0, 10.5, 6.2, rng, step=2.0, wobble=0.06)
segs = list(trunk); tips = []; mids = []
nb = 16
tl = [0.56, 0.95, 0.7, 0.86, 0.62, 1.0, 0.74, 0.9, 0.58, 0.82, 0.66, 0.97, 0.78, 0.88, 0.6, 0.93]
for i in range(nb):
    k = min(len(trunk) - 1, int(tl[i] * len(trunk)) - 1)
    start = np.array(trunk[k][1])
    az = math.radians(i * (360 / nb) + rng.uniform(-7, 7))
    rho = rng.uniform(36, 50)
    target = np.array([0.5 + rho * math.cos(az), rng.uniform(134, 152), 0.5 + rho * math.sin(az)])
    v = target - start
    L = float(np.linalg.norm(v)) * 1.04
    d0 = v / np.linalg.norm(v) + np.array([0, 0.28, 0])
    br, tip = G(start, d0, L, 4.9, 1.5, rng, step=1.6, wobble=0.09, gravity=0.04)
    segs += br; tips.append(tip); mids.append(br[len(br) // 2][1]); mids.append(br[int(len(br) * 0.78)][1])
    for s in range(5):
        j = int(len(br) * rng.uniform(0.35, 0.9))
        sdv = trees._perturb(d0 + np.array([0, 0.25, 0]), rng, 0.8)
        sdv[1] = abs(sdv[1]) * 0.6 + 0.15
        sb, stip = G(br[j][1], sdv, L * rng.uniform(0.3, 0.5), 2.2, 0.7, rng, wobble=0.18)
        segs += sb; tips.append(stip); mids.append(sb[len(sb) // 2][1])
for k in range(8):
    az = math.radians(k * 45 + 20)
    sb, stip = G(top, np.array([math.cos(az) * 0.65, 1.0, math.sin(az) * 0.65]), rng.uniform(18, 25), 3.4, 0.9, rng, wobble=0.12)
    segs += sb; tips.append(stip); mids.append(sb[len(sb) // 2][1])
tips.append(top + np.array([0, 13.0, 0]))
roots = []
for i in range(12):
    az = i * (2 * math.pi / 12) + rng.uniform(-0.22, 0.22)
    dvec = np.array([math.cos(az), -0.08, math.sin(az)])
    L = rng.uniform(13, 17) if i % 3 else rng.uniform(21, 26)
    rt, _ = G(base + np.array([0, 4.4, 0]), dvec, L, 5.4, 1.0, rng, step=1.5, wobble=0.12, gravity=0.15)
    roots += rt
wood = SM(segs) | SM(roots).where(lambda x, y, z: y >= 68)
wood = wood.where(lambda x, y, z: (y >= 69) | (np.hypot(x, z) > 18.5))
leaves = Mask.empty()
for i, tip in enumerate(tips):
    c = np.array(tip) + np.array([0, 2.0, 0]); c[1] = max(c[1], 131.0)
    leaves = leaves | CL(c, rng.uniform(10.0, 13.0), 0.6, rng, 100 + i)
for i, mm in enumerate(mids):
    c = np.array(mm) + np.array([0, 4.0, 0]); c[1] = max(c[1], 130.0)
    leaves = leaves | CL(c, rng.uniform(7.0, 9.5), 0.62, rng, 300 + i)
leaves = leaves.where(lambda x, y, z: y >= 121)
leaves = DR(leaves, rng, 0.2, 8, 9)
leaves = leaves - wood
woodpal = P.patches({"crimson_hyphae": 6, "dark_oak_wood": 2, "stripped_spruce_wood": 2, "spruce_wood": 2,
                     "stripped_dark_oak_wood": 1, "mangrove_wood": 1}, size=5, seed=11)
S.put(wood, woodpal)
S.put(leaves, "cherry_leaves", only="air")
core = leaves.erode(2)
glow = Mask.from_points(core.sample(count=6000, min_dist=8, seed=3))
S.put(glow, "shroomlight")
pr = np.random.default_rng(5); n = 0
for _ in range(2600):
    a = pr.uniform(0, 2 * math.pi); rr_ = pr.uniform(19, 74)
    if 30 < rr_ < 38: continue
    y = 68 if rr_ <= 30 else 65
    x, z = int(round(rr_ * math.cos(a))), int(round(rr_ * math.sin(a)))
    if str(S.get(x, y, z)).endswith("air"):
        S.set(x, y, z, f"pink_petals[facing={['north','east','south','west'][int(pr.integers(4))]},flower_amount={int(pr.integers(1, 5))}]"); n += 1
print("cells", len(pts), "wood", wood.count, "leaves", leaves.count, "glow", glow.count, "top", top, "petals", n)
print("leaves bbox", leaves.bbox, "wood bbox", wood.bbox)
np.savez("/home/user/BuildMCP-test-project-/builds/sakura_grand/tree.npz", tips=np.array(tips), mids=np.array(mids))
mark("spawn", (0, 65, 56), "spawn", yaw=180)
