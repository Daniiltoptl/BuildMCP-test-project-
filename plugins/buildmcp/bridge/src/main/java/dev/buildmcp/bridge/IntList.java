package dev.buildmcp.bridge;

import java.util.Arrays;

/** Growable int array. */
final class IntList {
    private int[] data = new int[64];
    private int size;

    void add(int v) {
        if (size == data.length) {
            data = Arrays.copyOf(data, data.length * 2);
        }
        data[size++] = v;
    }

    int size() {
        return size;
    }

    int[] toArray() {
        return Arrays.copyOf(data, size);
    }
}
