package dev.buildmcp.fakeserver;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import org.bukkit.Chunk;
import org.bukkit.HeightMap;
import org.bukkit.Location;
import org.bukkit.NamespacedKey;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.entity.Entity;
import org.bukkit.plugin.Plugin;
import org.bukkit.util.BoundingBox;

/**
 * A world that behaves like the parts of a Paper world BuildBridge relies on, and checks the rules a
 * real server enforces: world access only on the main thread, chunks must be loaded (a sync load is
 * counted as a problem), plugin tickets keep chunks loaded, unticketed chunks unload after a while.
 */
final class FakeWorld implements World {
    static final int UNLOAD_AFTER_TICKS = 10;

    final FakeServer server;
    final String name;
    final NamespacedKey key;
    final Environment env;
    final int minY, maxY; // maxY exclusive
    final UUID uid = UUID.randomUUID();
    final Map<Long, FakeData> data = new HashMap<>(); // generated chunk contents (persist across unloads)
    final Map<Long, Long> loadedUntil = new HashMap<>(); // chunk -> tick until which it stays loaded
    final Map<Long, Set<Plugin>> tickets = new HashMap<>();
    final List<FakeEntity> entities = new ArrayList<>();
    final Map<Long, String> biomes = new HashMap<>(); // quart -> biome

    /** Contents of one chunk column. */
    static final class FakeData {
        final FakeBlockData[] blocks;
        final Map<Integer, String> tiles = new HashMap<>(); // local index -> SNBT content

        FakeData(int height) {
            blocks = new FakeBlockData[16 * 16 * height];
        }
    }

    FakeWorld(FakeServer server, String name, String key, Environment env, int minY, int maxY) {
        this.server = server;
        this.name = name;
        this.key = NamespacedKey.fromString(key);
        this.env = env;
        this.minY = minY;
        this.maxY = maxY;
    }

    static long ck(int cx, int cz) {
        return ((long) cx << 32) ^ (cz & 0xFFFFFFFFL);
    }

    int local(int x, int y, int z) {
        return ((y - minY) * 16 + (z & 15)) * 16 + (x & 15);
    }

    FakeData generate(int cx, int cz) {
        return data.computeIfAbsent(ck(cx, cz), k -> {
            FakeData d = new FakeData(maxY - minY);
            if (env == Environment.NORMAL) {
                FakeBlockData stone = FakeBlockData.parse("stone");
                FakeBlockData dirt = FakeBlockData.parse("dirt");
                FakeBlockData grass = FakeBlockData.parse("grass_block[snowy=false]");
                for (int x = 0; x < 16; x++) {
                    for (int z = 0; z < 16; z++) {
                        for (int y = minY; y <= 63; y++) {
                            d.blocks[local(x, y, z)] = y <= 60 ? stone : y <= 62 ? dirt : grass;
                        }
                    }
                }
            }
            return d;
        });
    }

    /** Main-thread check + loaded-chunk check for every world access. */
    FakeData access(int x, int z) {
        server.checkMain("world access");
        int cx = x >> 4, cz = z >> 4;
        long k = ck(cx, cz);
        if (!isLoaded(k)) {
            server.stats.syncChunkLoads++;
            loadedUntil.put(k, server.tick + UNLOAD_AFTER_TICKS);
        }
        return generate(cx, cz);
    }

    boolean isLoaded(long k) {
        if (tickets.containsKey(k) && !tickets.get(k).isEmpty()) {
            return true;
        }
        int cx = (int) (k >> 32), cz = (int) k;
        for (FakePlayer p : server.players) {
            if (p.getWorld() == this && Math.abs((p.getLocation().getBlockX() >> 4) - cx) <= 4
                    && Math.abs((p.getLocation().getBlockZ() >> 4) - cz) <= 4) {
                return true; // player view distance
            }
        }
        Long until = loadedUntil.get(k);
        return until != null && until >= server.tick;
    }

    FakeBlockData get(int x, int y, int z) {
        if (y < minY || y >= maxY) {
            return FakeBlockData.AIR;
        }
        FakeBlockData b = access(x, z).blocks[local(x, y, z)];
        return b == null ? FakeBlockData.AIR : b;
    }

    void set(int x, int y, int z, FakeBlockData b) {
        if (y < minY || y >= maxY) {
            throw new IllegalArgumentException("y out of world");
        }
        FakeData d = access(x, z);
        int i = local(x, y, z);
        FakeBlockData old = d.blocks[i] == null ? FakeBlockData.AIR : d.blocks[i];
        d.blocks[i] = b.isAir() ? null : b;
        if (!old.name.equals(b.name)) {
            d.tiles.remove(i);
            if (b.hasTile()) {
                d.tiles.put(i, "");
            }
        }
        server.stats.blockSets++;
    }

    String tile(int x, int y, int z) {
        return access(x, z).tiles.get(local(x, y, z));
    }

    void setTile(int x, int y, int z, String content) {
        access(x, z).tiles.put(local(x, y, z), content);
    }

    String biome(int x, int y, int z) {
        long q = (((long) (x >> 2)) & 0x3FFFFF) | ((((long) (z >> 2)) & 0x3FFFFF) << 22) | ((((long) (y >> 2)) & 0xFFFFF) << 44);
        return biomes.getOrDefault(q, "minecraft:plains");
    }

    void setBiome(int qx, int qy, int qz, String biome) {
        long q = (((long) qx) & 0x3FFFFF) | ((((long) qz) & 0x3FFFFF) << 22) | ((((long) qy) & 0xFFFFF) << 44);
        biomes.put(q, biome);
    }

    /** Tickless chunks expire (called every tick). */
    void tick() {
        loadedUntil.entrySet().removeIf(e -> e.getValue() < server.tick);
    }

    int ticketCount() {
        int n = 0;
        for (Set<Plugin> s : tickets.values()) {
            n += s.size();
        }
        return n;
    }

    // ------------------------------------------------------------------ World
    @Override
    public NamespacedKey getKey() {
        return key;
    }

    @Override
    public String getName() {
        return name;
    }

    @Override
    public UUID getUID() {
        return uid;
    }

    @Override
    public Environment getEnvironment() {
        return env;
    }

    @Override
    public int getMinHeight() {
        return minY;
    }

    @Override
    public int getMaxHeight() {
        return maxY;
    }

    @Override
    public Location getSpawnLocation() {
        return new Location(this, 0.5, 64, 0.5);
    }

    @Override
    public Block getBlockAt(int x, int y, int z) {
        server.checkMain("getBlockAt");
        return new FakeBlock(this, x, y, z);
    }

    @Override
    public Chunk getChunkAt(int x, int z) {
        access(x << 4, z << 4);
        return new FakeChunk(this, x, z);
    }

    @Override
    public boolean isChunkLoaded(int x, int z) {
        return isLoaded(ck(x, z));
    }

    @Override
    public CompletableFuture<Chunk> getChunkAtAsync(int x, int z, boolean gen) {
        CompletableFuture<Chunk> f = new CompletableFuture<>();
        // like Paper: loads off-thread, completes on the main thread a few ticks later
        server.scheduler.later(1 + Math.floorMod(x * 7 + z * 3, 3), () -> {
            generate(x, z);
            loadedUntil.put(ck(x, z), server.tick + UNLOAD_AFTER_TICKS);
            server.stats.asyncChunkLoads++;
            f.complete(new FakeChunk(this, x, z));
        });
        return f;
    }

    @Override
    public boolean addPluginChunkTicket(int x, int z, Plugin plugin) {
        server.checkMain("addPluginChunkTicket");
        long k = ck(x, z);
        if (!isLoaded(k)) {
            server.stats.syncChunkLoads++;
        }
        generate(x, z);
        return tickets.computeIfAbsent(k, kk -> new HashSet<>()).add(plugin);
    }

    @Override
    public boolean removePluginChunkTicket(int x, int z, Plugin plugin) {
        server.checkMain("removePluginChunkTicket");
        long k = ck(x, z);
        Set<Plugin> s = tickets.get(k);
        boolean r = s != null && s.remove(plugin);
        if (s != null && s.isEmpty()) {
            tickets.remove(k);
            loadedUntil.put(k, server.tick + UNLOAD_AFTER_TICKS);
        }
        return r;
    }

    @Override
    public int getHighestBlockYAt(int x, int z, HeightMap heightMap) {
        FakeData d = access(x, z);
        for (int y = maxY - 1; y >= minY; y--) {
            FakeBlockData b = d.blocks[local(x, y, z)];
            if (b != null && !(heightMap == HeightMap.MOTION_BLOCKING_NO_LEAVES && b.name.endsWith("_leaves"))) {
                return y;
            }
        }
        return minY - 1;
    }

    @Override
    public Collection<Entity> getNearbyEntities(BoundingBox box) {
        server.checkMain("getNearbyEntities");
        List<Entity> out = new ArrayList<>();
        for (FakeEntity e : entities) {
            Location l = e.getLocation();
            if (e.isValid() && box.contains(l.getX(), l.getY(), l.getZ())) {
                out.add(e);
            }
        }
        for (FakePlayer p : server.players) {
            Location l = p.getLocation();
            if (p.getWorld() == this && box.contains(l.getX(), l.getY(), l.getZ())) {
                out.add(p);
            }
        }
        return out;
    }
}
