package dev.buildmcp.bridge;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Logger;
import java.util.zip.GZIPInputStream;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

/** Backups of pasted areas (what was there before), for undo. Stored as bundles in plugins/BuildBridge/backups. */
final class Backups {
    record Entry(String id, String label, String world, int[] min, int[] size, long created, String job,
                 String entityTag, long cells, boolean undone, long bytes) {
        JsonObject toJson() {
            JsonObject o = new JsonObject();
            o.addProperty("id", id);
            o.addProperty("label", label);
            o.addProperty("world", world);
            o.add("min", Json.arr(min));
            o.add("size", Json.arr(size));
            o.addProperty("created", created);
            o.addProperty("job", job);
            if (entityTag != null) {
                o.addProperty("entity_tag", entityTag);
            }
            o.addProperty("cells", cells);
            o.addProperty("undone", undone);
            o.addProperty("bytes", bytes);
            return o;
        }

        static Entry fromJson(JsonObject o) {
            return new Entry(o.get("id").getAsString(), Json.str(o, "label", ""), o.get("world").getAsString(),
                    Json.ints(o, "min", 3), Json.ints(o, "size", 3), o.get("created").getAsLong(),
                    Json.str(o, "job", ""), Json.str(o, "entity_tag", null), (long) Json.num(o, "cells", 0),
                    Json.bool(o, "undone", false), (long) Json.num(o, "bytes", 0));
        }

        Entry withUndone(boolean u) {
            return new Entry(id, label, world, min, size, created, job, entityTag, cells, u, bytes);
        }
    }

    private final File dir;
    private final int keep;
    private final Logger log;
    private final List<Entry> entries = new ArrayList<>();
    private final Gson gson = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();

    Backups(File dir, int keep, Logger log) {
        this.dir = dir;
        this.keep = keep;
        this.log = log;
        load();
    }

    private File index() {
        return new File(dir, "index.json");
    }

    private synchronized void load() {
        entries.clear();
        File f = index();
        if (!f.exists()) {
            return;
        }
        try {
            JsonElement root = JsonParser.parseString(Files.readString(f.toPath(), StandardCharsets.UTF_8));
            for (JsonElement e : root.getAsJsonObject().getAsJsonArray("backups")) {
                Entry en = Entry.fromJson(e.getAsJsonObject());
                if (new File(dir, en.id() + ".bmcb").exists()) {
                    entries.add(en);
                }
            }
        } catch (Exception e) {
            log.warning("BuildBridge: could not read backups/index.json: " + e.getMessage());
        }
    }

    private void saveIndex() throws IOException {
        JsonArray a = new JsonArray();
        for (Entry e : entries) {
            a.add(e.toJson());
        }
        JsonObject root = new JsonObject();
        root.add("backups", a);
        File tmp = new File(dir, "index.json.tmp");
        Files.writeString(tmp.toPath(), gson.toJson(root), StandardCharsets.UTF_8);
        try {
            Files.move(tmp.toPath(), index().toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            Files.move(tmp.toPath(), index().toPath(), StandardCopyOption.REPLACE_EXISTING);
        }
    }

    /** Writes a backup bundle (any thread). */
    synchronized Entry save(Bundle bundle, String world, int[] min, String label, String job, String entityTag,
                            long cells) throws IOException {
        if (!dir.isDirectory() && !dir.mkdirs()) {
            throw new IOException("cannot create " + dir);
        }
        String id = "b" + Long.toString(System.currentTimeMillis(), 36);
        while (new File(dir, id + ".bmcb").exists()) {
            id = id + "x";
        }
        File f = new File(dir, id + ".bmcb");
        try (OutputStream out = Files.newOutputStream(f.toPath())) {
            bundle.write(out);
        }
        Entry e = new Entry(id, label, world, min, new int[]{bundle.w, bundle.h, bundle.l}, System.currentTimeMillis(),
                job, entityTag, cells, false, f.length());
        entries.add(e);
        while (entries.size() > keep) {
            Entry old = entries.remove(0);
            File of = new File(dir, old.id() + ".bmcb");
            if (!of.delete() && of.exists()) {
                log.warning("BuildBridge: could not delete old backup " + of);
            }
        }
        saveIndex();
        return e;
    }

    synchronized List<Entry> list() {
        return new ArrayList<>(entries);
    }

    synchronized Entry get(String id) {
        for (Entry e : entries) {
            if (e.id().equals(id)) {
                return e;
            }
        }
        return null;
    }

    /** Newest backup that has not been undone yet. */
    synchronized Entry latest() {
        for (int i = entries.size() - 1; i >= 0; i--) {
            if (!entries.get(i).undone()) {
                return entries.get(i);
            }
        }
        return null;
    }

    synchronized void setUndone(String id, boolean undone) {
        for (int i = 0; i < entries.size(); i++) {
            if (entries.get(i).id().equals(id)) {
                entries.set(i, entries.get(i).withUndone(undone));
            }
        }
        try {
            saveIndex();
        } catch (IOException e) {
            log.warning("BuildBridge: could not update backups/index.json: " + e.getMessage());
        }
    }

    Bundle read(Entry e, long maxCells) throws IOException {
        File f = new File(dir, e.id() + ".bmcb");
        try (InputStream in = new GZIPInputStream(Files.newInputStream(f.toPath()), 1 << 16)) {
            return Bundle.read(in, maxCells);
        }
    }
}
