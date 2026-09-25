package org.bukkit.command;

import org.bukkit.plugin.Plugin;

public final class PluginCommand extends Command {
    private final Plugin owner;
    private CommandExecutor executor;
    private TabCompleter completer;

    protected PluginCommand(String name, Plugin owner) {
        super(name);
        this.owner = owner;
    }

    /** Test kit only. */
    public static PluginCommand create(String name, Plugin owner) {
        return new PluginCommand(name, owner);
    }

    public void setExecutor(CommandExecutor executor) {
        this.executor = executor;
    }

    public void setTabCompleter(TabCompleter completer) {
        this.completer = completer;
    }

    public CommandExecutor getExecutor() {
        return executor;
    }

    public Plugin getPlugin() {
        return owner;
    }

    @Override
    public boolean execute(CommandSender sender, String commandLabel, String[] args) {
        return executor != null && executor.onCommand(sender, this, commandLabel, args);
    }
}
