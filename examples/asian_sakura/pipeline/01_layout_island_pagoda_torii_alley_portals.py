import math
# Compact sakura garden on a floating island. Spawn on a wooden deck in the south, looking north
# through one grand torii at a four-tier pagoda; two mode portals flank the courtyard, each behind
# its own small torii (the gates tell players where the game modes are).
isl = terrain.island((0, 80, -2), (28, 26), top_y=80, hill=2.0, roughness=0.3, flat_center=0.55, rim=4.0,
                     spikes=4, seed=21)
mark("spawn", (0, 82, 19), "spawn", yaw=180, pitch=-16)
mark("anchor", (0, 82, 19), "anchor")
mark("pagoda", (0, 81, -15), "point")
portals = {"survival": ((-17, 81, -6), "east", "Выживание", "lime"),
           "minigames": ((17, 81, -6), "west", "Мини-игры", "pink")}
yaw_of = {"south": 0, "west": 90, "north": 180, "east": 270}
for name, (pos, facing, _, _) in portals.items():
    mark(name, pos, "portal", yaw=yaw_of[facing])

# gravel courtyard in front of the pagoda, the alley from the deck and side paths to the portals
gravel = P.patches({"gravel": 6, "andesite": 1.2, "tuff": 0.8}, size=3, seed=4)  # raked gravel, no dirt spots
mossy = P.patches({"moss_block": 2, "grass_block": 3}, size=2, seed=5)
paths.plaza((0, 80, -4), radius=7.5, pattern="rings", seed=2)
paths.path([(0, 80, 16), (0, 80, 8), (0, 80, 1)], width=5, palette=gravel, edge=mossy, seed=3)
for name, ((x, y, z), facing, label, color) in portals.items():
    sx = -6 if x < 0 else 6
    paths.path([(sx, 80, -5), ((sx + x) / 2, 80, -6), (x, 80, z)], width=3, palette=gravel, edge=mossy,
               seed=len(name))

# hero: the pagoda at the end of the axis, framed from the spawn by a grand torii
arch.pagoda((0, 80, -16), tiers=4, base=11, tier_height=5, seed=3)
arch.torii((0, 80, 11), facing="south", width=9, height=11)  # beam above the pagoda top from the spawn
# small torii at the start of each portal path, then the portal
for name, ((x, y, z), facing, label, color) in portals.items():
    arch.torii((round(x * 0.55), 80, z), facing=facing, width=5, height=6)
    props.portal_frame((x, 80, z), facing=facing, width=5, height=7, label=label, color=color,
                       subtitle="Нажми, чтобы играть")
print(S.bbox(), "surface", isl.surface.count)