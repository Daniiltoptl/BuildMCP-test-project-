hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz")
Ht, water, sd, sdp = hm["Ht"], hm["water"], hm["sd"], hm["sd_pond"]; N = 216
rg = np.random.default_rng(21)
def gy(x, z): return int(S.top_y(int(x), int(z)) or Ht[int(x) + N, int(z) + N])
def isair(x, y, z): return str(S.get(x, y, z)).endswith("air")
# 1. restore the waterfall pool and the river head buried by the cliff base
nfix = 0
for x in range(96, 172):
    for z in range(-172, -96):
        if water[x + N, z + N] and not isair(x, 64, z) and "water" not in str(S.get(x, 64, z)) and isair(x, 66, z):
            bed = int(Ht[x + N, z + N])
            S.fill((x, bed + 1, z, x, 63, z), "water"); S.fill((x, 64, z, x, 65, z), "air"); nfix += 1
# 2. glow under the pond
pond = Mask((-N, 63, -N), (water & (sdp < 0))[:, None, :])
ng = 0
for (x, y, z) in S.mask("water", pond).sample(count=500, min_dist=8, seed=6):
    bed = int(Ht[x + N, z + N])
    if "water" in str(S.get(x, bed + 1, z)):
        S.set(x, bed, z, "sea_lantern"); ng += 1
        if rg.random() < 0.6: S.set(x, bed + 1, z, f"sea_pickle[pickles={int(rg.integers(2, 5))},waterlogged=true]")
# 3. plaza planters with a sakura and a pine, trees on the pond islands
def planter(cx, cz, kind, h, seed):
    S.fill((cx - 4, 65, cz - 4, cx + 4, 65, cz + 4), "polished_blackstone_bricks")
    for (dx, dz) in ((-4, -4), (4, -4), (-4, 4), (4, 4)): S.set(cx + dx, 66, cz + dz, "polished_blackstone_brick_wall"); S.set(cx + dx, 65, cz + dz, "chiseled_polished_blackstone")
    S.fill((cx - 3, 65, cz - 3, cx + 3, 65, cz + 3), P.mix({"moss_block": 4, "podzol": 2, "grass_block": 1}, seed=seed))
    trees.tree((cx, 65, cz), kind, height=h, seed=seed)
    for (dx, dz) in ((-2, 2), (2, -2), (2, 2), (-2, -2)):
        if isair(cx + dx, 66, cz + dz): S.set(cx + dx, 66, cz + dz, "flowering_azalea" if (dx + dz) else "azalea")
planter(40, -40, "cherry", 15, 3); planter(-40, 40, "pine", 19, 4)
trees.tree((63, 64, 63), "cherry", height=10, seed=5); trees.tree((63, 64, -63), "cherry", height=9, seed=6)
trees.tree((-63, 64, 63), "pine", height=11, seed=7)
rocks.boulder((-64, 64, -64), size=2.2, seed=8, sink=0.2)
# keep-out geometry
ring_r = lambda a: 112 + 2.5 * np.sin(3 * a)
segs = [[(79, 79), (86, 88), (92, 97)], [(-66, 91), (-78, 100), (-88, 111)], [(-79, -79), (-90, -90), (-100, -99)],
        [(72, -86), (86, -99), (100, -112)], [(112, 0), (118, 3)], [(-112, 0), (-118, -2)], [(0, 100), (0, 198)], [(0, -100), (0, -110)]]
boxes = [(114, -25, 168, 34), (-166, -22, -115, 13), (79, 95, 126, 129), (-130, -123, -97, -95), (-21, -169, 21, -104),
         (-11, 100, 11, 198), (-16, 180, 16, 197), (-124, 110, -84, 126)]
def free(x, y, z, margin=5.0):
    x = np.asarray(x, float); z = np.asarray(z, float)
    R = np.hypot(x, z); a = np.arctan2(z, x)
    ok = (R > 107) & (R < 211) & (np.abs(R - ring_r(a)) > margin)
    for (x1, z1, x2, z2) in boxes: ok &= ~((x >= x1) & (x <= x2) & (z >= z1) & (z <= z2))
    for pl in segs:
        for (ax, az), (bx, bz) in zip(pl, pl[1:]):
            vx, vz = bx - ax, bz - az; L = vx * vx + vz * vz
            t = np.clip(((x - ax) * vx + (z - az) * vz) / L, 0, 1)
            ok &= np.hypot(x - (ax + t * vx), z - (az + t * vz)) > margin
    return ok
# 4. willows on the pond and lake shores
nw = 0
for k in range(0, 360, 24):
    a = math.radians(k + 11)
    for r in np.arange(101, 112, 0.5):
        x, z = int(round(r * math.cos(a))), int(round(r * math.sin(a)))
        if 2.5 <= sd[x + N, z + N] <= 4.5 and abs(x) > 14 and not water[x + N, z + N] and isair(x, gy(x, z) + 1, z) and "grass" in str(S.get(x, gy(x, z), z)) + "grass" * 0:
            trees.tree((x, gy(x, z), z), "willow", height=float(rg.uniform(10, 13)), seed=100 + k); nw += 1; break
for (x, z) in ((-92, 128), (-100, 96), (-140, 104), (-136, 140)):
    if not water[x + N, z + N] and sd[x + N, z + N] < 7: trees.tree((x, gy(x, z), z), "willow", height=11, seed=abs(x)); nw += 1
# 5. forest
grass = S.mask(["grass_block", "moss_block"])
surf = S.surface(grass, clearance=3)
surf = surf.where(lambda x, y, z: free(x, y, z))
valley = surf.where(lambda x, y, z: np.hypot(x, z) < 166)
rim = surf.where(lambda x, y, z: np.hypot(x, z) >= 166)
t1 = trees.forest(valley, ["cherry"] * 6 + ["bush"] * 2 + ["birch", "pine"], density=0.0075, min_dist=9, seed=31, height_scale=(0.8, 1.3))
t2 = trees.forest(rim, ["pine"] * 5 + ["cherry"] * 3 + ["oak"], density=0.013, min_dist=7, seed=32, height_scale=(0.8, 1.3))
# 6. boulders
nb = 0
for (x, y, z) in valley.sample(count=46, min_dist=22, seed=9):
    if isair(x, y + 1, z): rocks.boulder((x, y, z), size=float(rg.uniform(1.3, 2.6)), seed=abs(int(x * 3 + z))); nb += 1
# 7. ground cover
surf2 = S.surface(S.mask(["grass_block", "moss_block"]), clearance=1).where(lambda x, y, z: (np.hypot(x, z) > 100) & free(x, y, z, 2.2) | ((np.hypot(x, z) > 100) & (np.hypot(x, z) < 107)))
items = {"short_grass": 8, "pink_petals[flower_amount=4]": 3, "pink_petals[flower_amount=2]": 2, "fern": 1,
         "pink_tulip": 0.5, "allium": 0.35, "azure_bluet": 0.4, "lily_of_the_valley": 0.3, "oxeye_daisy": 0.25}
nc = terrain.cover(surf2, density=0.42, seed=3, items=items)
print("pool fix", nfix, "glow", ng, "willows", nw, "trees", len(t1), len(t2), "boulders", nb, "cover", nc)
