package org.bukkit.plugin;

public final class PluginDescriptionFile {
    private final String name;
    private final String version;

    public PluginDescriptionFile(String name, String version, String mainClass) {
        this.name = name;
        this.version = version;
    }

    public String getName() {
        return name;
    }

    public String getVersion() {
        return version;
    }
}
