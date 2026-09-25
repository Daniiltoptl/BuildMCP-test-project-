package org.bukkit.block;

import org.bukkit.World;
import org.bukkit.block.data.BlockData;

public interface Block {
    int getX();

    int getY();

    int getZ();

    World getWorld();

    BlockData getBlockData();

    void setBlockData(BlockData data, boolean applyPhysics);
}
