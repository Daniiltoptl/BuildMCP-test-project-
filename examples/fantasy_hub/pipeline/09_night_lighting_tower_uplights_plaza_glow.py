import math
# wash the tower with light from hidden sources around its base and under the balcony
for k in range(8):
    a = 2 * math.pi * k / 8
    x, z = round(math.cos(a) * 10.5), round(-32 + math.sin(a) * 10.5)
    y = (S.top_y(x, z) or 80) + 1
    if S.get(x, y, z) == "minecraft:air":
        S.set(x, y, z, "light[level=12]")
for k in range(6):
    a = 2 * math.pi * k / 6 + 0.3
    x, z = round(math.cos(a) * 9.5), round(-32 + math.sin(a) * 9.5)
    if S.get(x, 98, z) == "minecraft:air":
        S.set(x, 98, z, "light[level=11]")
# soft light over the plaza and the portal pads (invisible light blocks, walkable)
for x, z in [(-7, -7), (7, -7), (-7, 7), (7, 7), (0, -11), (-11, 0), (11, 0)]:
    S.set(x, 82, z, "light[level=10]")
for name in ("survival", "skyblock", "pvp", "anarchy"):
    x, y, z = (int(v) for v in S.markers[name].pos)
    ang = math.atan2(z, x)
    lx, lz = round(x - math.cos(ang) * 4), round(z - math.sin(ang) * 4)
    S.set(lx, 82, lz, "light[level=11]")
# warm light around the logo so it reads at night too
for x in range(-22, 23, 11):
    S.set(x, 140, -30, "light[level=13]")
finalize()