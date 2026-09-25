package org.bukkit;

import java.util.Collection;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import org.bukkit.block.Block;
import org.bukkit.entity.Entity;
import org.bukkit.plugin.Plugin;
import org.bukkit.util.BoundingBox;

public interface World extends Keyed {
    String getName();

    UUID getUID();

    Environment getEnvironment();

    int getMinHeight();

    int getMaxHeight();

    Location getSpawnLocation();

    Block getBlockAt(int x, int y, int z);

    Chunk getChunkAt(int x, int z);

    boolean isChunkLoaded(int x, int z);

    default CompletableFuture<Chunk> getChunkAtAsync(int x, int z, boolean gen) {
        throw new UnsupportedOperationException();
    }

    boolean addPluginChunkTicket(int x, int z, Plugin plugin);

    boolean removePluginChunkTicket(int x, int z, Plugin plugin);

    int getHighestBlockYAt(int x, int z, HeightMap heightMap);

    Collection<Entity> getNearbyEntities(BoundingBox boundingBox);

    enum Environment {
        NORMAL, NETHER, THE_END, CUSTOM
    }
}
