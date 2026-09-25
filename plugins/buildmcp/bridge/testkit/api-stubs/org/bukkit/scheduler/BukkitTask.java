package org.bukkit.scheduler;

public interface BukkitTask {
    int getTaskId();

    boolean isCancelled();

    void cancel();
}
