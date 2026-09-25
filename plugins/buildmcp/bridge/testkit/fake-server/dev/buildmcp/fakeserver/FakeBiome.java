package dev.buildmcp.fakeserver;

import org.bukkit.NamespacedKey;
import org.bukkit.block.Biome;

record FakeBiome(NamespacedKey key) implements Biome {
    @Override
    public NamespacedKey getKey() {
        return key;
    }
}
