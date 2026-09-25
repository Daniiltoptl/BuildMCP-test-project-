package dev.buildmcp.bridge;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.scheduler.BukkitTask;

/** Runs jobs one after another on the main thread, within a time budget per tick. */
final class JobManager implements Runnable {
    private static final int KEEP = 100;

    private final BuildBridgePlugin plugin;
    private final Queue<Job> queue = new ConcurrentLinkedQueue<>();
    private final Map<String, Job> jobs = new LinkedHashMap<>();
    private volatile Job current;
    private BukkitTask task;

    JobManager(BuildBridgePlugin plugin) {
        this.plugin = plugin;
    }

    void start() {
        task = Bukkit.getScheduler().runTaskTimer(plugin, this, 1L, 1L);
    }

    /** Main thread (plugin disable): stops everything and releases chunk tickets. */
    void stop() {
        if (task != null) {
            task.cancel();
            task = null;
        }
        Job c = current;
        if (c != null) {
            c.cancelRequested = true;
            finish(c, "cancelled: plugin disabled");
        }
        Job q;
        while ((q = queue.poll()) != null) {
            q.cancelRequested = true;
            q.complete("cancelled: plugin disabled");
        }
    }

    Job submit(Job job) {
        synchronized (jobs) {
            jobs.put(job.id, job);
            if (jobs.size() > KEEP) {
                Iterator<Map.Entry<String, Job>> it = jobs.entrySet().iterator();
                while (jobs.size() > KEEP && it.hasNext()) {
                    Job j = it.next().getValue();
                    if (j.isFinished()) {
                        it.remove();
                    }
                }
            }
        }
        queue.add(job);
        return job;
    }

    Job get(String id) {
        synchronized (jobs) {
            return jobs.get(id);
        }
    }

    List<Job> list() {
        synchronized (jobs) {
            return new ArrayList<>(jobs.values());
        }
    }

    Job current() {
        return current;
    }

    int queued() {
        return queue.size();
    }

    boolean cancel(String id) {
        Job j = get(id);
        if (j == null || j.isFinished()) {
            return false;
        }
        j.cancelRequested = true;
        if (queue.remove(j)) {
            j.complete("cancelled before start");
        }
        return true;
    }

    @Override
    public void run() {
        long deadline = System.nanoTime() + plugin.config().maxTickMillis() * 1_000_000L;
        Job j = current;
        if (j == null) {
            j = queue.poll();
            if (j == null) {
                return;
            }
            current = j;
            j.started = System.currentTimeMillis();
            j.phase = "starting";
        }
        String phase = j.phase;
        long t0 = System.nanoTime();
        try {
            if (j.cancelRequested) {
                finish(j, "cancelled");
            } else if (j.tick(deadline)) {
                finish(j, null);
            }
            j.tickMs.merge(phase, (System.nanoTime() - t0) / 1e6, Math::max);
        } catch (Throwable t) {
            plugin.getLogger().log(Level.WARNING, "BuildBridge job " + j.id + " failed", t);
            String msg = t.getMessage() != null ? t.getMessage() : t.getClass().getSimpleName();
            finish(j, msg);
        }
    }

    private void finish(Job j, String err) {
        try {
            j.cleanup();
        } catch (Throwable t) {
            plugin.getLogger().log(Level.WARNING, "BuildBridge job cleanup failed", t);
        }
        j.complete(err);
        current = null;
        plugin.onJobFinished(j);
    }
}
