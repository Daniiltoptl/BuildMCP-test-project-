package dev.buildmcp.fakeserver;

import java.util.ArrayList;
import java.util.List;

import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.block.Block;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Player;

final class FakePlayer extends FakeEntity implements Player {
    final String name;
    final List<String> messages = new ArrayList<>();

    FakePlayer(FakeServer server, String name, Location loc) {
        super(server, EntityType.PLAYER, loc, "");
        this.name = name;
    }

    @Override
    public String getName() {
        return name;
    }

    @Override
    public void sendMessage(String message) {
        messages.add(message);
    }

    @Override
    public boolean hasPermission(String perm) {
        return true;
    }

    @Override
    public GameMode getGameMode() {
        return GameMode.CREATIVE;
    }

    @Override
    public Block getTargetBlockExact(int maxDistance) {
        server.checkMain("getTargetBlockExact");
        double yaw = Math.toRadians(loc.getYaw()), pitch = Math.toRadians(loc.getPitch());
        double dx = -Math.sin(yaw) * Math.cos(pitch), dy = -Math.sin(pitch), dz = Math.cos(yaw) * Math.cos(pitch);
        double x = loc.getX(), y = loc.getY() + 1.62, z = loc.getZ();
        FakeWorld w = (FakeWorld) loc.getWorld();
        for (double t = 0; t < maxDistance; t += 0.05) {
            int bx = (int) Math.floor(x + dx * t), by = (int) Math.floor(y + dy * t), bz = (int) Math.floor(z + dz * t);
            if (!w.get(bx, by, bz).isAir()) {
                return w.getBlockAt(bx, by, bz);
            }
        }
        return null;
    }

    @Override
    public void remove() {
        throw new IllegalStateException("players cannot be removed");
    }
}
