package dev.buildmcp.fakeserver;

import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

import org.bukkit.plugin.Plugin;
import org.bukkit.scheduler.BukkitScheduler;
import org.bukkit.scheduler.BukkitTask;

/** A 20 TPS main thread with sync tasks, repeating tasks and an async pool. */
final class FakeScheduler implements BukkitScheduler {
    private final FakeServer server;
    private final Queue<Runnable> sync = new ConcurrentLinkedQueue<>();
    private final List<Timer> timers = new ArrayList<>();
    private final Queue<Timer> newTimers = new ConcurrentLinkedQueue<>();
    private final ExecutorService async = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "fake-async");
        t.setDaemon(true);
        return t;
    });
    private final AtomicInteger ids = new AtomicInteger();

    final class Timer implements BukkitTask {
        final int id = ids.incrementAndGet();
        final Runnable task;
        final long period;
        long next;
        volatile boolean cancelled;

        Timer(Runnable task, long delay, long period) {
            this.task = task;
            this.period = period;
            this.next = server.tick + Math.max(1, delay);
        }

        @Override
        public int getTaskId() {
            return id;
        }

        @Override
        public boolean isCancelled() {
            return cancelled;
        }

        @Override
        public void cancel() {
            cancelled = true;
        }
    }

    FakeScheduler(FakeServer server) {
        this.server = server;
    }

    /** Main thread: one server tick. */
    void tick() {
        Timer nt;
        while ((nt = newTimers.poll()) != null) {
            timers.add(nt);
        }
        for (Timer t : new ArrayList<>(timers)) {
            if (t.cancelled) {
                timers.remove(t);
                continue;
            }
            if (server.tick >= t.next) {
                long t0 = System.nanoTime();
                try {
                    t.task.run();
                } catch (Throwable e) {
                    e.printStackTrace();
                }
                if (t.period > 0) { // plugin repeating tasks (the job runner): how long one run takes
                    server.stats.maxTaskMicros = Math.max(server.stats.maxTaskMicros, (System.nanoTime() - t0) / 1000);
                }
                if (t.period <= 0) {
                    timers.remove(t);
                } else {
                    t.next = server.tick + t.period;
                }
            }
        }
        long end = System.nanoTime() + 5_000_000L; // sync tasks run in the rest of the tick, like Paper
        Runnable r;
        while ((r = sync.poll()) != null) {
            try {
                r.run();
            } catch (Throwable e) {
                e.printStackTrace();
            }
            if (System.nanoTime() > end) {
                break;
            }
        }
    }

    void later(long ticks, Runnable r) {
        newTimers.add(new Timer(r, ticks, 0));
    }

    void shutdown() {
        async.shutdownNow();
    }

    @Override
    public BukkitTask runTask(Plugin plugin, Runnable task) {
        Timer t = new Timer(task, 1, 0);
        newTimers.add(t);
        return t;
    }

    @Override
    public BukkitTask runTaskAsynchronously(Plugin plugin, Runnable task) {
        Timer t = new Timer(task, 0, 0);
        async.submit(task);
        return t;
    }

    @Override
    public BukkitTask runTaskTimer(Plugin plugin, Runnable task, long delay, long period) {
        Timer t = new Timer(task, delay, period);
        newTimers.add(t);
        return t;
    }

    @Override
    public <T> Future<T> callSyncMethod(Plugin plugin, Callable<T> task) {
        FutureTask<T> f = new FutureTask<>(task);
        sync.add(f);
        return f;
    }
}
