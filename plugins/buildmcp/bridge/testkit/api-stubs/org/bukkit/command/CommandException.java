package org.bukkit.command;

public class CommandException extends RuntimeException {
    public CommandException(String msg, Throwable cause) {
        super(msg, cause);
    }
}
