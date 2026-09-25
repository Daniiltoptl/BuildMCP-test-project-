package dev.buildmcp.fakeserver;

import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;

class FakeEntity implements Entity {
    final FakeServer server;
    final EntityType type;
    final UUID uuid = UUID.randomUUID();
    final Set<String> tags = new LinkedHashSet<>();
    String snbt; // stored NBT content without the outer braces
    Location loc;
    boolean valid = true;

    FakeEntity(FakeServer server, EntityType type, Location loc, String snbt) {
        this.server = server;
        this.type = type;
        this.loc = loc;
        this.snbt = snbt;
    }

    @Override
    public Location getLocation() {
        return loc.clone();
    }

    @Override
    public World getWorld() {
        return loc.getWorld();
    }

    @Override
    public UUID getUniqueId() {
        return uuid;
    }

    @Override
    public EntityType getType() {
        return type;
    }

    @Override
    public Set<String> getScoreboardTags() {
        return tags;
    }

    @Override
    public boolean isValid() {
        return valid;
    }

    @Override
    public void remove() {
        server.checkMain("Entity.remove");
        valid = false;
        ((FakeWorld) loc.getWorld()).entities.remove(this);
    }

    @Override
    public boolean teleport(Location location) {
        server.checkMain("teleport");
        loc = location.clone();
        return true;
    }
}
