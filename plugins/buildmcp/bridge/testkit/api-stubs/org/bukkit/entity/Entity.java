package org.bukkit.entity;

import java.util.Set;
import java.util.UUID;

import org.bukkit.Location;
import org.bukkit.World;

public interface Entity {
    Location getLocation();

    World getWorld();

    UUID getUniqueId();

    EntityType getType();

    Set<String> getScoreboardTags();

    boolean isValid();

    void remove();

    boolean teleport(Location location);
}
