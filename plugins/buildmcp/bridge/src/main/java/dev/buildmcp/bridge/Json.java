package dev.buildmcp.bridge;

import java.util.Collection;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

/** Small JSON helpers (Gson ships with Paper). */
final class Json {
    private Json() {}

    static JsonArray arr(int... v) {
        JsonArray a = new JsonArray();
        for (int x : v) {
            a.add(x);
        }
        return a;
    }

    static JsonArray arr(double... v) {
        JsonArray a = new JsonArray();
        for (double x : v) {
            a.add(x);
        }
        return a;
    }

    static JsonArray strings(Collection<String> v) {
        JsonArray a = new JsonArray();
        for (String s : v) {
            a.add(s);
        }
        return a;
    }

    static String[] strings(JsonElement e) {
        if (e == null || !e.isJsonArray()) {
            throw new ApiError(400, "expected a list of strings");
        }
        JsonArray a = e.getAsJsonArray();
        String[] out = new String[a.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = a.get(i).isJsonNull() ? "" : a.get(i).getAsString();
        }
        return out;
    }

    static int[] ints(JsonObject o, String key, int n) {
        JsonElement e = o.get(key);
        if (e == null || !e.isJsonArray() || e.getAsJsonArray().size() != n) {
            throw new ApiError(400, "'" + key + "' must be a list of " + n + " integers");
        }
        int[] out = new int[n];
        for (int i = 0; i < n; i++) {
            out[i] = (int) Math.floor(e.getAsJsonArray().get(i).getAsDouble());
        }
        return out;
    }

    static double[] doubles(JsonObject o, String key, int n) {
        JsonElement e = o.get(key);
        if (e == null || !e.isJsonArray() || e.getAsJsonArray().size() != n) {
            throw new ApiError(400, "'" + key + "' must be a list of " + n + " numbers");
        }
        double[] out = new double[n];
        for (int i = 0; i < n; i++) {
            out[i] = e.getAsJsonArray().get(i).getAsDouble();
        }
        return out;
    }

    static String str(JsonObject o, String key, String def) {
        JsonElement e = o.get(key);
        return e == null || e.isJsonNull() ? def : e.getAsString();
    }

    static boolean bool(JsonObject o, String key, boolean def) {
        JsonElement e = o.get(key);
        return e == null || e.isJsonNull() ? def : e.getAsBoolean();
    }

    static double num(JsonObject o, String key, double def) {
        JsonElement e = o.get(key);
        return e == null || e.isJsonNull() ? def : e.getAsDouble();
    }

    static JsonObject error(String message) {
        JsonObject o = new JsonObject();
        o.addProperty("error", message);
        return o;
    }
}
