package org.bukkit;

public final class NamespacedKey {
    private final String namespace;
    private final String key;

    public NamespacedKey(String namespace, String key) {
        this.namespace = namespace;
        this.key = key;
    }

    public static NamespacedKey minecraft(String key) {
        return new NamespacedKey("minecraft", key);
    }

    public static NamespacedKey fromString(String s) {
        int i = s.indexOf(':');
        return i < 0 ? minecraft(s) : new NamespacedKey(s.substring(0, i), s.substring(i + 1));
    }

    public String getNamespace() {
        return namespace;
    }

    public String getKey() {
        return key;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof NamespacedKey k && k.namespace.equals(namespace) && k.key.equals(key);
    }

    @Override
    public int hashCode() {
        return namespace.hashCode() * 31 + key.hashCode();
    }

    @Override
    public String toString() {
        return namespace + ":" + key;
    }
}
