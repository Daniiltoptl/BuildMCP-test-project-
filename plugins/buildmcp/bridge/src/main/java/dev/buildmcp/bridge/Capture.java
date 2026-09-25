package dev.buildmcp.bridge;

import java.util.ArrayList;
import java.util.List;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.TranslatableComponent;
import net.kyori.adventure.text.TranslationArgument;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.command.CommandSender;

/**
 * Runs commands as a silent console-level sender and captures the feedback
 * (no chat spam for operators, no console log lines). Main thread only.
 */
final class Capture {
    private Capture() {}

    record Result(boolean dispatched, List<Component> messages, String error) {
        String text() {
            StringBuilder sb = new StringBuilder();
            for (Component c : messages) {
                if (!sb.isEmpty()) {
                    sb.append('\n');
                }
                sb.append(plain(c));
            }
            if (error != null) {
                if (!sb.isEmpty()) {
                    sb.append('\n');
                }
                sb.append(error);
            }
            return sb.toString();
        }

        List<String> lines() {
            List<String> out = new ArrayList<>();
            for (Component c : messages) {
                out.add(plain(c));
            }
            if (error != null) {
                out.add(error);
            }
            return out;
        }

        /** True if some message is a translatable text whose key starts with one of the prefixes. */
        boolean hasKey(String... prefixes) {
            for (Component c : messages) {
                if (findKey(c, prefixes) != null) {
                    return true;
                }
            }
            return false;
        }

        /** SNBT from a "/data get block|entity" answer, or null. */
        String dataQuery() {
            for (Component c : messages) {
                TranslatableComponent tc = findKey(c, "commands.data.block.query", "commands.data.entity.query");
                if (tc != null && !tc.arguments().isEmpty()) {
                    return argText(tc.arguments().get(tc.arguments().size() - 1));
                }
            }
            return null;
        }
    }

    static Result run(String command) {
        List<Component> msgs = new ArrayList<>();
        CommandSender sender = Bukkit.createCommandSender(msgs::add);
        String cmd = command.startsWith("/") ? command.substring(1) : command;
        try {
            boolean ok = Bukkit.dispatchCommand(sender, cmd);
            return new Result(ok, msgs, null);
        } catch (RuntimeException e) {
            Throwable c = e.getCause() != null ? e.getCause() : e;
            return new Result(false, msgs, c.getClass().getSimpleName() + ": " + c.getMessage());
        }
    }

    /**
     * Runs a command in the given world's dimension (commands default to the overworld). The inner
     * command must be a plain vanilla name ("data", not "minecraft:data"): it is parsed by Brigadier.
     */
    static Result runIn(World world, String command) {
        return run("minecraft:execute in " + world.getKey() + " run " + command);
    }

    static String plain(Component c) {
        return PlainTextComponentSerializer.plainText().serialize(c);
    }

    private static String argText(TranslationArgument a) {
        Object v = a.value();
        if (v instanceof Component c) {
            return plain(c);
        }
        return String.valueOf(v);
    }

    private static TranslatableComponent findKey(Component c, String... prefixes) {
        if (c instanceof TranslatableComponent tc) {
            for (String p : prefixes) {
                if (tc.key().startsWith(p)) {
                    return tc;
                }
            }
        }
        for (Component child : c.children()) {
            TranslatableComponent hit = findKey(child, prefixes);
            if (hit != null) {
                return hit;
            }
        }
        return null;
    }
}
