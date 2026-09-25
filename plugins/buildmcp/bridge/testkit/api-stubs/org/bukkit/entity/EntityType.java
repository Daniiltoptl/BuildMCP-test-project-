package org.bukkit.entity;

import org.bukkit.Keyed;
import org.bukkit.NamespacedKey;

public enum EntityType implements Keyed {
    TEXT_DISPLAY("text_display"), BLOCK_DISPLAY("block_display"), ITEM_DISPLAY("item_display"),
    INTERACTION("interaction"), ARMOR_STAND("armor_stand"), ITEM_FRAME("item_frame"),
    GLOW_ITEM_FRAME("glow_item_frame"), PAINTING("painting"), MARKER("marker"), PLAYER("player"),
    UNKNOWN("unknown");

    private final String name;

    EntityType(String name) {
        this.name = name;
    }

    @Override
    public NamespacedKey getKey() {
        return NamespacedKey.minecraft(name);
    }

    public static EntityType fromName(String n) {
        String k = n.startsWith("minecraft:") ? n.substring(10) : n;
        for (EntityType t : values()) {
            if (t.name.equals(k)) {
                return t;
            }
        }
        return null;
    }
}
