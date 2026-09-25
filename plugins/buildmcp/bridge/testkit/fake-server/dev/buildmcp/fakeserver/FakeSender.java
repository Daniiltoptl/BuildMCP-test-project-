package dev.buildmcp.fakeserver;

import java.util.function.Consumer;

import net.kyori.adventure.text.Component;

import org.bukkit.command.ConsoleCommandSender;

/** Console-level sender. With a feedback consumer it is Paper's createCommandSender(...) sender. */
final class FakeSender implements ConsoleCommandSender {
    private final Consumer<? super Component> feedback;

    FakeSender(Consumer<? super Component> feedback) {
        this.feedback = feedback;
    }

    void feedback(Component c) {
        if (feedback != null) {
            feedback.accept(c);
        } else {
            System.out.println("[console] " + FakeServer.plain(c));
        }
    }

    @Override
    public void sendMessage(String message) {
        feedback(Component.text(message));
    }

    @Override
    public String getName() {
        return feedback == null ? "CONSOLE" : "FeedbackForwardingSender";
    }

    @Override
    public boolean hasPermission(String name) {
        return true;
    }
}
