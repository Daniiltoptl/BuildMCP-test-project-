package dev.buildmcp.bridge;

import org.bukkit.Keyed;

/**
 * Namespaced ids of registry values. Going through {@link Keyed} keeps the plugin binary compatible
 * with types that changed from enums to interfaces between 1.21.x releases (Biome in 1.21.3).
 */
final class Keys {
    private Keys() {}

    static String of(Keyed k) {
        return k.getKey().toString();
    }
}
