package dev.buildmcp.bridge;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.entity.Player;

/**
 * The HTTP API BuildMCP talks to. Every endpoint except /v1/ping needs "Authorization: Bearer TOKEN".
 * Handlers run on HTTP threads and hop to the main thread for anything that touches the world.
 */
final class HttpApi {
    private static final long WAIT_MS = 15 * 60 * 1000L;

    private final BuildBridgePlugin plugin;
    private HttpServer server;
    private ExecutorService pool;

    HttpApi(BuildBridgePlugin plugin) {
        this.plugin = plugin;
    }

    void start() throws IOException {
        BridgeConfig c = plugin.config();
        server = HttpServer.create(new InetSocketAddress(InetAddress.getByName(c.bind()), c.port()), 32);
        AtomicInteger n = new AtomicInteger();
        pool = Executors.newFixedThreadPool(4, r -> {
            Thread t = new Thread(r, "BuildBridge-HTTP-" + n.incrementAndGet());
            t.setDaemon(true);
            return t;
        });
        server.setExecutor(pool);
        server.createContext("/", this::handle);
        server.start();
    }

    void stop() {
        if (server != null) {
            server.stop(0);
            server = null;
        }
        if (pool != null) {
            pool.shutdownNow();
            pool = null;
        }
    }

    // --------------------------------------------------------------- plumbing
    private void handle(HttpExchange ex) {
        try {
            String path = ex.getRequestURI().getPath();
            String method = ex.getRequestMethod();
            if (!ipAllowed(ex)) {
                send(ex, 403, Json.error("this IP is not in allowed-ips"));
                return;
            }
            if (path.equals("/v1/ping")) {
                JsonObject o = new JsonObject();
                o.addProperty("ok", true);
                o.addProperty("plugin", "BuildBridge");
                o.addProperty("version", plugin.version());
                send(ex, 200, o);
                return;
            }
            if (!authorized(ex)) {
                send(ex, 401, Json.error("missing or wrong token: use the token from plugins/BuildBridge/config.yml"));
                return;
            }
            route(ex, method, path);
        } catch (ApiError e) {
            sendQuietly(ex, e.status, Json.error(e.getMessage()));
        } catch (Throwable t) {
            plugin.getLogger().log(Level.WARNING, "BuildBridge API error", t);
            sendQuietly(ex, 500, Json.error(t.getClass().getSimpleName() + ": " + t.getMessage()));
        } finally {
            ex.close();
        }
    }

    private boolean ipAllowed(HttpExchange ex) {
        List<String> allowed = plugin.config().allowedIps();
        if (allowed == null || allowed.isEmpty()) {
            return true;
        }
        String ip = ex.getRemoteAddress().getAddress().getHostAddress();
        return allowed.contains(ip);
    }

    private boolean authorized(HttpExchange ex) {
        String token = plugin.config().token();
        String h = ex.getRequestHeaders().getFirst("Authorization");
        if (token == null || token.isBlank() || h == null || !h.startsWith("Bearer ")) {
            return false;
        }
        byte[] a = h.substring(7).trim().getBytes(StandardCharsets.UTF_8);
        byte[] b = token.getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(a, b);
    }

    private static void send(HttpExchange ex, int status, JsonElement body) throws IOException {
        byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void sendBytes(HttpExchange ex, byte[] bytes, String type) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(200, bytes.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(bytes);
        }
    }

    private void sendQuietly(HttpExchange ex, int status, JsonElement body) {
        try {
            send(ex, status, body);
        } catch (IOException | RuntimeException ignored) {
            // client went away or headers were already sent
        }
    }

    private byte[] body(HttpExchange ex) throws IOException {
        long limit = plugin.config().maxUploadBytes();
        try (InputStream in = ex.getRequestBody()) {
            byte[] data = in.readNBytes((int) Math.min(Integer.MAX_VALUE - 16, limit + 1));
            if (data.length > limit) {
                throw new ApiError(413, "upload larger than max-upload-mb");
            }
            return data;
        }
    }

    private JsonObject jsonBody(HttpExchange ex) throws IOException {
        byte[] b = body(ex);
        if (b.length == 0) {
            return new JsonObject();
        }
        JsonElement e = JsonParser.parseString(new String(b, StandardCharsets.UTF_8));
        if (!e.isJsonObject()) {
            throw new ApiError(400, "expected a JSON object");
        }
        return e.getAsJsonObject();
    }

    private static void expect(String method, String want) {
        if (!method.equalsIgnoreCase(want)) {
            throw new ApiError(405, "use " + want);
        }
    }

    // ----------------------------------------------------------------- routes
    private void route(HttpExchange ex, String method, String path) throws Exception {
        String[] p = path.replaceAll("/+$", "").split("/");
        // p[0] = "", p[1] = "v1"
        if (p.length < 3 || !p[1].equals("v1")) {
            throw new ApiError(404, "unknown endpoint " + path);
        }
        switch (p[2]) {
            case "status" -> send(ex, 200, Sync.call(plugin, plugin::statusJson));
            case "players" -> {
                if (p.length == 3) {
                    send(ex, 200, Sync.call(plugin, this::playersJson));
                } else {
                    String name = URLDecoder.decode(p[3], StandardCharsets.UTF_8);
                    send(ex, 200, Sync.call(plugin, () -> playerJson(findPlayer(name))));
                }
            }
            case "paste" -> {
                expect(method, "POST");
                send(ex, 200, paste(body(ex)));
            }
            case "jobs" -> {
                if (p.length == 3) {
                    JsonArray a = new JsonArray();
                    for (Job j : plugin.jobs().list()) {
                        a.add(j.toJson());
                    }
                    JsonObject o = new JsonObject();
                    o.add("jobs", a);
                    send(ex, 200, o);
                } else {
                    Job j = plugin.jobs().get(p[3]);
                    if (j == null) {
                        throw new ApiError(404, "no job " + p[3]);
                    }
                    if (p.length > 4 && p[4].equals("cancel")) {
                        expect(method, "POST");
                        plugin.jobs().cancel(j.id);
                    }
                    send(ex, 200, j.toJson());
                }
            }
            case "backups" -> {
                JsonArray a = new JsonArray();
                for (Backups.Entry e : plugin.backups().list()) {
                    a.add(e.toJson());
                }
                JsonObject o = new JsonObject();
                o.add("backups", a);
                send(ex, 200, o);
            }
            case "undo" -> {
                expect(method, "POST");
                JsonObject req = jsonBody(ex);
                Job j = plugin.startUndo(Json.str(req, "backup", "last"));
                JsonObject o = j.toJson();
                o.addProperty("job", j.id);
                send(ex, 200, o);
            }
            case "region" -> {
                expect(method, "POST");
                JsonObject req = jsonBody(ex);
                World w = Sync.call(plugin, () -> world(Json.str(req, "world", null)));
                ReadJob job = new ReadJob(plugin, w, Json.ints(req, "box", 6), Json.bool(req, "tiles", true),
                        Json.bool(req, "entities", true));
                plugin.jobs().submit(job);
                job.await(WAIT_MS);
                sendBytes(ex, job.result().toBytes(), "application/octet-stream");
            }
            case "heightmap" -> {
                expect(method, "POST");
                JsonObject req = jsonBody(ex);
                World w = Sync.call(plugin, () -> world(Json.str(req, "world", null)));
                HeightmapJob job = new HeightmapJob(plugin, w, Json.ints(req, "rect", 4));
                plugin.jobs().submit(job);
                job.await(WAIT_MS);
                send(ex, 200, job.resultJson());
            }
            case "command" -> {
                expect(method, "POST");
                JsonObject req = jsonBody(ex);
                String cmd = Json.str(req, "command", "").trim();
                if (cmd.isEmpty()) {
                    throw new ApiError(400, "empty command");
                }
                String worldName = Json.str(req, "world", null);
                JsonObject out = Sync.call(plugin, () -> {
                    Capture.Result r = worldName == null ? Capture.run(cmd) : Capture.runIn(world(worldName), cmd);
                    JsonObject o = new JsonObject();
                    o.addProperty("dispatched", r.dispatched());
                    o.add("output", Json.strings(r.lines()));
                    return o;
                });
                send(ex, 200, out);
            }
            case "teleport" -> {
                expect(method, "POST");
                JsonObject req = jsonBody(ex);
                send(ex, 200, Sync.call(plugin, () -> teleport(req)));
            }
            default -> throw new ApiError(404, "unknown endpoint " + path);
        }
    }

    // --------------------------------------------------------------- handlers
    private JsonObject paste(byte[] body) throws Exception {
        Bundle b = Bundle.read(body, plugin.config().maxCells());
        JsonObject h = b.header;
        int[] min = Json.ints(h, "min", 3);
        String worldName = Json.str(h, "world", null);
        boolean backup = Json.bool(h, "backup", plugin.config().backupsEnabled()) && plugin.config().backupsEnabled();
        boolean compare = Json.bool(h, "compare", true);
        String tag = Json.str(h, "entity_tag", null);
        String label = Json.str(h, "label", "paste");
        World w = Sync.call(plugin, () -> world(worldName));
        PasteJob job = new PasteJob(plugin, b, w, min[0], min[1], min[2], backup, compare, tag, label, null);
        plugin.jobs().submit(job);
        JsonObject o = job.toJson();
        o.addProperty("job", job.id);
        o.addProperty("queue", plugin.jobs().queued());
        return o;
    }

    /** Main thread. */
    static World world(String name) {
        if (name == null || name.isBlank()) {
            return Bukkit.getWorlds().get(0);
        }
        World w = Bukkit.getWorld(name);
        if (w == null) {
            for (World x : Bukkit.getWorlds()) {
                if (x.getKey().toString().equals(name) || x.getKey().getKey().equals(name)) {
                    return x;
                }
            }
            throw new ApiError(404, "no world '" + name + "'");
        }
        return w;
    }

    /** Main thread. Empty name = the only/first online player. */
    static Player findPlayer(String name) {
        if (name == null || name.isBlank() || name.equals("@")) {
            for (Player p : Bukkit.getOnlinePlayers()) {
                return p;
            }
            throw new ApiError(404, "nobody is online");
        }
        Player p = Bukkit.getPlayerExact(name);
        if (p == null) {
            throw new ApiError(404, "player '" + name + "' is not online");
        }
        return p;
    }

    private JsonObject playersJson() {
        JsonArray a = new JsonArray();
        for (Player p : Bukkit.getOnlinePlayers()) {
            a.add(playerJson(p));
        }
        JsonObject o = new JsonObject();
        o.add("players", a);
        return o;
    }

    static JsonObject playerJson(Player p) {
        JsonObject o = new JsonObject();
        Location l = p.getLocation();
        o.addProperty("name", p.getName());
        o.addProperty("uuid", p.getUniqueId().toString());
        o.addProperty("world", l.getWorld() != null ? l.getWorld().getName() : null);
        o.add("pos", Json.arr(l.getX(), l.getY(), l.getZ()));
        o.add("block", Json.arr(l.getBlockX(), l.getBlockY(), l.getBlockZ()));
        o.addProperty("yaw", l.getYaw());
        o.addProperty("pitch", l.getPitch());
        GameMode gm = p.getGameMode();
        o.addProperty("gamemode", gm.name().toLowerCase(java.util.Locale.ROOT));
        Block target = p.getTargetBlockExact(160);
        if (target != null) {
            o.add("target", Json.arr(target.getX(), target.getY(), target.getZ()));
            o.addProperty("target_block", target.getBlockData().getAsString());
        }
        int[] sel = WorldEditHook.selection(p);
        if (sel != null) {
            o.add("selection", Json.arr(sel));
        }
        return o;
    }

    private JsonObject teleport(JsonObject req) {
        Player p = findPlayer(Json.str(req, "player", ""));
        String worldName = Json.str(req, "world", null);
        World w = worldName == null ? p.getWorld() : world(worldName);
        double[] pos = Json.doubles(req, "pos", 3);
        Location cur = p.getLocation();
        float yaw = (float) Json.num(req, "yaw", cur.getYaw());
        float pitch = (float) Json.num(req, "pitch", cur.getPitch());
        boolean ok = p.teleport(new Location(w, pos[0], pos[1], pos[2], yaw, pitch));
        JsonObject o = playerJson(p);
        o.addProperty("ok", ok);
        return o;
    }
}
