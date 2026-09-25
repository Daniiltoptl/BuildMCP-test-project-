package dev.buildmcp.bridge;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;

import com.google.gson.JsonObject;

import org.bukkit.Bukkit;
import org.bukkit.ChunkSnapshot;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.BlockData;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.util.BoundingBox;

/**
 * Pastes a bundle 1:1: exact block states without physics or neighbour updates, block entity NBT,
 * entities and biomes. Before touching the world it saves what was there (for undo) and skips cells
 * that already hold the right block, so re-pasting a slightly changed build only sends the changes.
 *
 * <p>Steps: load chunks (async) -> snapshot -> capture NBT for the backup -> analyse (async) ->
 * remove the previous paste's entities -> place blocks -> NBT -> entities -> biomes.
 */
final class PasteJob extends Job {
    private enum Step { PREPARE, LOAD, SNAPSHOT, CAPTURE, ANALYZE, REMOVE, PLACE, TILES, ENTITIES, BIOMES, DONE }

    private record Plan(int[][] todo, long total, long unchanged) {}

    private final BuildBridgePlugin plugin;
    private final Bundle b;
    private final World world;
    private final int ox, oy, oz;
    private final boolean makeBackup;
    private final boolean compare;
    private final String entityTag;
    private final String undoOf;

    private Step step = Step.PREPARE;
    private BlockData[] states;
    private BlockData air;
    private ChunkSet chunkSet;
    private int yLo, yHi;
    private final Map<Long, ChunkSnapshot> snaps = new HashMap<>();
    private int cursor;
    private int cellCursor;
    private final Set<Integer> tileCells = new HashSet<>();
    private final List<int[]> worldTiles = new ArrayList<>();
    private final List<Entity> oldEntities = new ArrayList<>();
    private final List<Bundle.Tile> backupTiles = new ArrayList<>();
    private final List<Bundle.Ent> backupEntities = new ArrayList<>();
    private CompletableFuture<Plan> analysis;
    private Plan plan;
    private List<String> biomeCommands = List.of();
    private long placed, unchanged, invalid, tilesOk, entitiesOk, entitiesRemoved, biomesOk;
    private volatile String backupId;

    PasteJob(BuildBridgePlugin plugin, Bundle b, World world, int ox, int oy, int oz, boolean makeBackup,
             boolean compare, String entityTag, String label, String undoOf) {
        super(undoOf != null ? "undo" : "paste", label);
        this.plugin = plugin;
        this.b = b;
        this.world = world;
        this.ox = ox;
        this.oy = oy;
        this.oz = oz;
        this.makeBackup = makeBackup;
        this.compare = compare;
        this.entityTag = entityTag == null || entityTag.isBlank() ? null : entityTag;
        this.undoOf = undoOf;
    }

    String backupId() {
        return backupId;
    }

    String undoOf() {
        return undoOf;
    }

    long placed() {
        return placed;
    }

    @Override
    boolean tick(long deadline) throws Exception {
        while (System.nanoTime() < deadline) {
            switch (step) {
                case PREPARE -> prepare();
                case LOAD -> {
                    done = chunkSet.loaded();
                    if (!chunkSet.poll(plugin)) {
                        done = chunkSet.loaded();
                        return false;
                    }
                    next(Step.SNAPSHOT, "snapshot", chunkSet.chunks.size());
                }
                case SNAPSHOT -> {
                    if (!snapshot(deadline)) {
                        return false;
                    }
                }
                case CAPTURE -> {
                    if (!capture(deadline)) {
                        return false;
                    }
                }
                case ANALYZE -> {
                    if (analysis == null) {
                        startAnalysis();
                    }
                    if (!analysis.isDone()) {
                        return false;
                    }
                    plan = analysis.join();
                    snaps.clear();
                    unchanged = plan.unchanged();
                    int y1 = oy + yLo, y2 = oy + yHi;
                    if (b.biomes != null && yLo <= yHi) {
                        biomeCommands = BiomeBoxes.commands(b.biomePalette, b.biomes, b.w, b.l, ox, oz, y1, y2);
                    }
                    next(Step.REMOVE, "removing old entities", oldEntities.size());
                }
                case REMOVE -> {
                    for (Entity e : oldEntities) {
                        if (e.isValid()) {
                            e.remove();
                            entitiesRemoved++;
                        }
                    }
                    oldEntities.clear();
                    next(Step.PLACE, "placing blocks", plan.total());
                }
                case PLACE -> {
                    if (!place(deadline)) {
                        return false;
                    }
                    next(Step.TILES, "block entities", b.tiles.size());
                }
                case TILES -> {
                    if (!tiles(deadline)) {
                        return false;
                    }
                    next(Step.ENTITIES, "entities", b.entities.size());
                }
                case ENTITIES -> {
                    if (!entities(deadline)) {
                        return false;
                    }
                    next(Step.BIOMES, "biomes", biomeCommands.size());
                }
                case BIOMES -> {
                    if (!biomes(deadline)) {
                        return false;
                    }
                    step = Step.DONE;
                }
                case DONE -> {
                    return true;
                }
            }
        }
        return false;
    }

    private void next(Step s, String phaseName, long phaseTotal) {
        step = s;
        phase = phaseName;
        cursor = 0;
        cellCursor = 0;
        done = 0;
        total = phaseTotal;
    }

    // ----------------------------------------------------------------- steps
    private void prepare() {
        int minY = world.getMinHeight(), maxY = world.getMaxHeight() - 1;
        yLo = Math.max(0, minY - oy);
        yHi = Math.min(b.h - 1, maxY - oy);
        if (yLo > 0 || yHi < b.h - 1) {
            warn("part of the build is outside the world height " + minY + ".." + maxY + " and was skipped");
        }
        air = Bukkit.createBlockData("minecraft:air");
        states = new BlockData[b.palette.length];
        for (int i = 1; i < b.palette.length; i++) {
            try {
                states[i] = Bukkit.createBlockData(b.palette[i]);
            } catch (IllegalArgumentException e) {
                warn("unknown block state '" + b.palette[i] + "' for this server version: skipped");
            }
        }
        if (states.length > 1) {
            for (char c : b.cells) {
                if (c != 0 && states[c] == null) {
                    invalid++;
                }
            }
        }
        for (Bundle.Tile t : b.tiles) {
            if (inside(t.x(), t.y(), t.z())) {
                tileCells.add(b.index(t.x(), t.y(), t.z()));
            } else {
                warn("block entity at " + t.x() + "," + t.y() + "," + t.z() + " is outside the bundle");
            }
        }
        chunkSet = new ChunkSet(world, ox, oz, ox + b.w - 1, oz + b.l - 1);
        chunkSet.request();
        next(Step.LOAD, "loading chunks", chunkSet.chunks.size());
    }

    private boolean inside(int x, int y, int z) {
        return x >= 0 && y >= 0 && z >= 0 && x < b.w && y < b.h && z < b.l;
    }

    /** Main thread: copies the chunks (for compare + backup) and lists what has to be saved. */
    private boolean snapshot(long deadline) {
        List<int[]> chunks = chunkSet.chunks;
        boolean biomes = makeBackup && b.biomes != null;
        while (cursor < chunks.size()) {
            int[] c = chunks.get(cursor++);
            org.bukkit.Chunk ch = world.getChunkAt(c[0], c[1]);
            snaps.put(ChunkSet.key(c[0], c[1]), ch.getChunkSnapshot(false, biomes, false));
            if (makeBackup) {
                for (BlockState st : ch.getTileEntities()) {
                    int x = st.getX() - ox, y = st.getY() - oy, z = st.getZ() - oz;
                    if (inside(x, y, z) && y >= yLo && y <= yHi && b.cells[b.index(x, y, z)] != 0) {
                        worldTiles.add(new int[]{x, y, z});
                    }
                }
            }
            done = cursor;
            if (System.nanoTime() > deadline) {
                return false;
            }
        }
        if (entityTag != null) {
            BoundingBox box = new BoundingBox(ox, oy, oz, ox + b.w, oy + b.h, oz + b.l);
            for (Entity e : world.getNearbyEntities(box)) {
                if (!(e instanceof Player) && e.getScoreboardTags().contains(entityTag)) {
                    oldEntities.add(e);
                }
            }
        }
        next(Step.CAPTURE, "saving block entities", makeBackup ? worldTiles.size() + oldEntities.size() : 0);
        return true;
    }

    /** Main thread: NBT of existing block entities and of the entities that will be replaced. */
    private boolean capture(long deadline) {
        if (!makeBackup) {
            next(Step.ANALYZE, "analysing", 0);
            return true;
        }
        while (cursor < worldTiles.size() + oldEntities.size()) {
            int k = cursor++;
            if (k < worldTiles.size()) {
                int[] t = worldTiles.get(k);
                Capture.Result r = Capture.runIn(world, String.format(Locale.ROOT, "data get block %d %d %d",
                        ox + t[0], oy + t[1], oz + t[2]));
                String snbt = r.dataQuery();
                if (snbt != null) {
                    backupTiles.add(new Bundle.Tile(t[0], t[1], t[2], snbt));
                } else {
                    warn("could not save block entity at " + (ox + t[0]) + "," + (oy + t[1]) + "," + (oz + t[2]) + ": " + r.text());
                }
            } else {
                Entity e = oldEntities.get(k - worldTiles.size());
                Capture.Result r = Capture.run("minecraft:data get entity " + e.getUniqueId());
                String snbt = r.dataQuery();
                if (snbt != null) {
                    Location l = e.getLocation();
                    backupEntities.add(new Bundle.Ent(l.getX() - ox, l.getY() - oy, l.getZ() - oz,
                            Keys.of(e.getType()), snbt));
                } else {
                    warn("could not save entity " + e.getUniqueId() + ": " + r.text());
                }
            }
            done = cursor;
            if (System.nanoTime() > deadline) {
                return false;
            }
        }
        next(Step.ANALYZE, "analysing", 0);
        return true;
    }

    private void startAnalysis() {
        analysis = new CompletableFuture<>();
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                analysis.complete(analyze());
            } catch (Throwable t) {
                analysis.completeExceptionally(t);
            }
        });
    }

    /** Async: which cells really change, and the backup of those cells. */
    private Plan analyze() throws Exception {
        List<int[]> chunks = chunkSet.chunks;
        char[] backupCells = makeBackup ? new char[b.cells.length] : null;
        Map<BlockData, Integer> backupIndex = new HashMap<>();
        List<String> backupPalette = new ArrayList<>();
        backupPalette.add("");
        int[][] todo = new int[chunks.size()][];
        long count = 0, same = 0;
        for (int ci = 0; ci < chunks.size(); ci++) {
            int[] c = chunks.get(ci);
            ChunkSnapshot s = snaps.get(ChunkSet.key(c[0], c[1]));
            int x0 = Math.max(ox, c[0] << 4) - ox, x1 = Math.min(ox + b.w - 1, (c[0] << 4) + 15) - ox;
            int z0 = Math.max(oz, c[1] << 4) - oz, z1 = Math.min(oz + b.l - 1, (c[1] << 4) + 15) - oz;
            IntList list = new IntList();
            for (int y = yLo; y <= yHi; y++) {
                int wy = oy + y;
                for (int z = z0; z <= z1; z++) {
                    int lz = (oz + z) & 15;
                    int base = z * b.w + y * b.w * b.l;
                    for (int x = x0; x <= x1; x++) {
                        int i = base + x;
                        int idx = b.cells[i];
                        if (idx == 0) {
                            continue;
                        }
                        BlockData target = states[idx];
                        if (target == null) {
                            continue;
                        }
                        BlockData cur = s.getBlockData((ox + x) & 15, wy, lz);
                        if (compare && cur.equals(target) && (tileCells.isEmpty() || !tileCells.contains(i))) {
                            same++;
                            continue;
                        }
                        list.add(i);
                        if (backupCells != null) {
                            Integer bi = backupIndex.get(cur);
                            if (bi == null) {
                                bi = backupPalette.size();
                                backupPalette.add(cur.getAsString());
                                backupIndex.put(cur, bi);
                            }
                            backupCells[i] = (char) (int) bi;
                        }
                    }
                }
            }
            todo[ci] = list.toArray();
            count += todo[ci].length;
        }
        if (makeBackup && (count > 0 || !backupTiles.isEmpty() || !backupEntities.isEmpty() || !b.entities.isEmpty()
                || !b.tiles.isEmpty() || b.biomes != null)) {
            String[] bioPal = null;
            byte[] bioGrid = null;
            if (b.biomes != null) {
                Map<String, Integer> bi = new HashMap<>();
                List<String> bp = new ArrayList<>();
                bioGrid = new byte[b.w * b.l];
                int sampleY = oy + Math.max(yLo, Math.min(yHi, b.h / 2));
                for (int z = 0; z < b.l; z++) {
                    for (int x = 0; x < b.w; x++) {
                        if ((b.biomes[x + z * b.w] & 0xFF) == Bundle.BIOME_KEEP) {
                            bioGrid[x + z * b.w] = (byte) Bundle.BIOME_KEEP;
                            continue;
                        }
                        ChunkSnapshot s = snaps.get(ChunkSet.key((ox + x) >> 4, (oz + z) >> 4));
                        String key = Keys.of(s.getBiome((ox + x) & 15, sampleY, (oz + z) & 15));
                        Integer v = bi.get(key);
                        if (v == null) {
                            v = bp.size();
                            if (v >= Bundle.BIOME_KEEP) {
                                v = 0;
                            } else {
                                bp.add(key);
                                bi.put(key, v);
                            }
                        }
                        bioGrid[x + z * b.w] = (byte) (int) v;
                    }
                }
                bioPal = bp.toArray(new String[0]);
            }
            JsonObject h = new JsonObject();
            h.addProperty("kind", "backup");
            h.addProperty("world", world.getName());
            h.add("min", Json.arr(ox, oy, oz));
            h.addProperty("label", "undo: " + label);
            if (entityTag != null) {
                h.addProperty("entity_tag", entityTag);
            }
            char[] cells = backupCells != null ? backupCells : new char[b.cells.length];
            Bundle backup = new Bundle(h, b.w, b.h, b.l, backupPalette.toArray(new String[0]), cells,
                    new ArrayList<>(backupTiles), new ArrayList<>(backupEntities), bioPal, bioGrid);
            Backups.Entry e = plugin.backups().save(backup, world.getName(), new int[]{ox, oy, oz}, label, id,
                    entityTag, count);
            backupId = e.id();
        }
        return new Plan(todo, count, same);
    }

    /** Main thread: sets blocks without physics, shape updates or neighbour updates. */
    private boolean place(long deadline) {
        int[][] todo = plan.todo();
        int wl = b.w * b.l;
        while (cursor < todo.length) {
            int[] list = todo[cursor];
            while (cellCursor < list.length) {
                int i = list[cellCursor++];
                int y = i / wl, rest = i - y * wl, z = rest / b.w, x = rest - z * b.w;
                Block blk = world.getBlockAt(ox + x, oy + y, oz + z);
                if (!tileCells.isEmpty() && tileCells.contains(i)) {
                    blk.setBlockData(air, false); // fresh block entity, no stale NBT
                }
                blk.setBlockData(states[b.cells[i]], false);
                placed++;
                done++;
                if ((placed & 127) == 0 && System.nanoTime() > deadline) {
                    return false;
                }
            }
            cursor++;
            cellCursor = 0;
        }
        return true;
    }

    private boolean tiles(long deadline) {
        while (cursor < b.tiles.size()) {
            Bundle.Tile t = b.tiles.get(cursor++);
            done = cursor;
            if (!inside(t.x(), t.y(), t.z()) || t.y() < yLo || t.y() > yHi) {
                continue;
            }
            char idx = b.cells[b.index(t.x(), t.y(), t.z())];
            if (idx != 0 && states[idx] == null) {
                continue;
            }
            Capture.Result r = Capture.runIn(world, String.format(Locale.ROOT, "data merge block %d %d %d %s",
                    ox + t.x(), oy + t.y(), oz + t.z(), t.snbt()));
            if (r.hasKey("commands.data.block.modified", "commands.data.merge.failed")) {
                tilesOk++;
            } else {
                warn("NBT at " + (ox + t.x()) + "," + (oy + t.y()) + "," + (oz + t.z()) + " failed: " + shorten(r.text()));
            }
            if (System.nanoTime() > deadline) {
                return false;
            }
        }
        return true;
    }

    private boolean entities(long deadline) {
        int minY = world.getMinHeight(), maxY = world.getMaxHeight();
        while (cursor < b.entities.size()) {
            Bundle.Ent e = b.entities.get(cursor++);
            done = cursor;
            double x = ox + e.x(), y = oy + e.y(), z = oz + e.z();
            if (y < minY - 64 || y > maxY + 64) {
                warn("entity " + e.id() + " is outside the world height: skipped");
                continue;
            }
            Capture.Result r = Capture.runIn(world, String.format(Locale.ROOT, "summon %s %.5f %.5f %.5f %s",
                    e.id(), x, y, z, e.snbt()));
            if (r.hasKey("commands.summon.success")) {
                entitiesOk++;
            } else {
                warn("entity " + e.id() + " at " + String.format(Locale.ROOT, "%.1f,%.1f,%.1f", x, y, z) + " failed: "
                        + shorten(r.text()));
            }
            if (System.nanoTime() > deadline) {
                return false;
            }
        }
        return true;
    }

    private boolean biomes(long deadline) {
        while (cursor < biomeCommands.size()) {
            Capture.Result r = Capture.runIn(world, biomeCommands.get(cursor++));
            done = cursor;
            if (r.hasKey("commands.fillbiome.success")) {
                biomesOk++;
            } else if (r.text().toLowerCase(Locale.ROOT).contains("no biome entries were changed")) {
                biomesOk++; // newer servers report "already that biome" as a failure
            } else {
                warn("biome: " + shorten(r.text()));
            }
            if (System.nanoTime() > deadline) {
                return false;
            }
        }
        return true;
    }

    private static String shorten(String s) {
        s = s == null ? "" : s.replace('\n', ' ');
        return s.length() > 300 ? s.substring(0, 300) + "..." : s;
    }

    @Override
    void cleanup() {
        if (chunkSet != null) {
            chunkSet.release(plugin);
        }
        snaps.clear();
        oldEntities.clear();
    }

    @Override
    void describe(JsonObject o) {
        o.addProperty("step", step.name().toLowerCase(Locale.ROOT));
        o.addProperty("world", world.getName());
        o.add("min", Json.arr(ox, oy, oz));
        o.add("size", Json.arr(b.w, b.h, b.l));
        o.addProperty("placed", placed);
        o.addProperty("unchanged", unchanged);
        o.addProperty("invalid", invalid);
        o.addProperty("tiles", tilesOk);
        o.addProperty("entities", entitiesOk);
        o.addProperty("entities_removed", entitiesRemoved);
        o.addProperty("biome_commands", biomesOk);
        if (plan != null) {
            o.addProperty("changes", plan.total());
        }
        if (backupId != null) {
            o.addProperty("backup", backupId);
        }
        if (undoOf != null) {
            o.addProperty("undo_of", undoOf);
        }
    }
}
