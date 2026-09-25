package dev.buildmcp.bridge;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

/**
 * The exchange format between BuildMCP and the bridge (a gzip stream).
 *
 * <pre>
 * "BMCB" | u8 version=1 | i32 headerLength | header (UTF-8 JSON)
 *        | i32 cellCount | cellCount x u16 palette index (index = x + z*W + y*W*L)
 *        | i32 biomeLength | biomeLength x u8 biome palette index per column (x + z*W), 255 = keep
 * </pre>
 *
 * Header: size [W,H,L], min [x,y,z] (world position of cell 0,0,0), palette (index 0 = "": leave the
 * world block alone), tiles [[x,y,z,snbt]...], entities [[x,y,z,id,snbt]...] (positions relative to
 * min), biomes (biome palette or null) plus request options (world, label, backup, entity_tag...).
 */
final class Bundle {
    static final int VERSION = 1;
    static final int BIOME_KEEP = 255;
    private static final byte[] MAGIC = {'B', 'M', 'C', 'B'};

    record Tile(int x, int y, int z, String snbt) {}

    record Ent(double x, double y, double z, String id, String snbt) {}

    final JsonObject header;
    final int w, h, l;
    final String[] palette;
    final char[] cells;
    final List<Tile> tiles;
    final List<Ent> entities;
    final String[] biomePalette; // null = no biomes
    final byte[] biomes; // null = no biomes

    Bundle(JsonObject header, int w, int h, int l, String[] palette, char[] cells, List<Tile> tiles,
           List<Ent> entities, String[] biomePalette, byte[] biomes) {
        this.header = header;
        this.w = w;
        this.h = h;
        this.l = l;
        this.palette = palette;
        this.cells = cells;
        this.tiles = tiles;
        this.entities = entities;
        this.biomePalette = biomePalette;
        this.biomes = biomes;
    }

    int index(int x, int y, int z) {
        return x + z * w + y * w * l;
    }

    long volume() {
        return (long) w * h * l;
    }

    // ------------------------------------------------------------------ read
    static Bundle read(byte[] gz, long maxCells) throws IOException {
        try (InputStream raw = new GZIPInputStream(new ByteArrayInputStream(gz), 1 << 16)) {
            return read(raw, maxCells);
        } catch (java.util.zip.ZipException e) {
            throw new IOException("body is not a gzip BuildMCP bundle: " + e.getMessage(), e);
        }
    }

    static Bundle read(InputStream raw, long maxCells) throws IOException {
        DataInputStream in = new DataInputStream(new BufferedInputStream(raw, 1 << 16));
        byte[] magic = in.readNBytes(4);
        if (magic.length != 4 || magic[0] != MAGIC[0] || magic[1] != MAGIC[1] || magic[2] != MAGIC[2]
                || magic[3] != MAGIC[3]) {
            throw new IOException("not a BuildMCP bundle (bad magic)");
        }
        int version = in.readUnsignedByte();
        if (version != VERSION) {
            throw new IOException("unsupported bundle version " + version + " (bridge understands " + VERSION + ")");
        }
        int hlen = in.readInt();
        if (hlen < 2 || hlen > 512 * 1024 * 1024) {
            throw new IOException("bad header length " + hlen);
        }
        byte[] hb = in.readNBytes(hlen);
        if (hb.length != hlen) {
            throw new IOException("truncated header");
        }
        JsonObject header = JsonParser.parseString(new String(hb, StandardCharsets.UTF_8)).getAsJsonObject();
        int[] size = Json.ints(header, "size", 3);
        if (size[0] <= 0 || size[1] <= 0 || size[2] <= 0) {
            throw new IOException("bad size");
        }
        long volume = (long) size[0] * size[1] * size[2];
        if (volume > maxCells || volume > Integer.MAX_VALUE - 16) {
            throw new IOException("bundle has " + volume + " cells, over the limit " + maxCells + " (max-cells)");
        }
        int n = in.readInt();
        if (n != volume) {
            throw new IOException("cell count " + n + " does not match size " + volume);
        }
        char[] cells = new char[n];
        byte[] buf = new byte[1 << 16];
        int pos = 0;
        while (pos < n) {
            int take = Math.min(buf.length / 2, n - pos);
            in.readFully(buf, 0, take * 2);
            for (int k = 0; k < take; k++) {
                cells[pos + k] = (char) (((buf[2 * k] & 0xFF) << 8) | (buf[2 * k + 1] & 0xFF));
            }
            pos += take;
        }
        int blen = in.readInt();
        byte[] biomes = null;
        if (blen > 0) {
            if (blen != size[0] * size[2]) {
                throw new IOException("biome grid has " + blen + " entries, expected " + size[0] * size[2]);
            }
            biomes = in.readNBytes(blen);
            if (biomes.length != blen) {
                throw new IOException("truncated biome grid");
            }
        }
        String[] palette = Json.strings(header.get("palette"));
        if (palette.length == 0) {
            throw new IOException("empty palette");
        }
        int max = 0;
        for (char c : cells) {
            if (c > max) {
                max = c;
            }
        }
        if (max >= palette.length) {
            throw new IOException("cell refers to palette index " + max + " but the palette has " + palette.length);
        }
        List<Tile> tiles = new ArrayList<>();
        JsonElement te = header.get("tiles");
        if (te != null && te.isJsonArray()) {
            for (JsonElement e : te.getAsJsonArray()) {
                JsonArray a = e.getAsJsonArray();
                tiles.add(new Tile(a.get(0).getAsInt(), a.get(1).getAsInt(), a.get(2).getAsInt(), a.get(3).getAsString()));
            }
        }
        List<Ent> ents = new ArrayList<>();
        JsonElement ee = header.get("entities");
        if (ee != null && ee.isJsonArray()) {
            for (JsonElement e : ee.getAsJsonArray()) {
                JsonArray a = e.getAsJsonArray();
                ents.add(new Ent(a.get(0).getAsDouble(), a.get(1).getAsDouble(), a.get(2).getAsDouble(),
                        a.get(3).getAsString(), a.size() > 4 && !a.get(4).isJsonNull() ? a.get(4).getAsString() : "{}"));
            }
        }
        String[] biomePalette = null;
        JsonElement be = header.get("biomes");
        if (be != null && be.isJsonArray() && biomes != null) {
            biomePalette = Json.strings(be);
            for (byte b : biomes) {
                int v = b & 0xFF;
                if (v != BIOME_KEEP && v >= biomePalette.length) {
                    throw new IOException("biome index " + v + " outside the biome palette");
                }
            }
        } else {
            biomes = null;
        }
        return new Bundle(header, size[0], size[1], size[2], palette, cells, tiles, ents, biomePalette, biomes);
    }

    // ----------------------------------------------------------------- write
    byte[] toBytes() throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream(Math.max(1024, cells.length / 4));
        write(bos);
        return bos.toByteArray();
    }

    void write(OutputStream target) throws IOException {
        JsonObject hdr = header.deepCopy();
        JsonArray size = new JsonArray();
        size.add(w);
        size.add(h);
        size.add(l);
        hdr.add("size", size);
        JsonArray pal = new JsonArray();
        for (String s : palette) {
            pal.add(s);
        }
        hdr.add("palette", pal);
        JsonArray ta = new JsonArray();
        for (Tile t : tiles) {
            JsonArray a = new JsonArray();
            a.add(t.x());
            a.add(t.y());
            a.add(t.z());
            a.add(t.snbt());
            ta.add(a);
        }
        hdr.add("tiles", ta);
        JsonArray ea = new JsonArray();
        for (Ent e : entities) {
            JsonArray a = new JsonArray();
            a.add(e.x());
            a.add(e.y());
            a.add(e.z());
            a.add(e.id());
            a.add(e.snbt());
            ea.add(a);
        }
        hdr.add("entities", ea);
        if (biomePalette != null && biomes != null) {
            JsonArray ba = new JsonArray();
            for (String s : biomePalette) {
                ba.add(s);
            }
            hdr.add("biomes", ba);
        } else {
            hdr.remove("biomes");
        }
        byte[] hb = hdr.toString().getBytes(StandardCharsets.UTF_8);
        GZIPOutputStream gz = new GZIPOutputStream(target, 1 << 16);
        DataOutputStream out = new DataOutputStream(new BufferedOutputStream(gz, 1 << 16));
        out.write(MAGIC);
        out.writeByte(VERSION);
        out.writeInt(hb.length);
        out.write(hb);
        out.writeInt(cells.length);
        byte[] buf = new byte[1 << 16];
        int pos = 0;
        while (pos < cells.length) {
            int take = Math.min(buf.length / 2, cells.length - pos);
            for (int k = 0; k < take; k++) {
                char c = cells[pos + k];
                buf[2 * k] = (byte) (c >>> 8);
                buf[2 * k + 1] = (byte) c;
            }
            out.write(buf, 0, take * 2);
            pos += take;
        }
        if (biomePalette != null && biomes != null) {
            out.writeInt(biomes.length);
            out.write(biomes);
        } else {
            out.writeInt(0);
        }
        out.flush();
        gz.finish();
    }
}
