hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_simple/hm.npz"); Ht = hm["Ht"]; N = 76
rg = np.random.default_rng(4)
def gy(x, z): return int(S.top_y(int(x), int(z)) or Ht[int(x) + N, int(z) + N])
DSL = "deepslate_tile_slab"; DT = "deepslate_tiles"
GRAV = P.mix({"gravel": 5, "andesite": 2, "coarse_dirt": 1, "stone": 1}, cluster=2, seed=3)
EDGE = P.mix({"coarse_dirt": 2, "moss_block": 2, "rooted_dirt": 1}, seed=4)
dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
for dx, dz in dirs:
    pts = []
    for r in range(25, 66, 4):
        w = 1.8 * math.sin(r / 9.0)
        x, z = dx * r - dz * w, dz * r + dx * w
        pts.append((x, gy(x, z), z))
    paths.path(pts, width=3.6, palette=GRAV, edge=EDGE, edge_width=1.0, seed=dx + 3 * dz + 5)
def toro(x, z, y=None):
    y = gy(x, z) + 1 if y is None else y
    S.set(x,y,z,"chiseled_stone_bricks"); S.set(x,y+1,z,"stone_brick_wall")
    S.set(x,y+2,z,"stone_brick_slab[type=top]"); S.set(x,y+3,z,"ochre_froglight")
    for f,(ox,oz) in (("north",(0,-1)),("south",(0,1)),("west",(-1,0)),("east",(1,0))):
        S.set(x+ox,y+3,z+oz,f"spruce_trapdoor[facing={f},open=true,half=bottom]")
    S.fill((x-1,y+4,z-1,x+1,y+4,z+1), f"{DSL}[type=bottom]"); S.set(x,y+4,z,DT); S.set(x,y+5,z,"stone_brick_wall")
# lanterns flanking each plaza entrance and along the paths
lamps = []
for dx, dz in dirs:
    for r in (24, 40, 54):
        for s in (-1, 1):
            x, z = dx * r - dz * s * 4, dz * r + dx * s * 4
            if r == 24: toro(x, z, 65)
            else: toro(x, z)
            lamps.append((x, z))
# benches on the plaza between the entrances, facing the centre
for k in range(4):
    a = math.radians(45 + 90 * k)
    cx, cz = 21 * math.cos(a), 21 * math.sin(a)
    for off in (-3, 3):
        b = a + math.radians(90)
        x, z = int(round(cx + off * math.cos(b))), int(round(cz + off * math.sin(b)))
        f = "north" if abs(math.sin(a)) > abs(math.cos(a)) and math.sin(a) > 0 else "south" if math.sin(a) < 0 else "east"
        # facing toward the centre: choose by dominant axis
        fx = "west" if math.cos(a) > 0 else "east"; fz = "north" if math.sin(a) > 0 else "south"
        props.bench((x, 64, z), facing=fz if off < 0 else fx, length=2)
# planters with small sakuras at the 4 diagonals of the plaza
for k in range(4):
    a = math.radians(45 + 90 * k)
    cx, cz = int(round(17 * math.cos(a))), int(round(17 * math.sin(a)))
    S.fill((cx-2, 65, cz-2, cx+2, 65, cz+2), "polished_blackstone_bricks")
    S.fill((cx-1, 65, cz-1, cx+1, 65, cz+1), "moss_block")
    trees.tree((cx, 65, cz), "cherry", height=9, seed=10 + k)
    S.set(cx, 66, cz - 0, S.get(cx, 66, cz))
# tree ring
gr = S.mask(["grass_block", "moss_block"])
surf = S.surface(gr, clearance=3)
def ok(x, y, z):
    x = np.asarray(x, float); z = np.asarray(z, float)
    R = np.hypot(x, z)
    good = (R > 33) & (R < 69)
    good &= ~((np.abs(x) < 6.5) & (np.abs(z) > 24)) & ~((np.abs(z) < 6.5) & (np.abs(x) > 24))
    return good
surf = surf.where(ok)
inner = surf.where(lambda x, y, z: np.hypot(x, z) < 50)
outer = surf.where(lambda x, y, z: np.hypot(x, z) >= 50)
t1 = trees.forest(inner, ["cherry"] * 5 + ["bush"], density=0.012, min_dist=8, seed=21)
t2 = trees.forest(outer, ["cherry"] * 4 + ["pine"] * 3 + ["birch"], density=0.02, min_dist=6.5, seed=22)
# a few big sakuras as focal points between the paths
nb = 0
for k in range(4):
    a = math.radians(45 + 90 * k + rg.uniform(-8, 8))
    x, z = int(round(40 * math.cos(a))), int(round(40 * math.sin(a)))
    trees.tree((x, gy(x, z), z), "cherry", height=17, seed=40 + k); nb += 1
# hidden light in the crowns
leaves = S.mask("cherry_leaves").erode(1)
glow = Mask.from_points(leaves.sample(count=400, min_dist=6, seed=5))
S.put(glow, "shroomlight")
# boulders and ground cover
for (x, y, z) in surf.sample(count=14, min_dist=18, seed=9):
    rocks.boulder((x, y, z), size=float(rg.uniform(1.2, 2.2)), seed=abs(int(x * 7 + z)))
items = {"short_grass": 8, "pink_petals[flower_amount=4]": 4, "pink_petals[flower_amount=2]": 2, "fern": 1,
         "pink_tulip": 0.5, "allium": 0.3, "azure_bluet": 0.4, "lily_of_the_valley": 0.3}
cov = S.surface(S.mask(["grass_block", "moss_block"]), clearance=1).where(lambda x, y, z: np.hypot(x, z) > 27.5)
nc = terrain.cover(cov, density=0.45, seed=3, items=items)
# petals drifting onto the plaza edge
n = 0
for _ in range(500):
    a = rg.uniform(0, 2 * math.pi); r = rg.uniform(19, 25)
    x, z = int(round(r * math.cos(a))), int(round(r * math.sin(a)))
    if str(S.get(x, 65, z)).endswith("air"):
        S.set(x, 65, z, f"pink_petals[facing={['north','east','south','west'][int(rg.integers(4))]},flower_amount={int(rg.integers(1, 4))}]"); n += 1
print("trees", len(t1), len(t2), nb, "glow", glow.count, "cover", nc, "petals", n)
