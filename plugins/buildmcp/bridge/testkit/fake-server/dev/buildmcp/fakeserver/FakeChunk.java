package dev.buildmcp.fakeserver;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.bukkit.Chunk;
import org.bukkit.ChunkSnapshot;
import org.bukkit.NamespacedKey;
import org.bukkit.World;
import org.bukkit.block.Biome;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.BlockData;
import org.bukkit.plugin.Plugin;

record FakeChunk(FakeWorld world, int x, int z) implements Chunk {
    @Override
    public int getX() {
        return x;
    }

    @Override
    public int getZ() {
        return z;
    }

    @Override
    public World getWorld() {
        return world;
    }

    @Override
    public ChunkSnapshot getChunkSnapshot(boolean includeMaxblocky, boolean includeBiome, boolean includeBiomeTempRain) {
        FakeWorld.FakeData d = world.access(x << 4, z << 4);
        world.server.stats.snapshots++;
        Map<Long, String> bio = null;
        if (includeBiome) {
            bio = new HashMap<>();
            for (int qy = world.minY >> 2; qy < world.maxY >> 2; qy++) {
                for (int qz = 0; qz < 4; qz++) {
                    for (int qx = 0; qx < 4; qx++) {
                        int bx = (x << 4) + qx * 4, bz = (z << 4) + qz * 4;
                        bio.put(((long) qy << 8) | ((long) qz << 4) | qx, world.biome(bx, qy * 4, bz));
                    }
                }
            }
        }
        return new Snapshot(world, x, z, d.blocks.clone(), bio);
    }

    @Override
    public BlockState[] getTileEntities() {
        FakeWorld.FakeData d = world.access(x << 4, z << 4);
        List<BlockState> out = new ArrayList<>();
        for (int i : d.tiles.keySet()) {
            int lx = i & 15, lz = (i >> 4) & 15, y = (i >> 8) + world.minY;
            out.add(new FakeBlockState((x << 4) + lx, y, (z << 4) + lz));
        }
        return out.toArray(new BlockState[0]);
    }

    @Override
    public boolean addPluginChunkTicket(Plugin plugin) {
        return world.addPluginChunkTicket(x, z, plugin);
    }

    @Override
    public boolean removePluginChunkTicket(Plugin plugin) {
        return world.removePluginChunkTicket(x, z, plugin);
    }

    /** Immutable copy, safe to read from any thread. */
    record Snapshot(FakeWorld world, int cx, int cz, FakeBlockData[] blocks, Map<Long, String> biomes)
            implements ChunkSnapshot {
        @Override
        public int getX() {
            return cx;
        }

        @Override
        public int getZ() {
            return cz;
        }

        @Override
        public BlockData getBlockData(int x, int y, int z) {
            if (x < 0 || x > 15 || z < 0 || z > 15) {
                throw new IllegalArgumentException("snapshot coordinates are chunk-local");
            }
            if (y < world.minY || y >= world.maxY) {
                return FakeBlockData.AIR;
            }
            FakeBlockData b = blocks[world.local(x, y, z)];
            return b == null ? FakeBlockData.AIR : b;
        }

        @Override
        public Biome getBiome(int x, int y, int z) {
            if (biomes == null) {
                throw new IllegalStateException("snapshot taken without biomes");
            }
            String k = biomes.get(((long) (y >> 2) << 8) | ((long) (z >> 2) << 4) | (x >> 2));
            return new FakeBiome(NamespacedKey.fromString(k == null ? "minecraft:plains" : k));
        }
    }
}
