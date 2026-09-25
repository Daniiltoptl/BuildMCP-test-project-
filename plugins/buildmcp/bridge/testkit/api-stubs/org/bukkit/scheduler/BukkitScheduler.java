package org.bukkit.scheduler;

import java.util.concurrent.Callable;
import java.util.concurrent.Future;

import org.bukkit.plugin.Plugin;

public interface BukkitScheduler {
    BukkitTask runTask(Plugin plugin, Runnable task);

    BukkitTask runTaskAsynchronously(Plugin plugin, Runnable task);

    BukkitTask runTaskTimer(Plugin plugin, Runnable task, long delay, long period);

    <T> Future<T> callSyncMethod(Plugin plugin, Callable<T> task);
}
