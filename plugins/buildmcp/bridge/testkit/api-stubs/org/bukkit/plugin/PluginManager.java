package org.bukkit.plugin;

public interface PluginManager {
    Plugin getPlugin(String name);

    boolean isPluginEnabled(String name);
}
