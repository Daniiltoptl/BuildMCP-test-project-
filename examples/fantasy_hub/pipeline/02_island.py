S.clear((-40, 79, -40, 40, 79, 5))  # remove the layout helper blocks
isl = terrain.island((0, 80, -8), (50, 47), top_y=80, hill=2.5, roughness=0.3, flat_center=0.62, rim=4.5,
                     spikes=5, seed=11)
print(S.bbox(), isl.surface.count)