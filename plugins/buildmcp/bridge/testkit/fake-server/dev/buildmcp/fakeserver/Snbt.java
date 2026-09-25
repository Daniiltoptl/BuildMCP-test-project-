package dev.buildmcp.fakeserver;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Just enough SNBT handling for the fake server: validation, top-level keys, merge, Tags. */
final class Snbt {
    private Snbt() {}

    /** Checks brackets and quotes; throws IllegalArgumentException like the game's parser would. */
    static void validate(String s) {
        String t = s.strip();
        if (!t.startsWith("{") || !t.endsWith("}")) {
            throw new IllegalArgumentException("Expected '{' at position 0: " + t);
        }
        int depth = 0;
        char quote = 0;
        for (int i = 0; i < t.length(); i++) {
            char c = t.charAt(i);
            if (quote != 0) {
                if (c == '\\') {
                    i++;
                } else if (c == quote) {
                    quote = 0;
                }
                continue;
            }
            if (c == '"' || c == '\'') {
                quote = c;
            } else if (c == '{' || c == '[') {
                depth++;
            } else if (c == '}' || c == ']') {
                depth--;
                if (depth < 0) {
                    throw new IllegalArgumentException("Unbalanced brackets at " + i);
                }
            }
        }
        if (depth != 0 || quote != 0) {
            throw new IllegalArgumentException("Unexpected end of NBT");
        }
    }

    /** Top-level "key: value" pairs of a compound (values kept as raw text). */
    static Map<String, String> entries(String s) {
        Map<String, String> out = new LinkedHashMap<>();
        String t = s.strip();
        if (t.startsWith("{") && t.endsWith("}")) {
            t = t.substring(1, t.length() - 1);
        }
        for (String part : splitTop(t)) {
            if (part.isBlank()) {
                continue;
            }
            int c = keyEnd(part);
            String key = part.substring(0, c).strip();
            if (key.startsWith("\"") && key.endsWith("\"") && key.length() >= 2) {
                key = key.substring(1, key.length() - 1);
            }
            out.put(key, part.substring(c + 1).strip());
        }
        return out;
    }

    private static int keyEnd(String part) {
        char quote = 0;
        for (int i = 0; i < part.length(); i++) {
            char c = part.charAt(i);
            if (quote != 0) {
                if (c == quote) {
                    quote = 0;
                }
            } else if (c == '"' || c == '\'') {
                quote = c;
            } else if (c == ':') {
                return i;
            }
        }
        throw new IllegalArgumentException("Expected key: " + part);
    }

    private static List<String> splitTop(String s) {
        List<String> out = new ArrayList<>();
        int depth = 0, start = 0;
        char quote = 0;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (quote != 0) {
                if (c == '\\') {
                    i++;
                } else if (c == quote) {
                    quote = 0;
                }
                continue;
            }
            if (c == '"' || c == '\'') {
                quote = c;
            } else if (c == '{' || c == '[') {
                depth++;
            } else if (c == '}' || c == ']') {
                depth--;
            } else if (c == ',' && depth == 0) {
                out.add(s.substring(start, i));
                start = i + 1;
            }
        }
        out.add(s.substring(start));
        return out;
    }

    static String join(Map<String, String> m) {
        StringBuilder sb = new StringBuilder("{");
        for (Map.Entry<String, String> e : m.entrySet()) {
            if (sb.length() > 1) {
                sb.append(", ");
            }
            sb.append(e.getKey()).append(": ").append(e.getValue());
        }
        return sb.append('}').toString();
    }

    static List<String> tags(String snbt) {
        List<String> out = new ArrayList<>();
        if (snbt == null || snbt.isBlank()) {
            return out;
        }
        String v = entries(snbt).get("Tags");
        if (v == null) {
            return out;
        }
        v = v.strip();
        if (v.startsWith("[") && v.endsWith("]")) {
            for (String part : splitTop(v.substring(1, v.length() - 1))) {
                String p = part.strip();
                if (p.length() >= 2 && (p.startsWith("\"") || p.startsWith("'"))) {
                    p = p.substring(1, p.length() - 1);
                }
                if (!p.isEmpty()) {
                    out.add(p);
                }
            }
        }
        return out;
    }
}
