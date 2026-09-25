package org.bukkit.configuration.file;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Test kit: enough YAML for BuildBridge's config.yml (maps, scalars, flow/empty lists, "- item" lists). */
public class YamlConfiguration extends FileConfiguration {

    public void load(File file) throws IOException {
        loadFromString(Files.readString(file.toPath(), StandardCharsets.UTF_8));
    }

    @SuppressWarnings("unchecked")
    public void loadFromString(String text) {
        root.clear();
        Deque<Object[]> stack = new ArrayDeque<>(); // {indent, map}
        stack.push(new Object[]{-1, root});
        String lastKey = null;
        Map<String, Object> lastMap = root;
        for (String raw : text.split("\n")) {
            String line = stripComment(raw).replace("\r", "");
            if (line.isBlank()) {
                continue;
            }
            int indent = line.length() - line.stripLeading().length();
            String s = line.strip();
            while (indent <= (int) stack.peek()[0]) {
                stack.pop();
            }
            Map<String, Object> cur = (Map<String, Object>) stack.peek()[1];
            if (s.startsWith("- ")) {
                Object v = lastMap.get(lastKey);
                if (!(v instanceof List)) {
                    v = new ArrayList<>();
                    lastMap.put(lastKey, v);
                }
                ((List<Object>) v).add(scalar(s.substring(2).strip()));
                continue;
            }
            int colon = s.indexOf(':');
            String key = s.substring(0, colon).strip();
            String val = s.substring(colon + 1).strip();
            if (val.isEmpty()) {
                Map<String, Object> child = new LinkedHashMap<>();
                cur.put(key, child);
                stack.push(new Object[]{indent, child});
            } else {
                cur.put(key, scalar(val));
            }
            lastKey = key;
            lastMap = cur;
        }
    }

    private static String stripComment(String line) {
        boolean q1 = false, q2 = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (c == '\'' && !q2) {
                q1 = !q1;
            } else if (c == '"' && !q1) {
                q2 = !q2;
            } else if (c == '#' && !q1 && !q2 && (i == 0 || Character.isWhitespace(line.charAt(i - 1)))) {
                return line.substring(0, i);
            }
        }
        return line;
    }

    private static Object scalar(String v) {
        if (v.equals("[]")) {
            return new ArrayList<>();
        }
        if (v.startsWith("[") && v.endsWith("]")) {
            List<Object> out = new ArrayList<>();
            for (String part : v.substring(1, v.length() - 1).split(",")) {
                if (!part.isBlank()) {
                    out.add(scalar(part.strip()));
                }
            }
            return out;
        }
        if ((v.startsWith("\"") && v.endsWith("\"")) || (v.startsWith("'") && v.endsWith("'"))) {
            return v.substring(1, v.length() - 1);
        }
        if (v.equals("true") || v.equals("false")) {
            return Boolean.parseBoolean(v);
        }
        try {
            return Long.parseLong(v);
        } catch (NumberFormatException e) {
            return v;
        }
    }

    @Override
    public void save(File file) throws IOException {
        StringBuilder sb = new StringBuilder();
        dump(root, 0, sb);
        Files.createDirectories(file.toPath().getParent());
        Files.writeString(file.toPath(), sb.toString(), StandardCharsets.UTF_8);
    }

    @SuppressWarnings("unchecked")
    private static void dump(Map<String, Object> m, int indent, StringBuilder sb) {
        for (Map.Entry<String, Object> e : m.entrySet()) {
            sb.append(" ".repeat(indent)).append(e.getKey()).append(':');
            Object v = e.getValue();
            if (v instanceof Map) {
                sb.append('\n');
                dump((Map<String, Object>) v, indent + 2, sb);
            } else if (v instanceof List<?> l) {
                sb.append(l.isEmpty() ? " []\n" : "\n");
                for (Object o : l) {
                    sb.append(" ".repeat(indent + 2)).append("- ").append(o).append('\n');
                }
            } else if (v instanceof String s) {
                sb.append(" \"").append(s).append("\"\n");
            } else {
                sb.append(' ').append(v).append('\n');
            }
        }
    }
}
