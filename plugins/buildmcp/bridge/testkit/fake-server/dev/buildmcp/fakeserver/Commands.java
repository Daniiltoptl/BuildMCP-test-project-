package dev.buildmcp.fakeserver;

import java.util.Arrays;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import net.kyori.adventure.text.Component;

import org.bukkit.command.CommandSender;
import org.bukkit.entity.EntityType;

/** The handful of vanilla commands BuildBridge uses, with the same translation keys as the game. */
final class Commands {
    private Commands() {}

    static final class Ctx {
        final FakeServer server;
        final CommandSender sender;
        FakeWorld world;

        Ctx(FakeServer server, CommandSender sender, FakeWorld world) {
            this.server = server;
            this.sender = sender;
            this.world = world;
        }
    }

    static boolean run(Ctx ctx, String line) {
        String[] a = line.split(" ", -1);
        String cmd = a[0].startsWith("minecraft:") ? a[0].substring(10) : a[0];
        try {
            switch (cmd) {
                case "execute" -> {
                    // execute in <dimension> run <command>
                    if (a.length < 5 || !a[1].equals("in") || !a[3].equals("run")) {
                        return error(ctx, "Incorrect argument for command");
                    }
                    FakeWorld w = ctx.server.worldByKey(a[2]);
                    if (w == null) {
                        return error(ctx, "Unknown dimension '" + a[2] + "'");
                    }
                    ctx.world = w;
                    return run(ctx, String.join(" ", Arrays.copyOfRange(a, 4, a.length)));
                }
                case "data" -> {
                    return data(ctx, a, line);
                }
                case "summon" -> {
                    return summon(ctx, a, line);
                }
                case "fillbiome" -> {
                    return fillbiome(ctx, a);
                }
                case "setblock" -> {
                    int x = Integer.parseInt(a[1]), y = Integer.parseInt(a[2]), z = Integer.parseInt(a[3]);
                    String rest = String.join(" ", Arrays.copyOfRange(a, 4, a.length));
                    String nbt = null;
                    int brace = rest.indexOf('{');
                    if (brace >= 0) {
                        nbt = rest.substring(brace);
                        rest = rest.substring(0, brace);
                    }
                    ctx.world.set(x, y, z, FakeBlockData.parse(rest.strip()));
                    if (nbt != null) {
                        Snbt.validate(nbt);
                        ctx.world.setTile(x, y, z, Snbt.join(Snbt.entries(nbt)));
                    }
                    return ok(ctx, Component.translatable("commands.setblock.success", Component.text(x),
                            Component.text(y), Component.text(z)));
                }
                case "say" -> {
                    return ok(ctx, Component.text("[Server] " + line.substring(line.indexOf(' ') + 1)));
                }
                case "testkit" -> {
                    return ok(ctx, Component.text(ctx.server.statsLine()));
                }
                case "bb", "buildbridge" -> {
                    return ctx.server.plugin.getCommand("buildbridge").execute(ctx.sender, cmd,
                            Arrays.copyOfRange(a, 1, a.length));
                }
                default -> {
                    return error(ctx, "Unknown or incomplete command, see below for error");
                }
            }
        } catch (IllegalArgumentException | ArrayIndexOutOfBoundsException e) {
            return error(ctx, "Invalid command: " + e.getMessage());
        }
    }

    private static boolean ok(Ctx ctx, Component c) {
        ctx.server.reply(ctx.sender, c);
        return true;
    }

    private static boolean error(Ctx ctx, String msg) {
        ctx.server.reply(ctx.sender, Component.text(msg));
        return true; // vanilla commands report failures as feedback, dispatch still "handled" them
    }

    private static String rest(String line, int words) {
        int idx = 0;
        for (int i = 0; i < words; i++) {
            idx = line.indexOf(' ', idx) + 1;
        }
        return line.substring(idx);
    }

    private static boolean data(Ctx ctx, String[] a, String line) {
        String op = a[1];
        if (a[2].equals("block")) {
            int x = Integer.parseInt(a[3]), y = Integer.parseInt(a[4]), z = Integer.parseInt(a[5]);
            String tile = ctx.world.tile(x, y, z);
            if (tile == null) {
                return error(ctx, "The target block is not a block entity");
            }
            FakeBlockData b = ctx.world.get(x, y, z);
            if (op.equals("get")) {
                Map<String, String> m = new java.util.LinkedHashMap<>();
                m.put("x", String.valueOf(x));
                m.put("y", String.valueOf(y));
                m.put("z", String.valueOf(z));
                m.put("id", "\"minecraft:" + beId(b.name) + "\"");
                m.putAll(Snbt.entries(tile.isEmpty() ? "{}" : tile));
                return ok(ctx, Component.translatable("commands.data.block.query", Component.text(x), Component.text(y),
                        Component.text(z), Component.text(Snbt.join(m))));
            }
            if (op.equals("merge")) {
                String nbt = rest(line, 6);
                Snbt.validate(nbt);
                Map<String, String> m = Snbt.entries(tile.isEmpty() ? "{}" : tile);
                Map<String, String> add = Snbt.entries(nbt);
                add.keySet().removeAll(java.util.List.of("x", "y", "z", "id"));
                String before = Snbt.join(m);
                m.putAll(add);
                if (Snbt.join(m).equals(before)) {
                    return error(ctx, "Nothing changed. The specified properties already have these values");
                }
                ctx.world.setTile(x, y, z, Snbt.join(m));
                return ok(ctx, Component.translatable("commands.data.block.modified", Component.text(x),
                        Component.text(y), Component.text(z)));
            }
        } else if (a[2].equals("entity") && op.equals("get")) {
            FakeEntity e = ctx.server.entity(UUID.fromString(a[3]));
            if (e == null) {
                return error(ctx, "No entity was found");
            }
            Map<String, String> m = Snbt.entries(e.snbt == null || e.snbt.isEmpty() ? "{}" : e.snbt);
            m.put("Pos", String.format(Locale.ROOT, "[%sd, %sd, %sd]", e.loc.getX(), e.loc.getY(), e.loc.getZ()));
            long msb = e.uuid.getMostSignificantBits(), lsb = e.uuid.getLeastSignificantBits();
            m.put("UUID", String.format(Locale.ROOT, "[I; %d, %d, %d, %d]", (int) (msb >> 32), (int) msb, (int) (lsb >> 32), (int) lsb));
            return ok(ctx, Component.translatable("commands.data.entity.query", Component.text(e.type.name()),
                    Component.text(Snbt.join(m))));
        }
        return error(ctx, "Incorrect argument for command");
    }

    private static String beId(String block) {
        if (block.endsWith("_hanging_sign")) {
            return "hanging_sign";
        }
        if (block.endsWith("_sign")) {
            return "sign";
        }
        if (block.endsWith("_banner")) {
            return "banner";
        }
        if (block.endsWith("_head") || block.endsWith("_skull")) {
            return "skull";
        }
        return block;
    }

    private static boolean summon(Ctx ctx, String[] a, String line) {
        EntityType t = EntityType.fromName(a[1]);
        if (t == null || t == EntityType.PLAYER || t == EntityType.UNKNOWN) {
            return error(ctx, "Unknown entity: " + a[1]);
        }
        double x = Double.parseDouble(a[2]), y = Double.parseDouble(a[3]), z = Double.parseDouble(a[4]);
        String nbt = a.length > 5 ? rest(line, 5) : "{}";
        Snbt.validate(nbt);
        Map<String, String> m = Snbt.entries(nbt);
        if (m.containsKey("UUID")) {
            String[] parts = m.get("UUID").replaceAll("[\\[\\]I; ]", "").split(",");
            if (parts.length == 4) {
                long msb = ((long) Integer.parseInt(parts[0]) << 32) | (Integer.parseInt(parts[1]) & 0xFFFFFFFFL);
                long lsb = ((long) Integer.parseInt(parts[2]) << 32) | (Integer.parseInt(parts[3]) & 0xFFFFFFFFL);
                if (ctx.server.entity(new UUID(msb, lsb)) != null) {
                    return error(ctx, "Unable to summon entity due to duplicate UUIDs");
                }
            }
        }
        m.remove("UUID");
        m.remove("Pos");
        ctx.server.spawn(ctx.world, t, x, y, z, Snbt.join(m));
        return ok(ctx, Component.translatable("commands.summon.success", Component.text(t.name())));
    }

    private static boolean fillbiome(Ctx ctx, String[] a) {
        int x1 = Integer.parseInt(a[1]), y1 = Integer.parseInt(a[2]), z1 = Integer.parseInt(a[3]);
        int x2 = Integer.parseInt(a[4]), y2 = Integer.parseInt(a[5]), z2 = Integer.parseInt(a[6]);
        String biome = a[7].contains(":") ? a[7] : "minecraft:" + a[7];
        int qx1 = Math.floorDiv(Math.min(x1, x2), 4), qx2 = Math.floorDiv(Math.max(x1, x2), 4);
        int qy1 = Math.floorDiv(Math.min(y1, y2), 4), qy2 = Math.floorDiv(Math.max(y1, y2), 4);
        int qz1 = Math.floorDiv(Math.min(z1, z2), 4), qz2 = Math.floorDiv(Math.max(z1, z2), 4);
        long volume = (long) (4 * (qx2 - qx1) + 1) * (4 * (qy2 - qy1) + 1) * (4 * (qz2 - qz1) + 1);
        if (volume > 32768) {
            return error(ctx, "Too many blocks in the specified area (maximum 32768, specified " + volume + ")");
        }
        int n = 0;
        for (int qx = qx1; qx <= qx2; qx++) {
            for (int qy = qy1; qy <= qy2; qy++) {
                for (int qz = qz1; qz <= qz2; qz++) {
                    ctx.world.setBiome(qx, qy, qz, biome);
                    n++;
                }
            }
        }
        return ok(ctx, Component.translatable("commands.fillbiome.success.count", Component.text(n)));
    }
}
