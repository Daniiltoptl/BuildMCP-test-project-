import math
# Hub on a floating island: plaza at the origin, spawn on the south edge looking north at the
# tower; four mode portals on a semicircle in front of the tower (all visible from the spawn).
mark("spawn", (0, 81, 15), "spawn", yaw=180, pitch=-8)
mark("anchor", (0, 81, 15), "anchor")
mark("plaza", (0, 81, 0), "point")
mark("tower", (0, 81, -32), "point")
portals = [("survival", (-28, 81, -2), "east"), ("skyblock", (-15, 81, -25), "south"),
           ("pvp", (15, 81, -25), "south"), ("anarchy", (28, 81, -2), "west")]
yaw_of = {"south": 0, "west": 90, "north": 180, "east": 270}
for name, pos, facing in portals:
    mark(name, pos, "portal", yaw=yaw_of[facing])
mark("view_gate", (0, 88, 38), "viewpoint", yaw=180, pitch=-5)
mark("view_tower", (-34, 96, 22), "viewpoint", yaw=215, pitch=-12)
# temporary zone blocks to check the layout from above
S.fill((-1, 79, -1, 1, 79, 1), "gold_block")
for name, pos, facing in portals:
    x, y, z = pos
    S.fill((x - 2, 79, z - 2, x + 2, 79, z + 2), "red_concrete")
S.fill((-6, 79, -38, 6, 79, -26), "blue_concrete")
print("markers:", list(S.markers))