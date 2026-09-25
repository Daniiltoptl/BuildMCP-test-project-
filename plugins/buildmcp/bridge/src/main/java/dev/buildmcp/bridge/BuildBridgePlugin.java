package dev.buildmcp.bridge;

import java.io.File;
import java.io.IOException;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Locale;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.command.PluginCommand;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

/**
 * BuildBridge: lets BuildMCP (Claude) paste builds 1:1 (no physics, exact block states, NBT,
 * entities, biomes), back up and undo, read the world and see where players stand.
 */
public final class BuildBridgePlugin extends JavaPlugin {
    private static final String PREFIX = "§b[BuildBridge]§r ";

    private volatile BridgeConfig config;
    private JobManager jobs;
    private Backups backups;
    private HttpApi http;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        ensureToken();
        config = BridgeConfig.from(getConfig());
        backups = new Backups(new File(getDataFolder(), "backups"), config.keepBackups(), getLogger());
        jobs = new JobManager(this);
        jobs.start();
        startHttp();
        PluginCommand cmd = getCommand("buildbridge");
        if (cmd != null) {
            cmd.setExecutor(this);
            cmd.setTabCompleter(this);
        }
    }

    @Override
    public void onDisable() {
        if (http != null) {
            http.stop();
            http = null;
        }
        if (jobs != null) {
            jobs.stop();
        }
    }

    private void ensureToken() {
        String token = getConfig().getString("token", "");
        if (token == null || token.isBlank() || token.equals("change-me")) {
            byte[] raw = new byte[24];
            new SecureRandom().nextBytes(raw);
            getConfig().set("token", Base64.getUrlEncoder().withoutPadding().encodeToString(raw));
            saveConfig();
            getLogger().info("Generated a new access token in plugins/BuildBridge/config.yml");
        }
    }

    private void startHttp() {
        http = new HttpApi(this);
        try {
            http.start();
            getLogger().info("BuildBridge API listening on http://" + config.bind() + ":" + config.port() + "/v1/");
        } catch (IOException e) {
            http = null;
            getLogger().severe("Could not start the BuildBridge API on " + config.bind() + ":" + config.port() + ": "
                    + e.getMessage() + " (change 'port' in config.yml and run /bb reload)");
        }
    }

    // --------------------------------------------------------------- accessors
    BridgeConfig config() {
        return config;
    }

    JobManager jobs() {
        return jobs;
    }

    Backups backups() {
        return backups;
    }

    @SuppressWarnings("deprecation")
    String version() {
        return getDescription().getVersion();
    }

    @SuppressWarnings("deprecation")
    static int dataVersion() {
        return Bukkit.getUnsafe().getDataVersion();
    }

    static String minecraftVersion() {
        try {
            return Bukkit.getMinecraftVersion();
        } catch (NoSuchMethodError e) {
            String v = Bukkit.getBukkitVersion();
            int dash = v.indexOf('-');
            return dash > 0 ? v.substring(0, dash) : v;
        }
    }

    /** Main thread. */
    JsonObject statusJson() {
        JsonObject o = new JsonObject();
        o.addProperty("plugin", "BuildBridge");
        o.addProperty("version", version());
        o.addProperty("server", Bukkit.getName() + " " + Bukkit.getVersion());
        o.addProperty("minecraft", minecraftVersion());
        o.addProperty("data_version", dataVersion());
        try {
            double[] tps = Bukkit.getTPS();
            o.add("tps", Json.arr(Math.round(tps[0] * 100) / 100.0, Math.round(tps[1] * 100) / 100.0,
                    Math.round(tps[2] * 100) / 100.0));
        } catch (NoSuchMethodError ignored) {
            // not Paper
        }
        JsonArray worlds = new JsonArray();
        for (World w : Bukkit.getWorlds()) {
            JsonObject wo = new JsonObject();
            wo.addProperty("name", w.getName());
            wo.addProperty("key", w.getKey().toString());
            wo.addProperty("environment", w.getEnvironment().name().toLowerCase(Locale.ROOT));
            wo.addProperty("min_y", w.getMinHeight());
            wo.addProperty("max_y", w.getMaxHeight() - 1);
            Location s = w.getSpawnLocation();
            wo.add("spawn", Json.arr(s.getX(), s.getY(), s.getZ()));
            worlds.add(wo);
        }
        o.add("worlds", worlds);
        JsonArray players = new JsonArray();
        for (Player p : Bukkit.getOnlinePlayers()) {
            players.add(HttpApi.playerJson(p));
        }
        o.add("players", players);
        String we = WorldEditHook.name();
        if (we != null) {
            o.addProperty("worldedit", we);
        }
        Job cur = jobs.current();
        if (cur != null) {
            o.add("current_job", cur.toJson());
        }
        o.addProperty("queued_jobs", jobs.queued());
        o.addProperty("backups", backups.list().size());
        o.addProperty("max_tick_millis", config.maxTickMillis());
        return o;
    }

    /** Any thread: starts an undo job for a backup id ("last" = newest not undone). */
    Job startUndo(String id) throws Exception {
        Backups.Entry e = id == null || id.isBlank() || id.equals("last") ? backups.latest() : backups.get(id);
        if (e == null) {
            throw new ApiError(404, id == null || id.equals("last") ? "no backup to undo" : "no backup " + id);
        }
        if (e.undone()) {
            throw new ApiError(409, "backup " + e.id() + " was already undone");
        }
        Bundle b = backups.read(e, config.maxCells());
        World w = Sync.call(this, () -> HttpApi.world(e.world()));
        PasteJob job = new PasteJob(this, b, w, e.min()[0], e.min()[1], e.min()[2], false, true, e.entityTag(),
                "undo " + e.label(), e.id());
        jobs.submit(job);
        return job;
    }

    /** Main thread, after every job. */
    void onJobFinished(Job j) {
        if (j instanceof PasteJob pj) {
            if (pj.undoOf() != null && j.error == null) {
                backups.setUndone(pj.undoOf(), true);
            }
            String what = pj.undoOf() != null ? "Отмена" : "Вставка";
            String msg;
            if (j.error == null) {
                msg = PREFIX + what + " «" + j.label + "» готова: " + pj.placed() + " блоков за "
                        + String.format(Locale.ROOT, "%.1f", (j.finished - j.started) / 1000.0) + " с."
                        + (pj.backupId() != null ? " Отменить: /bb undo " + pj.backupId() : "");
            } else {
                msg = PREFIX + "§c" + what + " «" + j.label + "» не удалась: " + j.error;
            }
            for (Player p : Bukkit.getOnlinePlayers()) {
                if (p.hasPermission("buildbridge.notify")) {
                    p.sendMessage(msg);
                }
            }
            getLogger().info(msg.replaceAll("§.", ""));
        }
    }

    // ---------------------------------------------------------------- command
    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        String sub = args.length == 0 ? "status" : args[0].toLowerCase(Locale.ROOT);
        switch (sub) {
            case "status" -> {
                sender.sendMessage(PREFIX + "v" + version() + ", API "
                        + (http != null ? "http://" + config.bind() + ":" + config.port() + "/v1/" : "§cне запущен"));
                Job cur = jobs.current();
                sender.sendMessage(cur == null ? PREFIX + "Нет активных задач."
                        : PREFIX + "Задача " + cur.id + " (" + cur.label + "): " + cur.phase + " " + cur.done + "/" + cur.total);
                sender.sendMessage(PREFIX + "В очереди: " + jobs.queued() + ", бэкапов: " + backups.list().size());
            }
            case "jobs" -> {
                List<Job> list = jobs.list();
                if (list.isEmpty()) {
                    sender.sendMessage(PREFIX + "Задач ещё не было.");
                }
                for (Job j : list.subList(Math.max(0, list.size() - 10), list.size())) {
                    sender.sendMessage(PREFIX + j.id + " " + j.label + ": " + j.phase + (j.error != null ? " (" + j.error + ")" : ""));
                }
            }
            case "cancel" -> {
                Job cur = args.length > 1 ? jobs.get(args[1]) : jobs.current();
                if (cur == null || !jobs.cancel(cur.id)) {
                    sender.sendMessage(PREFIX + "Нечего отменять.");
                } else {
                    sender.sendMessage(PREFIX + "Отменяю " + cur.id + ". Уже вставленное останется, откат: /bb undo");
                }
            }
            case "backups" -> {
                List<Backups.Entry> list = backups.list();
                if (list.isEmpty()) {
                    sender.sendMessage(PREFIX + "Бэкапов нет.");
                }
                for (Backups.Entry e : list.subList(Math.max(0, list.size() - 10), list.size())) {
                    sender.sendMessage(PREFIX + e.id() + " " + e.label() + " (" + e.world() + " " + e.min()[0] + ","
                            + e.min()[1] + "," + e.min()[2] + ")" + (e.undone() ? " — отменён" : ""));
                }
            }
            case "undo" -> {
                try {
                    Job j = startUndo(args.length > 1 ? args[1] : "last");
                    sender.sendMessage(PREFIX + "Откатываю: " + j.label + " (" + j.id + ")");
                } catch (Exception e) {
                    sender.sendMessage(PREFIX + "§c" + e.getMessage());
                }
            }
            case "token" -> {
                if (sender instanceof ConsoleCommandSender) {
                    sender.sendMessage(PREFIX + "token: " + config.token());
                } else {
                    sender.sendMessage(PREFIX + "Токен виден только в консоли и в plugins/BuildBridge/config.yml.");
                }
            }
            case "reload" -> {
                reloadConfig();
                ensureToken();
                config = BridgeConfig.from(getConfig());
                if (http != null) {
                    http.stop();
                }
                startHttp();
                sender.sendMessage(PREFIX + "Настройки перечитаны.");
            }
            default -> sender.sendMessage(PREFIX + "/bb status | jobs | cancel [id] | backups | undo [id] | token | reload");
        }
        return true;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        List<String> out = new ArrayList<>();
        if (args.length == 1) {
            for (String s : new String[]{"status", "jobs", "cancel", "backups", "undo", "token", "reload"}) {
                if (s.startsWith(args[0].toLowerCase(Locale.ROOT))) {
                    out.add(s);
                }
            }
        } else if (args.length == 2 && args[0].equalsIgnoreCase("undo")) {
            for (Backups.Entry e : backups.list()) {
                if (!e.undone()) {
                    out.add(e.id());
                }
            }
        }
        return out;
    }
}
