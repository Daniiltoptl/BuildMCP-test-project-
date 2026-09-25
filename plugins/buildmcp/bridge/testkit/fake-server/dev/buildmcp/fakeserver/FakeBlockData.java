package dev.buildmcp.fakeserver;

import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Pattern;

import org.bukkit.block.data.BlockData;

/** Canonical "minecraft:name[a=b,...]" with properties sorted by name, like the game prints them. */
final class FakeBlockData implements BlockData {
    private static final Pattern NAME = Pattern.compile("[a-z0-9_./-]+");
    static final FakeBlockData AIR = new FakeBlockData("minecraft:air", "air");

    final String state;
    final String name; // without namespace and properties

    private FakeBlockData(String state, String name) {
        this.state = state;
        this.name = name;
    }

    static FakeBlockData parse(String s) {
        String t = s.strip();
        String props = null;
        int b = t.indexOf('[');
        if (b >= 0) {
            if (!t.endsWith("]")) {
                throw new IllegalArgumentException("Could not parse data: " + s);
            }
            props = t.substring(b + 1, t.length() - 1);
            t = t.substring(0, b);
        }
        String ns = "minecraft";
        int c = t.indexOf(':');
        if (c >= 0) {
            ns = t.substring(0, c);
            t = t.substring(c + 1);
        }
        if (!ns.equals("minecraft") || !NAME.matcher(t).matches() || t.contains("not_a_block")) {
            throw new IllegalArgumentException("Could not parse data: " + s);
        }
        Map<String, String> p = new TreeMap<>();
        if (props != null && !props.isBlank()) {
            for (String kv : props.split(",")) {
                int e = kv.indexOf('=');
                if (e <= 0) {
                    throw new IllegalArgumentException("Could not parse data: " + s);
                }
                p.put(kv.substring(0, e).strip(), kv.substring(e + 1).strip());
            }
        }
        StringBuilder sb = new StringBuilder("minecraft:").append(t);
        if (!p.isEmpty()) {
            sb.append('[');
            boolean first = true;
            for (Map.Entry<String, String> en : p.entrySet()) {
                if (!first) {
                    sb.append(',');
                }
                first = false;
                sb.append(en.getKey()).append('=').append(en.getValue());
            }
            sb.append(']');
        }
        return new FakeBlockData(sb.toString().intern(), t.intern());
    }

    boolean isAir() {
        return name.equals("air") || name.equals("cave_air") || name.equals("void_air");
    }

    boolean hasTile() {
        return name.endsWith("_sign") || name.endsWith("_banner") || name.endsWith("_head") || name.endsWith("_skull")
                || name.equals("chest") || name.equals("barrel") || name.equals("lectern") || name.equals("decorated_pot")
                || name.endsWith("campfire");
    }

    @Override
    public String getAsString() {
        return state;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof FakeBlockData d && d.state.equals(state);
    }

    @Override
    public int hashCode() {
        return state.hashCode();
    }

    @Override
    public String toString() {
        return state;
    }
}
