package org.bukkit.configuration.file;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Test kit: a map-backed configuration with dotted paths. */
public abstract class FileConfiguration {
    protected final Map<String, Object> root = new LinkedHashMap<>();

    public abstract void save(File file) throws IOException;

    @SuppressWarnings("unchecked")
    public Object get(String path) {
        Object cur = root;
        for (String part : path.split("\\.")) {
            if (!(cur instanceof Map)) {
                return null;
            }
            cur = ((Map<String, Object>) cur).get(part);
        }
        return cur;
    }

    @SuppressWarnings("unchecked")
    public void set(String path, Object value) {
        String[] parts = path.split("\\.");
        Map<String, Object> cur = root;
        for (int i = 0; i < parts.length - 1; i++) {
            Object next = cur.get(parts[i]);
            if (!(next instanceof Map)) {
                next = new LinkedHashMap<String, Object>();
                cur.put(parts[i], next);
            }
            cur = (Map<String, Object>) next;
        }
        cur.put(parts[parts.length - 1], value);
    }

    public String getString(String path) {
        return getString(path, null);
    }

    public String getString(String path, String def) {
        Object v = get(path);
        return v == null ? def : String.valueOf(v);
    }

    public int getInt(String path, int def) {
        Object v = get(path);
        return v instanceof Number n ? n.intValue() : v != null ? Integer.parseInt(v.toString()) : def;
    }

    public long getLong(String path, long def) {
        Object v = get(path);
        return v instanceof Number n ? n.longValue() : v != null ? Long.parseLong(v.toString()) : def;
    }

    public boolean getBoolean(String path, boolean def) {
        Object v = get(path);
        return v instanceof Boolean b ? b : v != null ? Boolean.parseBoolean(v.toString()) : def;
    }

    public List<String> getStringList(String path) {
        Object v = get(path);
        List<String> out = new ArrayList<>();
        if (v instanceof List<?> l) {
            for (Object o : l) {
                out.add(String.valueOf(o));
            }
        }
        return out;
    }
}
