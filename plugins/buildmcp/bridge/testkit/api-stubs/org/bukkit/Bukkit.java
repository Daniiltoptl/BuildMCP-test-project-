package org.bukkit;

import java.util.Collection;
import java.util.List;
import java.util.function.Consumer;
import java.util.logging.Logger;

import net.kyori.adventure.text.Component;

import org.bukkit.block.data.BlockData;
import org.bukkit.command.CommandException;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.PluginManager;
import org.bukkit.scheduler.BukkitScheduler;

public final class Bukkit {
    private static Server server;

    private Bukkit() {
    }

    public static Server getServer() {
        return server;
    }

    public static void setServer(Server s) {
        if (server != null) {
            throw new UnsupportedOperationException("Cannot redefine singleton Server");
        }
        server = s;
    }

    public static String getName() {
        return server.getName();
    }

    public static String getVersion() {
        return server.getVersion();
    }

    public static String getBukkitVersion() {
        return server.getBukkitVersion();
    }

    public static String getMinecraftVersion() {
        return server.getMinecraftVersion();
    }

    public static Logger getLogger() {
        return server.getLogger();
    }

    public static Collection<? extends Player> getOnlinePlayers() {
        return server.getOnlinePlayers();
    }

    public static Player getPlayerExact(String name) {
        return server.getPlayerExact(name);
    }

    public static List<World> getWorlds() {
        return server.getWorlds();
    }

    public static World getWorld(String name) {
        return server.getWorld(name);
    }

    public static BukkitScheduler getScheduler() {
        return server.getScheduler();
    }

    public static PluginManager getPluginManager() {
        return server.getPluginManager();
    }

    public static boolean dispatchCommand(CommandSender sender, String commandLine) throws CommandException {
        return server.dispatchCommand(sender, commandLine);
    }

    public static BlockData createBlockData(String data) throws IllegalArgumentException {
        return server.createBlockData(data);
    }

    @Deprecated
    public static UnsafeValues getUnsafe() {
        return server.getUnsafe();
    }

    public static double[] getTPS() {
        return server.getTPS();
    }

    public static CommandSender createCommandSender(Consumer<? super Component> feedback) {
        return server.createCommandSender(feedback);
    }

    public static ConsoleCommandSender getConsoleSender() {
        return server.getConsoleSender();
    }

    public static boolean isPrimaryThread() {
        return server.isPrimaryThread();
    }
}
