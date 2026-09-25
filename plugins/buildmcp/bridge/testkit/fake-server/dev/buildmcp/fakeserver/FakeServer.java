package dev.buildmcp.fakeserver;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.function.Consumer;
import java.util.logging.Logger;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Server;
import org.bukkit.UnsafeValues;
import org.bukkit.World;
import org.bukkit.block.data.BlockData;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.PluginDescriptionFile;
import org.bukkit.plugin.PluginManager;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitScheduler;

/**
 * A tiny stand-in for a Paper 1.21.4 server that runs the real BuildBridge plugin, so its HTTP API,
 * jobs, backups and undo can be tested end to end without Minecraft.
 *
 * <pre>java -cp ... dev.buildmcp.fakeserver.FakeServer --port 8765 --data DIR --token TOKEN</pre>
 *
 * Prints "READY" when the API is up; type "stop" (or close stdin) to shut down.
 */
public final class FakeServer implements Server {
    static final class Stats {
        long blockSets, physicsPlacements, syncChunkLoads, asyncChunkLoads, snapshots, commands;
        int violations;
        String firstViolation;
        long maxTickMicros;
        long maxTaskMicros;
    }

    final Stats stats = new Stats();
    final FakeScheduler scheduler = new FakeScheduler(this);
    final List<FakeWorld> worlds = new ArrayList<>();
    final List<FakePlayer> players = new ArrayList<>();
    final Logger logger = Logger.getLogger("FakeServer");
    volatile long tick;
    volatile boolean running = true;
    Thread mainThread;
    JavaPlugin plugin;

    public static void main(String[] args) throws Exception {
        Map<String, String> opt = new LinkedHashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2) {
            opt.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        }
        int port = Integer.parseInt(opt.getOrDefault("port", "8765"));
        File data = new File(opt.getOrDefault("data", "fake-server-data"));
        String token = opt.getOrDefault("token", "test-token");
        FakeServer s = new FakeServer();
        Bukkit.setServer(s);
        s.worlds.add(new FakeWorld(s, "world", "minecraft:overworld", World.Environment.NORMAL, -64, 320));
        s.worlds.add(new FakeWorld(s, "world_nether", "minecraft:the_nether", World.Environment.NETHER, 0, 256));
        s.players.add(new FakePlayer(s, "Steve", new Location(s.worlds.get(0), 0.5, 64, 0.5, 0f, 30f)));

        File pluginDir = new File(data, "BuildBridge");
        Files.createDirectories(pluginDir.toPath());
        String config = "bind: 127.0.0.1\nport: " + port + "\ntoken: \"" + token + "\"\nallowed-ips: []\n"
                + "max-tick-millis: 20\nmax-upload-mb: 64\nmax-cells: 5000000\nbackups:\n  enabled: true\n  keep: 5\n";
        Files.writeString(new File(pluginDir, "config.yml").toPath(), config, StandardCharsets.UTF_8);

        JavaPlugin p = (JavaPlugin) Class.forName("dev.buildmcp.bridge.BuildBridgePlugin").getDeclaredConstructor().newInstance();
        p.testkitInit(pluginDir, new PluginDescriptionFile("BuildBridge", "0.1.0-test", "dev.buildmcp.bridge.BuildBridgePlugin"),
                List.of("buildbridge"));
        s.plugin = p;

        CountDownLatch ready = new CountDownLatch(1);
        s.mainThread = new Thread(() -> s.loop(ready), "Server thread");
        s.mainThread.start();
        s.scheduler.runTask(p, () -> {
            p.testkitSetEnabled(true);
            ready.countDown();
        });
        ready.await();
        s.stats.maxTickMicros = 0;
        s.stats.maxTaskMicros = 0;
        System.out.println("READY " + port);
        System.out.flush();

        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            if (line.strip().equals("stop")) {
                break;
            }
        }
        CountDownLatch stopped = new CountDownLatch(1);
        s.scheduler.runTask(p, () -> {
            p.testkitSetEnabled(false);
            stopped.countDown();
        });
        stopped.await();
        s.running = false;
        s.mainThread.join(5000);
        s.scheduler.shutdown();
        System.out.println("STOPPED");
        System.exit(0);
    }

    private void loop(CountDownLatch ready) {
        while (running) {
            long start = System.nanoTime();
            tick++;
            scheduler.tick();
            for (FakeWorld w : worlds) {
                w.tick();
            }
            long took = (System.nanoTime() - start) / 1000;
            if (ready.getCount() == 0 && took > stats.maxTickMicros) {
                stats.maxTickMicros = took;
            }
            long sleep = 50 - took / 1000;
            if (sleep > 0) {
                try {
                    Thread.sleep(sleep);
                } catch (InterruptedException e) {
                    return;
                }
            }
        }
    }

    void checkMain(String what) {
        if (Thread.currentThread() != mainThread) {
            stats.violations++;
            if (stats.firstViolation == null) {
                stats.firstViolation = what + " from " + Thread.currentThread().getName();
            }
            throw new IllegalStateException("Asynchronous " + what + "!");
        }
    }

    static String plain(Component c) {
        return PlainTextComponentSerializer.plainText().serialize(c);
    }

    FakeWorld worldByKey(String key) {
        for (FakeWorld w : worlds) {
            if (w.key.toString().equals(key) || w.name.equals(key)) {
                return w;
            }
        }
        return null;
    }

    // ------------------------------------------------------------------ Server
    @Override
    public String getName() {
        return "FakePaper";
    }

    @Override
    public String getVersion() {
        return "fake-1 (MC: 1.21.4)";
    }

    @Override
    public String getBukkitVersion() {
        return "1.21.4-R0.1-SNAPSHOT";
    }

    @Override
    public String getMinecraftVersion() {
        return "1.21.4";
    }

    @Override
    public Logger getLogger() {
        return logger;
    }

    @Override
    public Collection<? extends Player> getOnlinePlayers() {
        return players;
    }

    @Override
    public Player getPlayerExact(String name) {
        for (FakePlayer p : players) {
            if (p.getName().equalsIgnoreCase(name)) {
                return p;
            }
        }
        return null;
    }

    @Override
    public List<World> getWorlds() {
        return new ArrayList<>(worlds);
    }

    @Override
    public World getWorld(String name) {
        for (FakeWorld w : worlds) {
            if (w.name.equals(name)) {
                return w;
            }
        }
        return null;
    }

    @Override
    public BukkitScheduler getScheduler() {
        return scheduler;
    }

    @Override
    public PluginManager getPluginManager() {
        return new PluginManager() {
            @Override
            public Plugin getPlugin(String name) {
                return name.equals("BuildBridge") ? plugin : null;
            }

            @Override
            public boolean isPluginEnabled(String name) {
                return name.equals("BuildBridge") && plugin.isEnabled();
            }
        };
    }

    @Override
    public BlockData createBlockData(String data) {
        return FakeBlockData.parse(data);
    }

    @Override
    public UnsafeValues getUnsafe() {
        return () -> 4189;
    }

    @Override
    public double[] getTPS() {
        return new double[]{20.0, 20.0, 20.0};
    }

    @Override
    public CommandSender createCommandSender(Consumer<? super Component> feedback) {
        return new FakeSender(feedback);
    }

    @Override
    public ConsoleCommandSender getConsoleSender() {
        return new FakeSender(null);
    }

    @Override
    public boolean isPrimaryThread() {
        return Thread.currentThread() == mainThread;
    }

    @Override
    public boolean dispatchCommand(CommandSender sender, String commandLine) {
        checkMain("dispatchCommand");
        stats.commands++;
        Commands.Ctx ctx = new Commands.Ctx(this, sender, worlds.get(0));
        return Commands.run(ctx, commandLine.strip());
    }

    void reply(CommandSender sender, Component c) {
        if (sender instanceof FakeSender fs) {
            fs.feedback(c);
        } else {
            sender.sendMessage(plain(c));
        }
    }

    FakeEntity spawn(FakeWorld w, EntityType type, double x, double y, double z, String content) {
        FakeEntity e = new FakeEntity(this, type, new Location(w, x, y, z), content);
        e.tags.addAll(Snbt.tags(content));
        w.entities.add(e);
        return e;
    }

    FakeEntity entity(UUID id) {
        for (FakeWorld w : worlds) {
            for (FakeEntity e : w.entities) {
                if (e.uuid.equals(id)) {
                    return e;
                }
            }
        }
        return null;
    }

    String statsLine() {
        int tickets = 0, entities = 0, tiles = 0;
        for (FakeWorld w : worlds) {
            tickets += w.ticketCount();
            entities += w.entities.size();
            for (FakeWorld.FakeData d : w.data.values()) {
                tiles += d.tiles.size();
            }
        }
        return String.format(Locale.ROOT,
                "tickets=%d entities=%d tiles=%d block_sets=%d physics=%d sync_loads=%d async_loads=%d snapshots=%d "
                        + "violations=%d max_tick_ms=%.1f max_task_ms=%.1f first_violation=%s",
                tickets, entities, tiles, stats.blockSets, stats.physicsPlacements, stats.syncChunkLoads,
                stats.asyncChunkLoads, stats.snapshots, stats.violations, stats.maxTickMicros / 1000.0, stats.maxTaskMicros / 1000.0,
                stats.firstViolation == null ? "-" : stats.firstViolation.replace(' ', '_'));
    }
}
