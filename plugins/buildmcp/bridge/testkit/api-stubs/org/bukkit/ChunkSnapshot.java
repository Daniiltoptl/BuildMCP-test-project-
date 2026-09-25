package org.bukkit;

import org.bukkit.block.Biome;
import org.bukkit.block.data.BlockData;

public interface ChunkSnapshot {
    int getX();

    int getZ();

    BlockData getBlockData(int x, int y, int z);

    Biome getBiome(int x, int y, int z);
}
