package dev.buildmcp.bridge;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Queue;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.plugin.Plugin;

/**
 * The chunk columns under a box: loads them asynchronously (Paper), keeps them loaded with plugin
 * tickets while a job runs and releases them afterwards. Main thread except the load callbacks.
 */
final class ChunkSet {
    final World world;
    /** Chunk coordinates [cx, cz], nearest to the box center first. */
    final List<int[]> chunks = new ArrayList<>();
    private final Queue<long[]> arrived = new ConcurrentLinkedQueue<>();
    private final Set<Long> ticketed = new HashSet<>();
    private final AtomicInteger failed = new AtomicInteger();
    private boolean requested;

    ChunkSet(World world, int x1, int z1, int x2, int z2) {
        this.world = world;
        int cx1 = x1 >> 4, cz1 = z1 >> 4, cx2 = x2 >> 4, cz2 = z2 >> 4;
        double mx = (cx1 + cx2) / 2.0, mz = (cz1 + cz2) / 2.0;
        for (int cx = cx1; cx <= cx2; cx++) {
            for (int cz = cz1; cz <= cz2; cz++) {
                chunks.add(new int[]{cx, cz});
            }
        }
        chunks.sort(Comparator.comparingDouble(c -> (c[0] - mx) * (c[0] - mx) + (c[1] - mz) * (c[1] - mz)));
    }

    static long key(int cx, int cz) {
        return ((long) cx << 32) ^ (cz & 0xFFFFFFFFL);
    }

    /** Starts async loads (generating missing chunks). */
    void request() {
        if (requested) {
            return;
        }
        requested = true;
        for (int[] c : chunks) {
            final int cx = c[0], cz = c[1];
            world.getChunkAtAsync(cx, cz, true).whenComplete((chunk, err) -> {
                if (err != null || chunk == null) {
                    failed.incrementAndGet();
                } else {
                    arrived.add(new long[]{cx, cz});
                }
            });
        }
    }

    /** Main thread: pins arrived chunks with tickets. True when every chunk is loaded and pinned. */
    boolean poll(Plugin plugin) {
        long[] c;
        while ((c = arrived.poll()) != null) {
            int cx = (int) c[0], cz = (int) c[1];
            if (ticketed.add(key(cx, cz))) {
                world.addPluginChunkTicket(cx, cz, plugin);
            }
        }
        if (failed.get() > 0) {
            throw new IllegalStateException(failed.get() + " chunk(s) could not be loaded");
        }
        return ticketed.size() >= chunks.size();
    }

    int loaded() {
        return ticketed.size();
    }

    /** Main thread: removes this job's tickets (the server unloads the chunks when nobody needs them). */
    void release(Plugin plugin) {
        if (!Bukkit.isPrimaryThread()) {
            throw new IllegalStateException("release off the main thread");
        }
        for (long k : ticketed) {
            world.removePluginChunkTicket((int) (k >> 32), (int) k, plugin);
        }
        ticketed.clear();
    }
}
