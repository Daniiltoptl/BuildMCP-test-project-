hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz"); Ht = hm["Ht"]; N = 216
RED="red_nether_bricks"; DT="deepslate_tiles"; DSL="deepslate_tile_slab"
rg = np.random.default_rng(9)
TOPY = 81                      # terrace surface block
cz = -148
# terrace
SB = P.mix({"stone_bricks": 6, "mossy_stone_bricks": 2, "cracked_stone_bricks": 1, "andesite": 1}, cluster=2, seed=2)
PAVE = P.mix({"polished_andesite": 4, "stone_bricks": 3, "polished_deepslate": 1}, cluster=2, seed=3)
S.fill((-17, 74, cz - 17, 17, TOPY, cz + 17), SB)
S.fill((-16, TOPY, cz - 16, 16, TOPY, cz + 16), PAVE)
S.fill((-17, TOPY + 1, cz - 17, 17, TOPY + 12, cz + 17), "air")
for x in range(-17, 18):
    for z in (cz - 17, cz + 17):
        if abs(x) <= 4 and z == cz + 17: continue
        S.set(x, TOPY + 1, z, "polished_blackstone_brick_wall" if x % 4 else "polished_blackstone_bricks")
        if x % 4 == 0: S.set(x, TOPY + 2, z, "polished_blackstone_brick_wall")
        S.set(z - cz, TOPY + 1, cz + x, "polished_blackstone_brick_wall" if x % 4 else "polished_blackstone_bricks")
        if x % 4 == 0: S.set(z - cz, TOPY + 2, cz + x, "polished_blackstone_brick_wall")
for sx in (-1, 1):
    for sz in (-1, 1):
        x, z = sx * 17, cz + sz * 17
        S.fill((x, TOPY + 1, z, x, TOPY + 3, z), "polished_blackstone_bricks"); S.set(x, TOPY + 4, z, "ochre_froglight")
        S.set(x, TOPY + 5, z, f"{DSL}[type=bottom]")
arch.pagoda((0, TOPY + 1, cz), tiers=5, base=21, tier_height=6, seed=3)
# open the south door of the pagoda
S.fill((-1, TOPY + 1, cz + 10, 1, TOPY + 3, cz + 10), "air")
S.fill((-2, TOPY + 1, cz + 10, -2, TOPY + 4, cz + 10), RED); S.fill((2, TOPY + 1, cz + 10, 2, TOPY + 4, cz + 10), RED)
S.fill((-2, TOPY + 4, cz + 10, 2, TOPY + 4, cz + 10), RED)
for x in (-6, 6):
    S.set(x, TOPY + 1, cz + 5, "light[level=14]")
# staircase with landings, from the avenue up to the terrace
z = -108; y = int(Ht[0 + N, z + N])
S.fill((-5, y - 1, z, 5, y, z), SB)
run = 0
steps = []
while y < TOPY:
    z -= 1
    if run == 6 and TOPY - y > 2:
        for k in range(3): steps.append((z - k, y, False))
        z -= 2; run = 0; continue
    y += 1; run += 1; steps.append((z, y, True))
zt = z
for (zz, yy, st) in steps:
    S.fill((-5, yy + 1, zz, 5, yy + 9, zz), "air")
    for x in range(-5, 6):
        g = int(Ht[x + N, zz + N])
        S.fill((x, min(g, yy) - 2, zz, x, yy, zz), SB)
    if st:
        S.fill((-4, yy, zz, 4, yy, zz), "stone_brick_stairs[facing=north,half=bottom]")
        for x in range(-4, 5):
            if rg.random() < 0.2: S.set(x, yy, zz, "mossy_stone_brick_stairs[facing=north,half=bottom]")
    for x in (-5, 5):
        S.set(x, yy + 1, zz, "polished_blackstone_brick_wall")
# join to the terrace
S.fill((-5, TOPY + 1, zt - 1, 5, TOPY + 9, cz + 17), "air")
S.fill((-5, TOPY - 3, zt - 1, 5, TOPY, cz + 17), SB)
# senbon torii over the stairs
for i, (zz, yy, st) in enumerate(steps):
    if i % 2: continue
    for x in (-4, 4):
        S.fill((x, yy + 1, zz, x, yy + 6, zz), RED)
    S.fill((-5, yy + 6, zz, 5, yy + 6, zz), RED)
    S.fill((-6, yy + 8, zz, 6, yy + 8, zz), RED)
    S.fill((-4, yy + 7, zz, -4, yy + 7, zz), RED); S.fill((4, yy + 7, zz, 4, yy + 7, zz), RED); S.set(0, yy + 7, zz, "gilded_blackstone")
    S.fill((-7, yy + 9, zz, 7, yy + 9, zz), f"{DSL}[type=bottom]")
    if i % 6 == 0:
        S.set(0, yy + 5, zz, "chain[axis=y]"); S.set(0, yy + 4, zz, "ochre_froglight")
print("stairs", len(steps), "from z=-109 to", zt, "y", y, "top", S.bbox())
mark("pagoda", (0, TOPY + 1, cz + 14), "warp", yaw=180)
