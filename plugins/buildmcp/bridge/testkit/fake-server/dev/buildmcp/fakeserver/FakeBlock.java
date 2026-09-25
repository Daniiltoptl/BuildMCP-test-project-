package dev.buildmcp.fakeserver;

import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.data.BlockData;

record FakeBlock(FakeWorld world, int x, int y, int z) implements Block {
    @Override
    public int getX() {
        return x;
    }

    @Override
    public int getY() {
        return y;
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
    public BlockData getBlockData() {
        return world.get(x, y, z);
    }

    @Override
    public void setBlockData(BlockData data, boolean applyPhysics) {
        if (applyPhysics) {
            world.server.stats.physicsPlacements++;
        }
        world.set(x, y, z, (FakeBlockData) data);
    }
}
