package dev.buildmcp.fakeserver;

import org.bukkit.block.BlockState;

record FakeBlockState(int x, int y, int z) implements BlockState {
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
}
