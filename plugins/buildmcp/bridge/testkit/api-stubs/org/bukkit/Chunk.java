package org.bukkit;

import org.bukkit.block.BlockState;
import org.bukkit.plugin.Plugin;

public interface Chunk {
    int getX();

    int getZ();

    World getWorld();

    ChunkSnapshot getChunkSnapshot(boolean includeMaxblocky, boolean includeBiome, boolean includeBiomeTempRain);

    BlockState[] getTileEntities();

    boolean addPluginChunkTicket(Plugin plugin);

    boolean removePluginChunkTicket(Plugin plugin);
}
