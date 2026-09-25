package dev.buildmcp.bridge;

import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

/** A unit of world work, advanced a little every server tick by the {@link JobManager}. */
abstract class Job {
    private static final AtomicInteger SEQ = new AtomicInteger();
    static final int MAX_WARNINGS = 200;

    final String id;
    final String kind;
    final String label;
    volatile String phase = "queued";
    volatile String error;
    volatile long done;
    volatile long total;
    final long created = System.currentTimeMillis();
    volatile long started;
    volatile long finished;
    volatile boolean cancelRequested;
    final List<String> warnings = new CopyOnWriteArrayList<>();
    /** Longest main-thread slice per phase (ms), to spot lag sources. */
    final java.util.Map<String, Double> tickMs = new java.util.concurrent.ConcurrentHashMap<>();
    private final CompletableFuture<Void> completion = new CompletableFuture<>();

    Job(String kind, String label) {
        this.id = kind + "-" + Long.toString(System.currentTimeMillis(), 36) + SEQ.incrementAndGet();
        this.kind = kind;
        this.label = label == null || label.isBlank() ? kind : label;
    }

    /** Main thread. Does work until {@code deadline} (System.nanoTime). Returns true when finished. */
    abstract boolean tick(long deadline) throws Exception;

    /** Main thread, called exactly once when the job ends (success, failure or cancel). */
    void cleanup() {}

    /** Extra fields for the job status. */
    void describe(JsonObject o) {}

    void warn(String w) {
        if (warnings.size() < MAX_WARNINGS) {
            warnings.add(w);
        } else if (warnings.size() == MAX_WARNINGS) {
            warnings.add("... more warnings omitted");
        }
    }

    boolean isFinished() {
        return completion.isDone();
    }

    void complete(String err) {
        finished = System.currentTimeMillis();
        if (err == null) {
            phase = "done";
        } else {
            error = err;
            phase = cancelRequested ? "cancelled" : "failed";
        }
        completion.complete(null);
    }

    /** Blocks (HTTP thread) until the job ends; throws if it failed. */
    void await(long timeoutMs) throws Exception {
        try {
            completion.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            throw new ApiError(504, "job " + id + " still running after " + timeoutMs / 1000 + " s (phase " + phase + ")");
        } catch (ExecutionException e) {
            throw new RuntimeException(e.getCause());
        }
        if (error != null) {
            throw new ApiError(500, "job " + id + " " + phase + ": " + error);
        }
    }

    JsonObject toJson() {
        JsonObject o = new JsonObject();
        o.addProperty("id", id);
        o.addProperty("kind", kind);
        o.addProperty("label", label);
        o.addProperty("phase", phase);
        o.addProperty("done", done);
        o.addProperty("total", total);
        o.addProperty("progress", total > 0 ? Math.min(1.0, (double) done / total) : (isFinished() ? 1.0 : 0.0));
        long end = finished > 0 ? finished : System.currentTimeMillis();
        o.addProperty("elapsed_ms", started > 0 ? end - started : 0);
        o.addProperty("queued_ms", (started > 0 ? started : end) - created);
        if (error != null) {
            o.addProperty("error", error);
        }
        JsonArray w = new JsonArray();
        for (String s : warnings) {
            w.add(s);
        }
        o.add("warnings", w);
        JsonObject t = new JsonObject();
        for (java.util.Map.Entry<String, Double> e : tickMs.entrySet()) {
            t.addProperty(e.getKey(), Math.round(e.getValue() * 10) / 10.0);
        }
        o.add("max_tick_ms", t);
        describe(o);
        return o;
    }
}
