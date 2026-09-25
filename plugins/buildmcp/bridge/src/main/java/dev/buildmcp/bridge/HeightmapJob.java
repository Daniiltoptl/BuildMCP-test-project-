package dev.buildmcp.bridge;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import org.bukkit.HeightMap;
import org.bukkit.World;
import org.bukkit.block.data.BlockData;

/** Surface height and top block of every column in a rectangle (ground without leaves). */
final class HeightmapJob extends Job {
    private final BuildBridgePlugin plugin;
    private final World world;
    private final int x1, z1, w, l;
    private ChunkSet chunkSet;
    private int[] heights;
    private int[] tops;
    private final Map<BlockData, Integer> index = new HashMap<>();
    private final List<String> palette = new ArrayList<>();
    private int cursor;
    private boolean loading = true;

    HeightmapJob(BuildBridgePlugin plugin, World world, int[] rect) {
        super("heightmap", "heightmap " + world.getName());
        this.plugin = plugin;
        this.world = world;
        this.x1 = Math.min(rect[0], rect[2]);
        this.z1 = Math.min(rect[1], rect[3]);
        this.w = Math.abs(rect[2] - rect[0]) + 1;
        this.l = Math.abs(rect[3] - rect[1]) + 1;
        if ((long) w * l > 4_000_000L) {
            throw new ApiError(413, "heightmap area too large (max 4M columns)");
        }
    }

    @Override
    boolean tick(long deadline) {
        if (chunkSet == null) {
            chunkSet = new ChunkSet(world, x1, z1, x1 + w - 1, z1 + l - 1);
            chunkSet.request();
            heights = new int[w * l];
            tops = new int[w * l];
            phase = "loading chunks";
            total = chunkSet.chunks.size();
        }
        if (loading) {
            boolean ready = chunkSet.poll(plugin);
            done = chunkSet.loaded();
            if (!ready) {
                return false;
            }
            loading = false;
            phase = "reading";
            total = (long) w * l;
            done = 0;
        }
        while (cursor < w * l) {
            int i = cursor++;
            int x = x1 + i % w, z = z1 + i / w;
            int y = world.getHighestBlockYAt(x, z, HeightMap.MOTION_BLOCKING_NO_LEAVES);
            heights[i] = y;
            BlockData d = world.getBlockAt(x, y, z).getBlockData();
            Integer v = index.get(d);
            if (v == null) {
                v = palette.size();
                palette.add(d.getAsString());
                index.put(d, v);
            }
            tops[i] = v;
            done = cursor;
            if ((cursor & 255) == 0 && System.nanoTime() > deadline) {
                return false;
            }
        }
        return true;
    }

    JsonObject resultJson() {
        JsonObject o = new JsonObject();
        o.addProperty("world", world.getName());
        o.addProperty("x1", x1);
        o.addProperty("z1", z1);
        o.addProperty("w", w);
        o.addProperty("l", l);
        JsonArray hs = new JsonArray();
        for (int v : heights) {
            hs.add(v);
        }
        o.add("heights", hs);
        o.add("top_palette", Json.strings(palette));
        JsonArray ts = new JsonArray();
        for (int v : tops) {
            ts.add(v);
        }
        o.add("top", ts);
        return o;
    }

    @Override
    void cleanup() {
        if (chunkSet != null) {
            chunkSet.release(plugin);
        }
    }
}
