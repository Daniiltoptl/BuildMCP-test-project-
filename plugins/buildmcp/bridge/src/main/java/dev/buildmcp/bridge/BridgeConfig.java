package dev.buildmcp.bridge;

import java.util.List;

import org.bukkit.configuration.file.FileConfiguration;

/** Settings from config.yml. */
record BridgeConfig(String bind, int port, String token, List<String> allowedIps, int maxTickMillis,
                    long maxUploadBytes, long maxCells, boolean backupsEnabled, int keepBackups) {

    static BridgeConfig from(FileConfiguration c) {
        return new BridgeConfig(
                c.getString("bind", "127.0.0.1"),
                c.getInt("port", 8765),
                c.getString("token", ""),
                c.getStringList("allowed-ips"),
                Math.max(1, Math.min(45, c.getInt("max-tick-millis", 20))),
                Math.max(1, c.getInt("max-upload-mb", 512)) * 1024L * 1024L,
                Math.max(1, c.getLong("max-cells", 50_000_000L)),
                c.getBoolean("backups.enabled", true),
                Math.max(1, c.getInt("backups.keep", 30)));
    }
}
