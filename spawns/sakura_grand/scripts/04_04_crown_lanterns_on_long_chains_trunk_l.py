rg = np.random.default_rng(77)
bx = Box(-76, 69, -76, 76, 190, 76)
NA = S.mask(None, bx); LF = S.mask("cherry_leaves", bx)
e = NA.extent; ox, oy, oz = e.x1, e.y1, e.z1
na = NA.arr; lf = LF.arr
eL = LF.extent
assert (eL.x1, eL.y1, eL.z1) == (ox, oy, oz) and lf.shape == na.shape, (e, eL)
first = np.where(na.any(1), na.argmax(1), -1)          # first non-air above y=69 per column
ok = np.zeros(first.shape, bool)
ii, kk = np.nonzero(first >= 0)
ok[ii, kk] = lf[ii, first[ii, kk], kk] & (first[ii, kk] + oy >= 108)
cand = [(int(i + ox), int(k + oz), int(first[i, k] + oy)) for i, k in zip(*np.nonzero(ok))]
rg.shuffle(cand)
chosen = []
for (x, z, yl) in cand:
    r_ = math.hypot(x, z)
    if r_ > 73 or r_ < 21: continue
    if all((x - a) ** 2 + (z - b) ** 2 >= 9.5 ** 2 for a, b, _ in chosen): chosen.append((x, z, yl))
n = 0
for (x, z, yl) in chosen:
    r_ = math.hypot(x, z)
    yb = int(rg.integers(79, 97)) if r_ > 38 else int(rg.integers(86, 100))
    S.fill((x, yb + 2, z, x, yl - 1, z), "chain[axis=y]")
    S.set(x, yb + 2, z, "polished_blackstone_slab[type=top]")
    S.set(x, yb + 1, z, "ochre_froglight"); S.set(x, yb, z, "ochre_froglight")
    S.set(x, yb - 1, z, "red_nether_brick_wall")
    n += 1
# invisible light so the trunk and the underside of the crown are never black
nl = 0
for rad, ys_, cnt in ((15, (74, 84, 94, 104), 10), (27, (80, 96, 108), 14), (44, (88, 104), 20), (60, (86, 100), 26)):
    for y in ys_:
        for j in range(cnt):
            a = 2 * math.pi * (j + 0.5 * (y % 3)) / cnt
            x, z = int(round(rad * math.cos(a))), int(round(rad * math.sin(a)))
            if str(S.get(x, y, z)).endswith("air"):
                S.set(x, y, z, "light[level=15]"); nl += 1
# shimenawa: straw rope around the trunk with white paper streamers
WOOD = ("crimson_hyphae", "dark_oak_wood", "stripped_spruce_wood", "spruce_wood", "stripped_dark_oak_wood", "mangrove_wood")
tb = Box(-18, 86, -18, 18, 87, 18)
W = S.mask(None, tb)
rope = (W.dilate(1) - W).where(lambda x, y, z: (y >= 86) & (y <= 87))
S.put(rope, "hay_block[axis=y]")
ns = 0
for i, (x, y, z) in enumerate(sorted(map(tuple, rope.where(lambda x, y, z: y == 86).points()))):
    if abs(x) >= abs(z): dx, dz, f = (1 if x > 0 else -1), 0, ("east" if x > 0 else "west")
    else: dx, dz, f = 0, (1 if z > 0 else -1), ("south" if z > 0 else "north")
    if (x + 2 * z) % 3: continue
    p = (x + dx, 86, z + dz)
    if str(S.get(*p)).endswith("air") and str(S.get(p[0], 85, p[2])).endswith("air"):
        S.set(*p, f"white_wall_banner[facing={f}]"); ns += 1
print("lanterns", n, "lights", nl, "rope", rope.count, "streamers", ns)
