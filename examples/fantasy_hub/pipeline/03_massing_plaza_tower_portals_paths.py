import math
# hero: the mage tower north of the plaza (teal roof, gold finials, turrets, balcony, entrance to the plaza)
arch.tower((0, 80, -32), radius=7, height=30, roof="cone", roof_material="dark_prismarine", balcony=19, turrets=4,
           door="south", band_every=7, seed=3)
# mode portals on the semicircle, each facing the plaza, with its own color
modes = {"survival": ("Выживание", "lime"), "skyblock": ("SkyBlock", "light_blue"), "pvp": ("PvP", "red"),
         "anarchy": ("Анархия", "purple")}
for name, (label, color) in modes.items():
    mk = S.markers[name]
    x, y, z = (int(v) for v in mk.pos)
    facing = {0: "south", 90: "west", 180: "north", 270: "east"}[int(mk.yaw) % 360]
    props.portal_frame((x, 80, z), facing=facing, width=5, height=7, label=label, color=color,
                       subtitle="Нажми, чтобы играть")