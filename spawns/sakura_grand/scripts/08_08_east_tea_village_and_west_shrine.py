hm = np.load("/home/user/BuildMCP-test-project-/builds/sakura_grand/hm.npz"); Ht = hm["Ht"]; N = 216
RED="red_nether_bricks"; DT="deepslate_tiles"; DSL="deepslate_tile_slab"
PAVE = P.mix({"stone_bricks": 5, "polished_andesite": 3, "cracked_stone_bricks": 1, "mossy_stone_bricks": 1, "andesite": 1}, cluster=2, seed=5)
GRAV = P.mix({"gravel": 5, "dead_tube_coral_block": 2, "andesite": 2, "stone": 1}, cluster=2, seed=3)
def toro(x, z, y):
    S.set(x,y,z,"chiseled_polished_blackstone"); S.set(x,y+1,z,"polished_blackstone_wall")
    S.set(x,y+2,z,"polished_blackstone_slab[type=top]"); S.set(x,y+3,z,"ochre_froglight")
    for f,(dx,dz) in (("north",(0,-1)),("south",(0,1)),("west",(-1,0)),("east",(1,0))):
        S.set(x+dx,y+3,z+dz,f"dark_oak_trapdoor[facing={f},open=true,half=bottom]")
    S.fill((x-1,y+4,z-1,x+1,y+4,z+1), f"{DSL}[type=bottom]"); S.set(x,y+4,z,DT); S.set(x,y+5,z,"polished_blackstone_wall")
def flat(x1, z1, x2, z2, y, pal):
    """level a patch: fill up to y, clear above"""
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            g = int(Ht[x + N, z + N])
            if g < y: S.fill((x, g, z, x, y - 1, z), "dirt")
    S.fill((x1, y + 1, z1, x2, y + 10, z2), "air")
    S.fill((x1, y, z1, x2, y, z2), pal)
# ---------------- village (ground block y=67)
GY = 67
flat(117, 1, 146, 11, GY, PAVE)                 # main street
flat(137, -3, 147, 15, GY, PAVE)               # square
houses = [((124, -17, 135, -8), "south", 5, 1), ((143, -20, 156, -10), "south", 6, 2),
          ((152, -3, 162, 9), "west", 5, 3), ((144, 19, 156, 29), "north", 5, 4), ((123, 17, 135, 26), "north", 6, 5)]
for (x1, z1, x2, z2), side, hgt, sd_ in houses:
    flat(x1 - 2, z1 - 2, x2 + 2, z2 + 2, GY, GRAV)
    S.fill((x1 - 1, GY, z1 - 1, x2 + 1, GY, z2 + 1), "polished_blackstone_bricks")
    arch.house((x1, GY + 1, z1, x2, GY + hgt, z2), door_side=side, roof_style="asian", seed=sd_, chimney=False)
    # door path to the street/square
    mx, mz = (x1 + x2) // 2, (z1 + z2) // 2
    if side == "south": flat(mx - 1, z2 + 2, mx + 1, 1, GY, PAVE) if z2 + 2 <= 1 else None
    if side == "north": flat(mx - 1, 11, mx + 1, z1 - 2, GY, PAVE) if z1 - 2 >= 11 else None
    if side == "west": flat(147, mz - 1, x1 - 2, mz + 1, GY, PAVE)
    for dx, dz in ((x1 - 2, z1 - 2), (x2 + 2, z2 + 2)):
        pass
# market stalls and lanterns on the square
props.market_stall((139, GY + 1, -1), facing="south", color="red")
props.market_stall((145, GY + 1, 13), facing="north", color="pink")
for (x, z) in ((137, -3), (147, -3), (137, 15), (147, 15), (120, 0), (120, 12), (130, 0), (130, 12)):
    toro(x, z, GY + 1)
props.bench((141, GY + 1, 12), facing="north", length=3)
# string of paper lanterns across the street
for x in (124, 132):
    for z in (0, 12):
        S.fill((x, GY + 1, z, x, GY + 6, z), "stripped_dark_oak_log[axis=y]")
    S.fill((x, GY + 6, 0, x, GY + 6, 12), "chain[axis=z]")
    S.set(x, GY + 6, 0, "stripped_dark_oak_log[axis=y]"); S.set(x, GY + 6, 12, "stripped_dark_oak_log[axis=y]")
    for z in (2, 4, 6, 8, 10):
        S.set(x, GY + 5, z, "ochre_froglight" if z % 4 == 2 else "pearlescent_froglight")
mark("village", (141, GY + 1, 6), "warp", yaw=90)
# ---------------- shrine (ground block y=69)
SY = 69
flat(-146, -16, -119, 8, SY, GRAV)             # courtyard
flat(-146, -6, -117, -2, SY, PAVE)             # sando (approach)
flat(-162, -17, -145, 9, SY, "polished_blackstone_bricks")
S.fill((-161, SY + 1, -16, -146, SY + 1, 8), PAVE)      # raised hall podium
arch.house((-160, SY + 2, -14, -148, SY + 8, 6), door_side="east", roof_style="asian", seed=11, chimney=False)
S.fill((-147, SY + 1, -6, -147, SY + 1, -2), "stone_brick_stairs[facing=west,half=bottom]")
S.fill((-146, SY + 1, -6, -146, SY + 1, -2), "air")
# offering box + rope bell
S.fill((-146, SY + 1, -5, -146, SY + 1, -3), "air")
S.set(-144, SY + 1, -4, "barrel[facing=up]"); S.set(-144, SY + 1, -5, "spruce_trapdoor[facing=north,open=true,half=bottom]"); S.set(-144, SY + 1, -3, "spruce_trapdoor[facing=south,open=true,half=bottom]")
arch.torii((-121, SY, -4), "east", width=11, height=10)
arch.torii((-133, SY, -4), "east", width=9, height=8)
for (x, z) in ((-126, -8), (-126, 0), (-138, -8), (-138, 0), (-144, -12), (-144, 4)):
    toro(x, z, SY + 1)
# low wall around the courtyard
for x in range(-146, -118):
    for z in (-17, 9):
        S.set(x, SY + 1, z, "stone_bricks" if x % 5 == 0 else "stone_brick_wall")
        if x % 5 == 0: S.set(x, SY + 2, z, "stone_brick_wall")
for z in range(-17, 10):
    if -9 <= z <= 1: continue
    S.set(-119, SY + 1, z, "stone_bricks" if z % 5 == 0 else "stone_brick_wall")
# ema (prayer plaque) rack and omikuji
for z in range(2, 7):
    S.set(-130, SY + 1, z + 0, "dark_oak_fence"); S.set(-130, SY + 2, z, "dark_oak_fence")
    S.set(-130, SY + 3, z, "dark_oak_slab[type=bottom]")
mark("shrine", (-128, SY + 1, -4), "warp", yaw=90)
print("ok")
