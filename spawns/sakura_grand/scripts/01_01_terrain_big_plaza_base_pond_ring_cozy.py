import os
N = 216
PR = 78
xs = np.arange(-N, N + 1)
X, Z = np.meshgrid(xs, xs, indexing="ij")
Rr = np.hypot(X, Z)
TH = np.arctan2(Z, X)
def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)
def seg_dist(pts):
    d = np.full(X.shape, 1e9)
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        vx, vz = bx - ax, bz - az
        L = vx * vx + vz * vz
        t = np.clip(((X - ax) * vx + (Z - az) * vz) / L, 0, 1)
        d = np.minimum(d, np.hypot(X - (ax + t * vx), Z - (az + t * vz)))
    return d
roll = 2.6 * noise.fbm(X, Z, 0, scale=54, octaves=4, seed=11) + 1.0 * noise.fbm(X, Z, 0, scale=15, octaves=2, seed=12)
h = 65.4 + roll * ss(106, 138, Rr) + 4.0 * ss(120, 170, Rr)
rimn = Rr + 16 * noise.fbm(X, Z, 0, scale=90, octaves=3, seed=21)
m = ss(160, 210, rimn)
def adiff(a0): return np.abs(np.arctan2(np.sin(TH - a0), np.cos(TH - a0)))
m = m * (1 - 0.93 * np.exp(-(adiff(math.pi / 2) / 0.11) ** 2))      # south pass
ridge = noise.ridged(X, Z, 0, scale=76, octaves=4, seed=22)
north = np.exp(-(adiff(-math.pi / 2) / 0.75) ** 2)
h = h + m * (15 + 30 * ridge + 20 * north * (0.4 + ridge))
def pad(cx, cz, r_in, r_out, y):
    global h
    d = np.hypot(X - cx, Z - cz) + 4 * noise.fbm(X, Z, 0, scale=24, octaves=2, seed=int(abs(cx * 7 + cz)))
    w = ss(r_out, r_in, d)
    h = h * (1 - w) + y * w
pad(0, -148, 21, 46, 80)      # pagoda hill
pad(142, 6, 30, 52, 67)       # tea village
pad(-144, -4, 28, 50, 69)     # shrine
pad(100, 106, 22, 38, 66)     # zen garden
pad(-110, -108, 13, 28, 69)   # onsen
pe = 101 + 3.5 * noise.fbm(X, Z, 0, scale=22, octaves=2, seed=31)
sd_pond = np.maximum(PR - Rr, Rr - pe)
river = [(118, -118), (106, -102), (97, -85), (84, -72), (72, -62)]
stream = [(-68, 66), (-82, 78), (-90, 94), (-102, 104)]
sd_river = seg_dist(river) - (3.8 + 1.0 * noise.fbm(X, Z, 0, scale=14, seed=32))
sd_stream = seg_dist(stream) - (3.0 + 0.8 * noise.fbm(X, Z, 0, scale=14, seed=33))
sd_lake = np.hypot(X + 116, Z - 118) - (25 + 5 * noise.fbm(X, Z, 0, scale=30, octaves=2, seed=34))
sd_pool = np.hypot(X - 121, Z + 121) - (11 + 2.5 * noise.fbm(X, Z, 0, scale=12, seed=35))
sd = np.minimum.reduce([sd_pond, sd_river, sd_stream, sd_lake, sd_pool])
water = sd < 0
w = ss(0, 9, sd)
h = np.where(sd >= 0, 64.0 * (1 - w) + np.maximum(h, 64.0) * w, h)
isl = np.hypot(X + 118, Z - 120) + 2 * noise.fbm(X, Z, 0, scale=9, seed=36)
h = np.where(isl < 8.5, 65.0, h); water &= ~(isl < 8.5)
pisl = np.full(X.shape, 1e9)
for (ix, iz, ir) in ((63, 63, 5.6), (-63, 63, 5.0), (-63, -63, 5.8), (63, -63, 4.8)):
    pisl = np.minimum(pisl, np.hypot(X - ix, Z - iz) - ir + 1.2 * noise.fbm(X, Z, 0, scale=6, seed=37))
h = np.where(pisl < 0, 64.0, h); water &= ~(pisl < 0)
h = np.where(Rr <= PR, 64.0, h)
fo = ss(204, 216, Rr)
h = h * (1 - fo) + 58 * fo
dw = np.minimum(-sd, np.where(pisl > 0, pisl, 0) + 0.5)
floor = 62 - np.clip(np.round(dw * 0.7), 0, 4)
floor = np.where(sd_lake < 0, 62 - np.clip(np.round(-sd_lake * 0.4), 0, 5), floor)
Ht = np.where(water, floor, np.round(h)).astype(int)
inside = Rr <= N
mn = Ht.copy()
for dx in (-1, 0, 1):
    for dz in (-1, 0, 1):
        mn = np.minimum(mn, np.roll(np.roll(Ht, dx, 0), dz, 1))
Hb = np.minimum(mn - 2, Ht - 5)
slope = np.zeros_like(Ht)
for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
    slope = np.maximum(slope, np.abs(Ht - np.roll(np.roll(Ht, dx, 0), dz, 1)))
ylo, yhi = int(Hb[inside].min()), int(Ht[inside].max())
ys = np.arange(ylo, yhi + 1)
Y3 = ys[None, :, None]
body = (Y3 >= Hb[:, None, :]) & (Y3 <= Ht[:, None, :]) & inside[:, None, :]
org = (-N, ylo, -N)
def M(a): return Mask(org, a)
top3 = (Y3 == Ht[:, None, :]) & inside[:, None, :]
def col(a2): return a2[:, None, :]
rock = P.patches({"stone": 5, "andesite": 3, "tuff": 2, "cobblestone": 1, "mossy_cobblestone": 1}, size=5, seed=3)
S.put(M(body), rock)
soil = (Y3 < Ht[:, None, :]) & (Y3 >= Ht[:, None, :] - 3) & body & col(slope < 3)
S.put(M(soil), P.mix({"dirt": 5, "coarse_dirt": 1, "rooted_dirt": 1}, cluster=2, seed=4))
steep = slope >= 3
jit = 5 * noise.fbm(X, Z, 0, scale=18, octaves=2, seed=41)
snowy = (Ht + jit >= 118) & ~steep
shore = (sd >= 0) & (sd < 1.6) & ~steep & (Rr > PR) & (pisl > 0)
grassy = ~steep & ~snowy & ~water & ~shore
grass = P.patches({"grass_block": 8, "moss_block": 3}, size=7, seed=5)
S.put(M(top3 & col(grassy)), grass)
S.put(M(top3 & col(shore)), P.patches({"gravel": 3, "sand": 2, "coarse_dirt": 2, "moss_block": 2, "stone": 1}, size=3, seed=6))
S.put(M(top3 & col(snowy)), P.patches({"snow_block": 6, "calcite": 2, "white_concrete_powder": 1}, size=4, seed=7))
S.put(M(top3 & col((slope == 2) & ~water & ~snowy)), P.patches({"moss_block": 3, "mossy_cobblestone": 2, "stone": 2, "grass_block": 3}, size=3, seed=8))
S.put(M(top3 & col(water)), P.patches({"gravel": 3, "clay": 2, "sand": 2, "mud": 1, "smooth_basalt": 1}, size=3, seed=9))
wat = (Y3 > Ht[:, None, :]) & (Y3 <= 63) & col(water & inside)
S.put(M(wat), "water")
S.set_biome((-N, ylo, -N, N, yhi + 100, N), "cherry_grove")
np.savez("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz", Ht=Ht, sd=sd, water=water, slope=slope,
         sd_pond=sd_pond, sd_lake=sd_lake, sd_river=sd_river, sd_stream=sd_stream, sd_pool=sd_pool, pisl=pisl)
print("y range", ylo, yhi, "blocks", int(body.sum()), "water cols", int(water.sum()))
for nm, (cx, cz) in {"pagoda": (0, -148), "village": (142, 6), "shrine": (-144, -4), "zen": (100, 106), "onsen": (-110, -108), "south": (0, 150), "s190": (0, 190)}.items():
    print(nm, int(Ht[cx + N, cz + N]))
