import math
# remove the misplaced first waterfall (off the island edge) and run a stream from the pond to the edge
S.clear(Box(-42, 40, 26, -34, 81, 34), only="water")
edge_x = next(x for x in range(-30, -56, -1) if S.top_y(x, 22) is None or S.top_y(x, 22) < 76) + 1
for x in range(-30, edge_x - 1, -1):
    for dz in (0, 1):
        S.set(x, 79, 22 + dz, "water")
        S.set(x, 78, 22 + dz, "mossy_cobblestone")
        S.clear((x, 80, 22 + dz, x, 82, 22 + dz), only="#plants")
terrain.waterfall((edge_x - 1, 79, 22), direction="west", width=2, drop=38)

# lamp posts: along the main axis and the portal paths (portals and the terrace have their own lanterns)
lamps = [(-4, 31), (3, 35), (-4, -18), (4, -18)]
for name in ("survival", "skyblock", "pvp", "anarchy"):
    x, y, z = (int(v) for v in S.markers[name].pos)
    ang = math.atan2(z, x)
    mid = (x * 0.62, z * 0.62 + 1)
    lamps.append((round(mid[0] + math.cos(ang + math.pi / 2) * 3.2), round(mid[1] + math.sin(ang + math.pi / 2) * 3.2)))
for lx, lz in lamps:
    props.lamp_post((lx, 80, lz), height=4)

# benches around the fountain facing it, flower planters between them
for k in range(8):
    a = math.radians(22.5 + k * 45)
    bx, bz = round(math.cos(a) * 9.5), round(math.sin(a) * 9.5)
    if k in (1, 2, 5, 6):
        facing = "north" if bz > 0 else "south"
        if abs(bx) > abs(bz):
            facing = "west" if bx > 0 else "east"
        props.bench((bx, 80, bz), facing=facing, length=3)
    else:
        props.planter((bx - 1, 80, bz - 1), size=3)

# mode banners on poles beside each portal
colors = {"survival": "lime", "skyblock": "light_blue", "pvp": "red", "anarchy": "purple"}
for name, col in colors.items():
    x, y, z = (int(v) for v in S.markers[name].pos)
    facing = {0: "south", 90: "west", 180: "north", 270: "east"}[int(S.markers[name].yaw) % 360]
    dx, dz = {"south": (1, 0), "north": (1, 0), "east": (0, 1), "west": (0, 1)}[facing]
    for side in (-1, 1):
        props.banner_pole((x + dx * 7 * side, 80, z + dz * 7 * side), color=col, height=6, facing=facing)