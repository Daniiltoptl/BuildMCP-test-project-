hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz")
Ht, water, sd = hm["Ht"], hm["water"], hm["sd"]
N = 216
DT="deepslate_tiles"; DSL="deepslate_tile_slab"; RED="red_nether_bricks"
def gy(x, z): return int(S.top_y(int(round(x)), int(round(z))) or Ht[int(round(x)) + N, int(round(z)) + N])
def sdv(x, z): return float(sd[int(round(x)) + N, int(round(z)) + N])
GRAV = P.mix({"gravel": 5, "dead_tube_coral_block": 2, "andesite": 2, "stone": 1, "cobblestone": 1}, cluster=2, seed=3)
EDGE = P.mix({"coarse_dirt": 2, "mossy_cobblestone": 2, "moss_block": 2, "rooted_dirt": 1}, seed=4)
PAVE = P.mix({"stone_bricks": 5, "polished_andesite": 3, "cracked_stone_bricks": 1, "mossy_stone_bricks": 1, "andesite": 1}, cluster=2, seed=5)
allpaths = []
def trail(pts, width=3.2, pal=GRAV):
    p3 = [(x, gy(x, z), z) for (x, z) in pts]
    paths.path(p3, width=width, palette=pal, edge=EDGE, edge_width=1.0, seed=len(allpaths))
    allpaths.append(pts)
# ring walk, split at water crossings
ring = []
for k in range(0, 361, 5):
    a = math.radians(k); rr = 112 + 2.5 * math.sin(3 * a)
    ring.append((rr * math.cos(a), rr * math.sin(a)))
seg = []; gaps = []; last_land = None; in_gap = False
for p in ring:
    if sdv(*p) < 3.0:
        if seg and len(seg) > 1: trail(seg, 4.0)
        if not in_gap: gaps.append([last_land, None]); in_gap = True
        seg = []
    else:
        if in_gap: gaps[-1][1] = p; in_gap = False; seg = [p] 
        else: seg.append(p)
        last_land = p
if len(seg) > 1: trail(seg, 4.0)
for a, b in gaps:
    if a is None or b is None: continue
    A = (int(round(a[0])), gy(*a), int(round(a[1]))); B = (int(round(b[0])), gy(*b), int(round(b[1])))
    paths.bridge(A, B, width=3, style="asian", arch=2.0)
    print("ring bridge", A, B)
# garden trails
trail([(79, 79), (86, 88), (92, 97)])                       # zen garden
trail([(-66, 91), (-78, 100), (-88, 111)])                  # lake
trail([(-79, -79), (-90, -90), (-100, -99)])                # onsen
trail([(72, -86), (86, -99), (100, -112)])                  # waterfall
trail([(112, 0), (118, 3)], 4.0); trail([(-112, 0), (-118, -2)], 4.0)
# landings at the stone routes / bridges
# south avenue
trail([(0, 103), (0, 125), (0, 150), (0, 172), (0, 184)], 7.5, PAVE)
trail([(0, -101), (0, -108)], 7.5, PAVE)
for z in (116, 136, 156):
    arch.torii((0, gy(0, z), z), "south", width=11, height=11)
# mountain gate (romon) at the south pass
def gate(cz):
    y = gy(0, cz)
    S.fill((-9, y - 2, cz - 3, 9, y, cz + 3), PAVE)
    for sx in (-1, 1):
        for x in (4, 8):
            for z in (cz - 2, cz + 2):
                S.fill((sx * x, y + 1, z, sx * x, y + 7, z), RED)
                S.set(sx * x, y + 1, z, "polished_blackstone_bricks")
        S.fill((sx * 5, y + 1, cz - 2, sx * 7, y + 7, cz + 2), "white_terracotta" if False else "smooth_quartz")
        S.fill((sx * 5, y + 1, cz - 2, sx * 7, y + 2, cz + 2), "polished_blackstone_bricks")
        S.fill((sx * 6, y + 4, cz - 2, sx * 6, y + 5, cz + 2), "dark_oak_trapdoor[facing=north,open=true,half=bottom]")
        S.set(sx * 6, y + 4, cz, "ochre_froglight"); S.set(sx * 6, y + 5, cz, "ochre_froglight")
    S.fill((-9, y + 8, cz - 3, 9, y + 8, cz + 3), RED)
    S.fill((-8, y + 8, cz - 2, 8, y + 8, cz + 2), "dark_oak_planks")
    arch.roof((-9, y + 1, cz - 3, 9, y + 8, cz + 3), style="asian", material="deepslate_tiles", overhang=2, pitch=0.5, gable_fill=RED) if False else None
    # lower skirt roof
    for d, yy in ((4, y + 9), (5, y + 8)):
        pass
    S.fill((-8, y + 9, cz - 2, 8, y + 12, cz + 2), "smooth_quartz")
    for x in (-8, -4, 0, 4, 8):
        S.fill((x, y + 9, cz - 2, x, y + 12, cz - 2), RED); S.fill((x, y + 9, cz + 2, x, y + 12, cz + 2), RED)
    S.fill((-8, y + 12, cz - 2, 8, y + 12, cz + 2), RED)
    S.fill((-7, y + 10, cz - 1, 7, y + 11, cz + 1), "air")
    for x in (-6, -2, 2, 6): S.set(x, y + 10, cz, "light[level=14]")
    S.fill((-10, y + 9, cz - 4, 10, y + 9, cz + 4), f"{DSL}[type=bottom]", only="air")
    S.fill((-11, y + 9, cz - 5, 11, y + 9, cz + 5), f"{DSL}[type=bottom]", only="air")
    arch.roof((-8, y + 9, cz - 2, 8, y + 12, cz + 2), style="asian", material="deepslate_tiles", overhang=3, pitch=0.7)
    for sx in (-1, 1):
        for z in (cz - 4, cz + 4):
            S.set(sx * 3, y + 7, z, "chain[axis=y]"); S.set(sx * 3, y + 6, z, "ochre_froglight")
            S.set(sx * 3, y + 8, z, "chain[axis=y]")
gate(188)
# stone lanterns along the trails
def toro(x, z):
    y = gy(x, z) + 1
    S.set(x,y,z,"chiseled_polished_blackstone"); S.set(x,y+1,z,"polished_blackstone_wall")
    S.set(x,y+2,z,"polished_blackstone_slab[type=top]"); S.set(x,y+3,z,"ochre_froglight")
    for f,(dx,dz) in (("north",(0,-1)),("south",(0,1)),("west",(-1,0)),("east",(1,0))):
        S.set(x+dx,y+3,z+dz,f"dark_oak_trapdoor[facing={f},open=true,half=bottom]")
    S.fill((x-1,y+4,z-1,x+1,y+4,z+1), f"{DSL}[type=bottom]"); S.set(x,y+4,z,DT); S.set(x,y+5,z,"polished_blackstone_wall")
placed = []
def light_line(pts, off, every=10.0):
    acc = every / 2; side = 1
    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, z1 - z0)
        if L < 1e-6: continue
        ux, uz = (x1 - x0) / L, (z1 - z0) / L
        t = 0.0
        while t < L:
            acc += 1.0; t += 1.0
            if acc >= every:
                acc = 0
                x = int(round(x0 + ux * t - uz * off * side)); z = int(round(z0 + uz * t + ux * off * side)); side = -side
                if sdv(x, z) < 2.5 or math.hypot(x, z) < 104: continue
                if any((x - a) ** 2 + (z - b) ** 2 < 36 for a, b in placed): continue
                hs = [gy(x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)]
                if max(hs) - min(hs) > 1: continue
                toro(x, z); placed.append((x, z))
for pts in allpaths:
    wide = abs(pts[0][0]) < 1 and abs(pts[-1][0]) < 1
    light_line(pts, 5.5 if wide else 3.2, 8.0 if wide else 11.0)
if True:
    for z in (106, 114, 124, 144, 164, 176):
        for x in (-6, 6):
            if (x, z) not in placed and all((x - a) ** 2 + (z - b) ** 2 >= 25 for a, b in placed): toro(x, z); placed.append((x, z))
np.save("/home/user/BuildMCP-test-project-/builds/sakura_grand/toro.npy", np.array(placed))
print("toro", len(placed), "gaps", len(gaps))
