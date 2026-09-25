package dev.buildmcp.bridge;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Turns a per-column biome grid into /fillbiome commands. Biomes live in 4x4x4 cells, so columns are
 * grouped into quart cells (majority vote) and merged into rectangles under the command volume limit.
 */
final class BiomeBoxes {
    static final int VOLUME_LIMIT = 32768;

    private BiomeBoxes() {}

    /** Commands (without "execute in") for world rows y1..y2. */
    static List<String> commands(String[] palette, byte[] grid, int w, int l, int ox, int oz, int y1, int y2) {
        List<String> out = new ArrayList<>();
        if (palette == null || grid == null || y2 < y1) {
            return out;
        }
        int qx1 = Math.floorDiv(ox, 4), qz1 = Math.floorDiv(oz, 4);
        int qx2 = Math.floorDiv(ox + w - 1, 4), qz2 = Math.floorDiv(oz + l - 1, 4);
        int qw = qx2 - qx1 + 1, ql = qz2 - qz1 + 1;
        int[] quart = new int[qw * ql];
        for (int qz = 0; qz < ql; qz++) {
            for (int qx = 0; qx < qw; qx++) {
                Map<Integer, Integer> votes = new HashMap<>();
                for (int dz = 0; dz < 4; dz++) {
                    for (int dx = 0; dx < 4; dx++) {
                        int x = (qx1 + qx) * 4 + dx - ox, z = (qz1 + qz) * 4 + dz - oz;
                        if (x < 0 || z < 0 || x >= w || z >= l) {
                            continue;
                        }
                        int v = grid[x + z * w] & 0xFF;
                        if (v != Bundle.BIOME_KEEP) {
                            votes.merge(v, 1, Integer::sum);
                        }
                    }
                }
                int best = -1, bestN = 0;
                for (Map.Entry<Integer, Integer> e : votes.entrySet()) {
                    if (e.getValue() > bestN || (e.getValue() == bestN && e.getKey() < best)) {
                        best = e.getKey();
                        bestN = e.getValue();
                    }
                }
                quart[qx + qz * qw] = best;
            }
        }
        int quartRows = Math.floorDiv(y2, 4) - Math.floorDiv(y1, 4) + 1;
        int maxArea = Math.max(1, VOLUME_LIMIT / (64 * quartRows));
        boolean[] used = new boolean[quart.length];
        for (int qz = 0; qz < ql; qz++) {
            for (int qx = 0; qx < qw; qx++) {
                int b = quart[qx + qz * qw];
                if (b < 0 || used[qx + qz * qw]) {
                    continue;
                }
                int ex = qx;
                while (ex + 1 < qw && quart[ex + 1 + qz * qw] == b && !used[ex + 1 + qz * qw] && (ex + 2 - qx) <= maxArea) {
                    ex++;
                }
                int rowW = ex - qx + 1;
                int ez = qz;
                grow:
                while (ez + 1 < ql && (ez + 2 - qz) * rowW <= maxArea) {
                    for (int x = qx; x <= ex; x++) {
                        int k = x + (ez + 1) * qw;
                        if (quart[k] != b || used[k]) {
                            break grow;
                        }
                    }
                    ez++;
                }
                for (int z = qz; z <= ez; z++) {
                    for (int x = qx; x <= ex; x++) {
                        used[x + z * qw] = true;
                    }
                }
                int bx1 = (qx1 + qx) * 4, bz1 = (qz1 + qz) * 4;
                int bx2 = (qx1 + ex) * 4 + 3, bz2 = (qz1 + ez) * 4 + 3;
                out.add(String.format(Locale.ROOT, "fillbiome %d %d %d %d %d %d %s",
                        bx1, y1, bz1, bx2, y2, bz2, palette[b]));
            }
        }
        return out;
    }
}
