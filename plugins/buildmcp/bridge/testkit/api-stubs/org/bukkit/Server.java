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

public interface Server {
    String getName();

    String getVersion();

    String getBukkitVersion();

    String getMinecraftVersion();

    Logger getLogger();

    Collection<? extends Player> getOnlinePlayers();

    Player getPlayerExact(String name);

    List<World> getWorlds();

    World getWorld(String name);

    BukkitScheduler getScheduler();

    PluginManager getPluginManager();

    boolean dispatchCommand(CommandSender sender, String commandLine) throws CommandException;

    BlockData createBlockData(String data) throws IllegalArgumentException;

    UnsafeValues getUnsafe();

    double[] getTPS();

    CommandSender createCommandSender(Consumer<? super Component> feedback);

    ConsoleCommandSender getConsoleSender();

    boolean isPrimaryThread();
}
