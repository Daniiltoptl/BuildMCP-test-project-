package dev.buildmcp.bridge;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

import com.google.gson.JsonObject;

import org.bukkit.Bukkit;
import org.bukkit.ChunkSnapshot;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.BlockData;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.util.BoundingBox;

/** Reads a box of the world into a bundle (blocks, optionally block entity NBT, entities and biomes). */
final class ReadJob extends Job {
    private enum Step { PREPARE, LOAD, SNAPSHOT, CAPTURE, BUILD, DONE }

    private final BuildBridgePlugin plugin;
    private final World world;
    private final int x1, y1, z1, w, h, l;
    private final boolean withTiles, withEntities;

    private Step step = Step.PREPARE;
    private ChunkSet chunkSet;
    private final Map<Long, ChunkSnapshot> snaps = new HashMap<>();
    private final List<int[]> tilePos = new ArrayList<>();
    private final List<Entity> ents = new ArrayList<>();
    private final List<Bundle.Tile> tiles = new ArrayList<>();
    private final List<Bundle.Ent> entities = new ArrayList<>();
    private int cursor;
    private CompletableFuture<Bundle> build;
    private volatile Bundle result;

    ReadJob(BuildBridgePlugin plugin, World world, int[] box, boolean withTiles, boolean withEntities) {
        super("read", "read " + world.getName() + " " + box[0] + "," + box[1] + "," + box[2] + " .. " + box[3] + ","
                + box[4] + "," + box[5]);
        this.plugin = plugin;
        this.world = world;
        int ax = Math.min(box[0], box[3]), bx = Math.max(box[0], box[3]);
        int ay = Math.max(Math.min(box[1], box[4]), world.getMinHeight());
        int by = Math.min(Math.max(box[1], box[4]), world.getMaxHeight() - 1);
        int az = Math.min(box[2], box[5]), bz = Math.max(box[2], box[5]);
        if (by < ay) {
            throw new ApiError(400, "the box is outside the world height " + world.getMinHeight() + ".." + (world.getMaxHeight() - 1));
        }
        this.x1 = ax;
        this.y1 = ay;
        this.z1 = az;
        this.w = bx - ax + 1;
        this.h = by - ay + 1;
        this.l = bz - az + 1;
        long volume = (long) w * h * l;
        if (volume > plugin.config().maxCells()) {
            throw new ApiError(413, "box has " + volume + " blocks, over max-cells " + plugin.config().maxCells());
        }
        this.withTiles = withTiles;
        this.withEntities = withEntities;
    }

    Bundle result() {
        return result;
    }

    @Override
    boolean tick(long deadline) throws Exception {
        while (System.nanoTime() < deadline) {
            switch (step) {
                case PREPARE -> {
                    chunkSet = new ChunkSet(world, x1, z1, x1 + w - 1, z1 + l - 1);
                    chunkSet.request();
                    step = Step.LOAD;
                    phase = "loading chunks";
                    total = chunkSet.chunks.size();
                }
                case LOAD -> {
                    boolean ready = chunkSet.poll(plugin);
                    done = chunkSet.loaded();
                    if (!ready) {
                        return false;
                    }
                    step = Step.SNAPSHOT;
                    phase = "snapshot";
                    cursor = 0;
                    done = 0;
                }
                case SNAPSHOT -> {
                    List<int[]> chunks = chunkSet.chunks;
                    while (cursor < chunks.size()) {
                        int[] c = chunks.get(cursor++);
                        org.bukkit.Chunk ch = world.getChunkAt(c[0], c[1]);
                        snaps.put(ChunkSet.key(c[0], c[1]), ch.getChunkSnapshot(false, true, false));
                        if (withTiles) {
                            for (BlockState st : ch.getTileEntities()) {
                                int x = st.getX() - x1, y = st.getY() - y1, z = st.getZ() - z1;
                                if (x >= 0 && y >= 0 && z >= 0 && x < w && y < h && z < l) {
                                    tilePos.add(new int[]{x, y, z});
                                }
                            }
                        }
                        done = cursor;
                        if (System.nanoTime() > deadline) {
                            return false;
                        }
                    }
                    if (withEntities) {
                        BoundingBox box = new BoundingBox(x1, y1, z1, x1 + w, y1 + h, z1 + l);
                        for (Entity e : world.getNearbyEntities(box)) {
                            if (!(e instanceof Player)) {
                                ents.add(e);
                            }
                        }
                    }
                    step = Step.CAPTURE;
                    phase = "reading NBT";
                    cursor = 0;
                    done = 0;
                    total = tilePos.size() + ents.size();
                }
                case CAPTURE -> {
                    while (cursor < tilePos.size() + ents.size()) {
                        int k = cursor++;
                        done = cursor;
                        if (k < tilePos.size()) {
                            int[] t = tilePos.get(k);
                            Capture.Result r = Capture.runIn(world, String.format(Locale.ROOT,
                                    "data get block %d %d %d", x1 + t[0], y1 + t[1], z1 + t[2]));
                            String snbt = r.dataQuery();
                            if (snbt != null) {
                                tiles.add(new Bundle.Tile(t[0], t[1], t[2], snbt));
                            }
                        } else {
                            Entity e = ents.get(k - tilePos.size());
                            if (!e.isValid()) {
                                continue;
                            }
                            Capture.Result r = Capture.run("minecraft:data get entity " + e.getUniqueId());
                            String snbt = r.dataQuery();
                            if (snbt != null) {
                                Location loc = e.getLocation();
                                entities.add(new Bundle.Ent(loc.getX() - x1, loc.getY() - y1, loc.getZ() - z1,
                                        Keys.of(e.getType()), snbt));
                            }
                        }
                        if (System.nanoTime() > deadline) {
                            return false;
                        }
                    }
                    ents.clear();
                    step = Step.BUILD;
                    phase = "building";
                    total = 0;
                    done = 0;
                    build = new CompletableFuture<>();
                    Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
                        try {
                            build.complete(buildBundle());
                        } catch (Throwable t) {
                            build.completeExceptionally(t);
                        }
                    });
                }
                case BUILD -> {
                    if (!build.isDone()) {
                        return false;
                    }
                    result = build.join();
                    snaps.clear();
                    step = Step.DONE;
                }
                case DONE -> {
                    return true;
                }
            }
        }
        return false;
    }

    private Bundle buildBundle() {
        char[] cells = new char[w * h * l];
        Map<BlockData, Integer> index = new HashMap<>();
        List<String> palette = new ArrayList<>();
        palette.add("");
        Map<String, Integer> bindex = new HashMap<>();
        List<String> bpal = new ArrayList<>();
        byte[] biomes = new byte[w * l];
        int sampleY = y1 + h / 2;
        for (int z = 0; z < l; z++) {
            for (int x = 0; x < w; x++) {
                int wx = x1 + x, wz = z1 + z;
                ChunkSnapshot s = snaps.get(ChunkSet.key(wx >> 4, wz >> 4));
                int lx = wx & 15, lz = wz & 15;
                for (int y = 0; y < h; y++) {
                    BlockData d = s.getBlockData(lx, y1 + y, lz);
                    Integer v = index.get(d);
                    if (v == null) {
                        v = palette.size();
                        if (v > 65535) {
                            throw new IllegalStateException("more than 65535 block states in the box");
                        }
                        palette.add(d.getAsString());
                        index.put(d, v);
                    }
                    cells[x + z * w + y * w * l] = (char) (int) v;
                }
                String bk = Keys.of(s.getBiome(lx, sampleY, lz));
                Integer bv = bindex.get(bk);
                if (bv == null) {
                    bv = Math.min(bpal.size(), Bundle.BIOME_KEEP - 1);
                    if (bv == bpal.size()) {
                        bpal.add(bk);
                    }
                    bindex.put(bk, bv);
                }
                biomes[x + z * w] = (byte) (int) bv;
            }
        }
        JsonObject hdr = new JsonObject();
        hdr.addProperty("kind", "region");
        hdr.addProperty("world", world.getName());
        hdr.add("min", Json.arr(x1, y1, z1));
        hdr.addProperty("data_version", BuildBridgePlugin.dataVersion());
        return new Bundle(hdr, w, h, l, palette.toArray(new String[0]), cells, tiles, entities,
                bpal.toArray(new String[0]), biomes);
    }

    @Override
    void cleanup() {
        if (chunkSet != null) {
            chunkSet.release(plugin);
        }
        snaps.clear();
    }

    @Override
    void describe(JsonObject o) {
        o.addProperty("world", world.getName());
        o.add("min", Json.arr(x1, y1, z1));
        o.add("size", Json.arr(w, h, l));
    }
}
