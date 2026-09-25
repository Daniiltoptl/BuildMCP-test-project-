package dev.buildmcp.bridge;

import java.lang.reflect.Method;
import java.util.Locale;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

/**
 * Optional WorldEdit/FAWE integration through reflection (no compile-time dependency): the player's
 * current selection, so they can point at an area with the wand.
 */
final class WorldEditHook {
    private WorldEditHook() {}

    static Plugin plugin() {
        Plugin p = Bukkit.getPluginManager().getPlugin("FastAsyncWorldEdit");
        if (p == null || !p.isEnabled()) {
            p = Bukkit.getPluginManager().getPlugin("WorldEdit");
        }
        return p != null && p.isEnabled() ? p : null;
    }

    static String name() {
        Plugin p = plugin();
        return p == null ? null : p.getName() + " " + p.getDescription().getVersion();
    }

    /** [x1,y1,z1,x2,y2,z2] of the player's selection, or null. Main thread. */
    static int[] selection(Player player) {
        Plugin we = plugin();
        if (we == null) {
            return null;
        }
        try {
            Object session = we.getClass().getMethod("getSession", Player.class).invoke(we, player);
            Object weWorld = session.getClass().getMethod("getSelectionWorld").invoke(session);
            if (weWorld == null) {
                return null;
            }
            Method getSel = null;
            for (Method m : session.getClass().getMethods()) {
                if (m.getName().equals("getSelection") && m.getParameterCount() == 1) {
                    getSel = m;
                    break;
                }
            }
            if (getSel == null) {
                return null;
            }
            Object region = getSel.invoke(session, weWorld);
            Object min = region.getClass().getMethod("getMinimumPoint").invoke(region);
            Object max = region.getClass().getMethod("getMaximumPoint").invoke(region);
            return new int[]{coord(min, "x"), coord(min, "y"), coord(min, "z"), coord(max, "x"), coord(max, "y"),
                    coord(max, "z")};
        } catch (ReflectiveOperationException | RuntimeException | LinkageError e) {
            return null; // no selection, incomplete selection or an unknown WorldEdit version
        }
    }

    private static int coord(Object vec, String axis) throws ReflectiveOperationException {
        String up = axis.toUpperCase(Locale.ROOT);
        for (String name : new String[]{axis, "get" + up, "getBlock" + up}) {
            try {
                return ((Number) vec.getClass().getMethod(name).invoke(vec)).intValue();
            } catch (NoSuchMethodException ignored) {
                // try the next accessor name
            }
        }
        throw new NoSuchMethodException(axis);
    }
}
