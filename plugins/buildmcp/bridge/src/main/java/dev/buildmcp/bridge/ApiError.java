package dev.buildmcp.bridge;

/** An error that becomes an HTTP status with a JSON message. */
final class ApiError extends RuntimeException {
    final int status;

    ApiError(int status, String message) {
        super(message);
        this.status = status;
    }
}
