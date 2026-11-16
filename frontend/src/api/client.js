// Every request goes through the API gateway at /api/v1/... (same origin: nginx in Docker,
// the Vite proxy in dev). Errors use the platform's standard body:
// {"error": {"code", "message", "details", "correlation_id"}}

export class ApiError extends Error {
  constructor(status, message, details = null, correlationId = null) {
    super(message);
    this.status = status;
    this.details = details;
    this.correlationId = correlationId;
  }

  /** Field errors as { name: message }, from details like [{field: "body.name", message}] */
  get fieldErrors() {
    if (!Array.isArray(this.details)) return {};
    return Object.fromEntries(
      this.details.map((d) => [String(d.field ?? "").replace(/^body\./, ""), d.message]),
    );
  }
}

const newCorrelationId = () => `ui-${crypto.randomUUID().slice(0, 12)}`;

/**
 * Call the gateway. Options:
 *   correlationId  reuse one ID for several calls (the Demo Lab tags a whole run with it)
 *   raw            never throw on an HTTP error; resolve to {status, ok, data, correlationId, ms}
 */
export async function api(path, { method = "GET", body, signal, correlationId = newCorrelationId(), raw = false } = {}) {
  const started = performance.now();
  let response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      signal,
      headers: {
        Accept: "application/json",
        "X-Correlation-ID": correlationId,
        ...(body !== undefined && { "Content-Type": "application/json" }),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, "Cannot reach the MiniOps gateway", null, correlationId);
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (raw) {
    return {
      status: response.status,
      ok: response.ok,
      data,
      correlationId: response.headers.get("X-Correlation-ID") ?? correlationId,
      ms: Math.round(performance.now() - started),
    };
  }
  if (response.status === 204) return null;
  if (!response.ok) {
    const error = data?.error;
    throw new ApiError(
      response.status,
      error?.message ?? `HTTP ${response.status}`,
      error?.details ?? null,
      error?.correlation_id ?? correlationId,
    );
  }
  return data;
}
