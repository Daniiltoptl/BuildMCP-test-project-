import math
# Compact antique hub on a floating island (~62 x 60). Spawn on a raised terrace in the south looking
# north across a forum (mosaic paving, a low fountain) at a Roman temple; the one NPC stands in the
# temple portico, framed by the two middle columns and the lit doorway behind it. A market stoa on the
# left, a green pergola garden on the right, palms and cypresses, red shade sails.
isl = terrain.island((0, 80, -4), (31, 29), top_y=80, hill=1.6, roughness=0.3, flat_center=0.62, rim=4.0,
                     spikes=5, seed=7)
mark("spawn", (0.5, 83, 16.5), "spawn", yaw=180, pitch=-6)
mark("anchor", (0, 83, 16), "anchor")
print(S.bbox(), isl.surface.count)