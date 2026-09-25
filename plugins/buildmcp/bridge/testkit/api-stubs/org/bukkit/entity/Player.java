package org.bukkit.entity;

import org.bukkit.GameMode;
import org.bukkit.block.Block;
import org.bukkit.command.CommandSender;

public interface Player extends Entity, CommandSender {
    GameMode getGameMode();

    Block getTargetBlockExact(int maxDistance);
}
