r = arch.temple((0, 80, -5), facing="south", width=15, depth=21, podium=3, column_h=8, seed=3)
nx, ny, nz = r["npc"]
mark("npc", (nx, ny, nz), "npc", yaw=0)
# foundation: the back of the podium stands on the rim slope, fill down to the rock
b = r["box"]
for x in range(b.x1, b.x2 + 1):
    for z in range(b.z1, b.z2 + 1):
        if S.get(x, 81, z) != "minecraft:air":
            y = 80
            while y > 60 and S.get(x, y, z) == "minecraft:air":
                S.put((x, y, z), T.wall_base)
                y -= 1
print(r)