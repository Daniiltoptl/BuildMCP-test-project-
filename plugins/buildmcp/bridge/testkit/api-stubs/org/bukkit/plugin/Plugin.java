package org.bukkit.plugin;

import java.io.File;
import java.util.logging.Logger;

import org.bukkit.command.TabExecutor;

public interface Plugin extends TabExecutor {
    File getDataFolder();

    PluginDescriptionFile getDescription();

    Logger getLogger();

    String getName();

    boolean isEnabled();

    void onEnable();

    void onDisable();
}
