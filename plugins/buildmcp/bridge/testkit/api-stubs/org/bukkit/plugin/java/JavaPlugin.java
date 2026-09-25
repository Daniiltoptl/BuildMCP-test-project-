package org.bukkit.plugin.java;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.command.PluginCommand;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.PluginDescriptionFile;

public abstract class JavaPlugin implements Plugin {
    private File dataFolder;
    private PluginDescriptionFile description;
    private Logger logger;
    private FileConfiguration config;
    private boolean enabled;
    private final Map<String, PluginCommand> commands = new HashMap<>();

    public JavaPlugin() {
    }

    /** Test kit only: what the plugin loader does on a real server. */
    public final void testkitInit(File dataFolder, PluginDescriptionFile description, List<String> commandNames) {
        this.dataFolder = dataFolder;
        this.description = description;
        this.logger = Logger.getLogger(description.getName());
        for (String c : commandNames) {
            commands.put(c, PluginCommand.create(c, this));
        }
    }

    /** Test kit only. */
    public final void testkitSetEnabled(boolean enabled) {
        this.enabled = enabled;
        if (enabled) {
            onEnable();
        } else {
            onDisable();
        }
    }

    @Override
    public File getDataFolder() {
        return dataFolder;
    }

    @Override
    public PluginDescriptionFile getDescription() {
        return description;
    }

    @Override
    public Logger getLogger() {
        return logger;
    }

    @Override
    public String getName() {
        return description.getName();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    public PluginCommand getCommand(String name) {
        return commands.get(name);
    }

    public FileConfiguration getConfig() {
        if (config == null) {
            reloadConfig();
        }
        return config;
    }

    public void reloadConfig() {
        YamlConfiguration c = new YamlConfiguration();
        File f = new File(dataFolder, "config.yml");
        try {
            if (f.exists()) {
                c.load(f);
            } else {
                try (InputStream in = getClass().getClassLoader().getResourceAsStream("config.yml")) {
                    if (in != null) {
                        c.loadFromString(new String(in.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
                    }
                }
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        config = c;
    }

    public void saveConfig() {
        try {
            getConfig().save(new File(dataFolder, "config.yml"));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    public void saveDefaultConfig() {
        File f = new File(dataFolder, "config.yml");
        if (f.exists()) {
            return;
        }
        try (InputStream in = getClass().getClassLoader().getResourceAsStream("config.yml")) {
            if (in != null) {
                Files.createDirectories(dataFolder.toPath());
                Files.write(f.toPath(), in.readAllBytes());
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    @Override
    public void onEnable() {
    }

    @Override
    public void onDisable() {
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        return false;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        return null;
    }
}
