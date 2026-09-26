import math
# Northern outpost on a floating island. Spawn on a stone platform in the south looking north along
# a snowy road at a longhouse (gable end towards the spawn); a watchtower rises behind its right
# shoulder (a tower straight behind the steep roof would be hidden); the two portals flank the yard.
isl = terrain.island((0, 80, -2), (28, 26), top_y=80, hill=2.5, roughness=0.35, flat_center=0.5, rim=4.0,
                     spikes=5, seed=41)
mark("spawn", (0, 82, 19), "spawn", yaw=180, pitch=-16)
mark("anchor", (0, 82, 19), "anchor")
mark("longhouse", (0, 81, -12), "point")
portals = {"survival": ((-17, 81, -4), "east", "Выживание", "light_blue"),
           "hardcore": ((17, 81, -4), "west", "Хардкор", "white")}
yaw_of = {"south": 0, "west": 90, "north": 180, "east": 270}
for name, (pos, facing, _, _) in portals.items():
    mark(name, pos, "portal", yaw=yaw_of[facing])

# yard in front of the longhouse, the road from the platform and side paths to the portals
road = P.patches({"stone_bricks": 3, "cobblestone": 2, "andesite": 1, "snow_block": 1.5, "packed_ice": 0.3},
                 size=2, seed=4)  # snow-dusted stone, no dirt on the snow
paths.plaza((0, 80, -1), radius=6.5, pattern="rings", seed=2)
paths.path([(0, 80, 16), (0, 80, 8), (0, 80, 3)], width=5, palette=road, edge="snow_block", seed=3)
for name, ((x, y, z), facing, label, color) in portals.items():
    sx = -5 if x < 0 else 5
    paths.path([(sx, 80, -2), ((sx + x) / 2, 80, -3), (x, 80, z)], width=3, palette=road, edge="snow_block",
               seed=len(name))

# hero: the watchtower behind the longhouse's right shoulder (~13 degrees right of the axis from the spawn)
timber = P.patches({"spruce_planks": 3, "stripped_spruce_wood": 2, "spruce_wood": 0.8}, size=2, seed=6)
arch.tower((10, 80, -21), radius=4, height=22, shape="square", roof="cone", band_every=6, material=timber, seed=7)
arch.house((-6, 81, -19, 6, 86, -7), roof_style="nordic", door_side="south", chimney=True, seed=4)
for name, ((x, y, z), facing, label, color) in portals.items():
    props.portal_frame((x, 80, z), facing=facing, width=5, height=7, label=label, color=color,
                       subtitle="Нажми, чтобы играть")
print(S.bbox())