N = 76; PR = 26
xs = np.arange(-N, N + 1)
X, Z = np.meshgrid(xs, xs, indexing="ij")
R = np.hypot(X, Z)
def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)
nz = noise.fbm(X, Z, 0, scale=26, octaves=3, seed=4)
redge = 72 + 3 * noise.fbm(X, Z, 0, scale=18, octaves=2, seed=5)
h = 64 + ss(PR + 3, 72, R) * (5.5 + 2.5 * nz) + 0.8 * nz * ss(PR + 2, PR + 12, R)
inside = R <= redge
Ht = np.where(R <= PR + 1.5, 64, np.round(h)).astype(int)
# rocky skirt below the rim
Hb = np.where(inside, np.minimum(Ht - 4, 56 + np.round(6 * ss(redge, redge - 14, R))).astype(int), 0)
slope = np.zeros_like(Ht)
for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
    slope = np.maximum(slope, np.abs(Ht - np.roll(np.roll(Ht, dx, 0), dz, 1)))
ylo, yhi = int(Hb[inside].min()), int(Ht[inside].max())
ys = np.arange(ylo, yhi + 1); Y3 = ys[None, :, None]
body = (Y3 >= Hb[:, None, :]) & (Y3 <= Ht[:, None, :]) & inside[:, None, :]
def M(a): return Mask((-N, ylo, -N), a)
def col(a): return a[:, None, :]
top = (Y3 == Ht[:, None, :]) & col(inside)
S.put(M(body), P.patches({"stone": 5, "andesite": 3, "tuff": 1, "mossy_cobblestone": 1}, size=4, seed=1))
S.put(M((Y3 < Ht[:, None, :]) & (Y3 >= Ht[:, None, :] - 3) & body), P.mix({"dirt": 5, "coarse_dirt": 1, "rooted_dirt": 1}, seed=2))
S.put(M(top & col(R > PR + 1.5)), P.patches({"grass_block": 9, "moss_block": 2}, size=6, seed=3))
S.put(M(top & col((slope >= 2) & (R > PR + 1.5))), P.patches({"moss_block": 2, "grass_block": 3, "mossy_cobblestone": 1}, size=3, seed=6))
S.set_biome((-N, ylo, -N, N, yhi + 40, N), "cherry_grove")

# ---------------- flat plaza at y=64
A = np.degrees(np.arctan2(Z, X)) % 360
pl = R <= PR
def m2(a, y=64): return Mask((-N, y, -N), a[:, None, :])
STONE = P.mix({"polished_andesite": 5, "stone_bricks": 3, "andesite": 1, "cracked_stone_bricks": 1}, cluster=2, seed=7)
S.put(m2(pl), STONE)
# rings and radial spokes in calcite / dark stone
S.put(m2(pl & (np.abs(R - 6.5) < 0.6)), "polished_deepslate")
S.put(m2(pl & (np.abs(R - 15.0) < 0.6)), "polished_deepslate")
S.put(m2(pl & (R > 6.5) & (R < 15) & ((A % 45 < 2.2) | (A % 45 > 42.8))), "calcite")
S.put(m2(pl & (R > 15) & (R < 24.5) & ((A % 22.5 < 1.3) | (A % 22.5 > 21.2))), "smooth_stone")
# central flower mosaic
petal = (R <= 6) & (np.cos(np.radians(A) * 8) * 2.2 + 3.6 > R)
S.put(m2(petal), P.mix({"pink_terracotta": 3, "pink_glazed_terracotta": 0, "cherry_planks": 1}, seed=8) if False else "pink_terracotta")
S.put(m2(R <= 1.6), "chiseled_stone_bricks")
S.put(m2(pl & (R > 24.5)), P.mix({"polished_blackstone_bricks": 4, "cracked_polished_blackstone_bricks": 1}, seed=9))
# low curb with gaps for the four paths
curb = (R > 25.3) & (R <= 26.3)
gap = (np.abs(X) <= 2) | (np.abs(Z) <= 2)
S.put(m2(curb & ~gap, 65), "polished_blackstone_brick_slab[type=bottom]")
for k in range(16):
    if k % 4 == 0: continue
    a = math.radians(k * 22.5)
    S.set(int(round(25.8 * math.cos(a))), 65, int(round(25.8 * math.sin(a))), "chiseled_polished_blackstone")
mark("spawn", (0, 65, 10), "spawn", yaw=180)
np.savez("/home/user/BuildMCP-test-project-/builds/sakura_simple/hm.npz", Ht=Ht, R=R)
print("y", ylo, yhi)
