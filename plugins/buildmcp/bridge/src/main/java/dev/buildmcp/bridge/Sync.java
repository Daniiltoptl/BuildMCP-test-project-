package dev.buildmcp.bridge;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.bukkit.Bukkit;
import org.bukkit.plugin.Plugin;

/** Runs code on the server main thread and waits for the result (HTTP threads must not touch the world). */
final class Sync {
    private Sync() {}

    static <T> T call(Plugin plugin, Callable<T> task) throws Exception {
        return call(plugin, task, 30_000L);
    }

    static <T> T call(Plugin plugin, Callable<T> task, long timeoutMs) throws Exception {
        if (Bukkit.isPrimaryThread()) {
            return task.call();
        }
        Future<T> f = Bukkit.getScheduler().callSyncMethod(plugin, task);
        try {
            return f.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (ExecutionException e) {
            Throwable c = e.getCause();
            if (c instanceof Exception ex) {
                throw ex;
            }
            throw new RuntimeException(c);
        } catch (TimeoutException e) {
            f.cancel(false);
            throw new ApiError(503, "the server main thread did not answer in " + timeoutMs / 1000 + " s");
        }
    }
}
