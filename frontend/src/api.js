// All requests go through the API gateway at /api/v1/...
// Same-origin in Docker (nginx proxy) and in dev (Vite proxy).

function newCorrelationId() {
  return `req-${crypto.randomUUID().slice(0, 12)}`;
}

export async function apiGet(path) {
  const response = await fetch(`/api/v1${path}`, {
    headers: { Accept: "application/json", "X-Correlation-ID": newCorrelationId() },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body?.error?.message ?? `HTTP ${response.status}`;
    throw new Error(message);
  }
  return body;
}
