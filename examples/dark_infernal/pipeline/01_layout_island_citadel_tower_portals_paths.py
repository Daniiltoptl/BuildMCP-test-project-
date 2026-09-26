import math
# Infernal citadel on a floating island. Spawn on a blackstone platform in the south, looking north
# up a processional way of blackstone bricks at the citadel; the PvP and Anarchy portals flank the
# forecourt (both in view from the spawn).
isl = terrain.island((0, 80, -2), (28, 26), top_y=80, hill=2.5, roughness=0.35, flat_center=0.5, rim=4.0,
                     spikes=5, seed=31)
mark("spawn", (0, 82, 19), "spawn", yaw=180, pitch=-16)
mark("anchor", (0, 82, 19), "anchor")
mark("citadel", (0, 81, -14), "point")
portals = {"pvp": ((-17, 81, -6), "east", "PvP", "red"), "anarchy": ((17, 81, -6), "west", "Анархия", "purple")}
yaw_of = {"south": 0, "west": 90, "north": 180, "east": 270}
for name, (pos, facing, _, _) in portals.items():
    mark(name, pos, "portal", yaw=yaw_of[facing])

# forecourt of blackstone bricks, a road from the platform and side roads to the portals
paths.plaza((0, 80, -4), radius=7.5, pattern="radial", seed=2)
paths.path([(0, 80, 16), (0, 80, 8), (0, 80, 1)], width=5, palette=T.plaza, seed=3)
for name, ((x, y, z), facing, label, color) in portals.items():
    sx = -6 if x < 0 else 6
    paths.path([(sx, 80, -5), ((sx + x) / 2, 80, -6), (x, 80, z)], width=3, seed=len(name))

# hero: the citadel tower (fits the spawn view: top at ~45 degrees up from the platform)
arch.tower((0, 80, -15), radius=6, height=22, shape="octagon", roof="cone", turrets=4, balcony=14,
           band_every=6, door="south", seed=5)
for name, ((x, y, z), facing, label, color) in portals.items():
    props.portal_frame((x, 80, z), facing=facing, width=5, height=7, label=label, color=color,
                       subtitle="Нажми, чтобы играть")
print(S.bbox())