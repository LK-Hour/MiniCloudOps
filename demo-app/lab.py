"""MiniOps Lab: a sandbox application whose health can be broken on purpose.

The dashboard's Demo Lab registers targets that point here and injects faults to show how the
platform reacts. Standard library only, so it runs on the stock python image with nothing to build.

Monitored endpoints (one per name, created on first use, healthy by default):
    GET  /                          always 200: a plain healthy app
    GET  /<name>/health             answers according to the endpoint's mode

Control API (reached through the gateway at /api/v1/lab/...):
    GET    /lab/health              liveness of the lab itself
    GET    /lab/endpoints           every endpoint, its fault settings and hit counter
    GET    /lab/endpoints/<name>
    PUT    /lab/endpoints/<name>    {"mode": "healthy|down|slow|flaky", "latency_ms": int,
                                     "status_code": int, "error_rate": float}
    DELETE /lab/endpoints/<name>    forget the endpoint (it becomes healthy again)

Modes:
    healthy  200 after latency_ms (default 0)
    down     status_code (default 503) immediately
    slow     200 after latency_ms (default 2500)
    flaky    status_code with probability error_rate (default 0.5), otherwise 200
"""
import json
import os
import random
import re
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "80"))
MAX_ENDPOINTS = 200
MAX_LATENCY_MS = 30_000
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
MODES = {"healthy", "down", "slow", "flaky"}
DEFAULTS = {"healthy": 0, "slow": 2500}

lock = threading.Lock()
endpoints: dict[str, dict] = {}


def log(level: str, message: str, **fields) -> None:
    """JSON lines, like the MiniOps services, so Loki parses them the same way."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": level,
        "service": "demo-app",
        "message": message,
        **fields,
    }
    print(json.dumps(record), file=sys.stdout, flush=True)


def new_endpoint(name: str) -> dict:
    return {
        "name": name,
        "mode": "healthy",
        "latency_ms": 0,
        "status_code": 503,
        "error_rate": 0.5,
        "hits": 0,
        "failures": 0,
        "last_hit_at": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def get_or_create(name: str) -> dict | None:
    with lock:
        if name not in endpoints:
            if len(endpoints) >= MAX_ENDPOINTS:
                return None
            endpoints[name] = new_endpoint(name)
        return endpoints[name]


def validate(body: dict) -> tuple[dict, list[dict]]:
    errors, clean = [], {}
    mode = body.get("mode", "healthy")
    if mode not in MODES:
        errors.append({"field": "body.mode", "message": f"Must be one of {sorted(MODES)}"})
    clean["mode"] = mode
    latency = body.get("latency_ms", DEFAULTS.get(mode, 0))
    if not isinstance(latency, int) or not 0 <= latency <= MAX_LATENCY_MS:
        errors.append({"field": "body.latency_ms", "message": f"Integer between 0 and {MAX_LATENCY_MS}"})
    clean["latency_ms"] = latency
    code = body.get("status_code", 503)
    if not isinstance(code, int) or not 400 <= code <= 599:
        errors.append({"field": "body.status_code", "message": "Integer between 400 and 599"})
    clean["status_code"] = code
    rate = body.get("error_rate", 0.5)
    if not isinstance(rate, (int, float)) or not 0 <= rate <= 1:
        errors.append({"field": "body.error_rate", "message": "Number between 0 and 1"})
    clean["error_rate"] = float(rate) if isinstance(rate, (int, float)) else rate
    return clean, errors


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        # A prober that times out closes the socket mid-request; that is expected here.
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        log("ERROR", "Unhandled error", error=repr(exc), client=client_address[0])


class Handler(BaseHTTPRequestHandler):
    server_version = "MiniOpsLab/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # replaced by structured logs
        pass

    @property
    def correlation_id(self) -> str | None:
        return self.headers.get("X-Correlation-ID")

    def send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def error(self, status: int, message: str, details=None) -> None:
        self.send_json(status, {"error": {"code": status, "message": message, "details": details,
                                          "correlation_id": self.correlation_id}})

    def read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 10_000:
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def route(self) -> tuple[str, str | None]:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "":
            return "root", None
        if path == "/lab/health":
            return "lab-health", None
        if path == "/lab/endpoints":
            return "collection", None
        if m := re.fullmatch(r"/lab/endpoints/([^/]+)", path):
            return "item", m.group(1)
        if m := re.fullmatch(r"/([^/]+)/health", path):
            return "probe", m.group(1)
        return "unknown", None

    # --- verbs -----------------------------------------------------------------------------------

    def do_GET(self) -> None:
        kind, name = self.route()
        if kind == "root":  # a plain healthy app, for targets registered as http://demo-app/
            return self.send_json(200, {"status": "ok", "service": "demo-app"})
        if kind == "lab-health":
            return self.send_json(200, {"status": "ok", "service": "demo-app", "endpoints": len(endpoints)})
        if kind == "collection":
            with lock:
                return self.send_json(200, sorted(endpoints.values(), key=lambda e: e["name"]))
        if kind == "item":
            with lock:
                endpoint = endpoints.get(name)
            return self.send_json(200, endpoint) if endpoint else self.error(404, f"Endpoint '{name}' not found")
        if kind == "probe":
            return self.probe(name)
        return self.error(404, "Unknown route")

    def do_PUT(self) -> None:
        kind, name = self.route()
        if kind != "item":
            return self.error(405, "Method not allowed")
        if not NAME.match(name):
            return self.error(422, "Invalid endpoint name", [{"field": "path.name", "message": NAME.pattern}])
        body = self.read_json()
        if body is None:
            return self.error(422, "Body must be a JSON object")
        clean, errors = validate(body)
        if errors:
            return self.error(422, "Validation failed", errors)
        endpoint = get_or_create(name)
        if endpoint is None:
            return self.error(409, f"Lab is full ({MAX_ENDPOINTS} endpoints); delete some first")
        with lock:
            endpoint.update(clean, updated_at=datetime.now(UTC).isoformat())
            snapshot = dict(endpoint)
        log("WARNING" if clean["mode"] != "healthy" else "INFO", "Fault configured",
            endpoint=name, correlation_id=self.correlation_id, **clean)
        self.send_json(200, snapshot)

    def do_DELETE(self) -> None:
        kind, name = self.route()
        if kind != "item":
            return self.error(405, "Method not allowed")
        with lock:
            removed = endpoints.pop(name, None)
        if removed is None:
            return self.error(404, f"Endpoint '{name}' not found")
        log("INFO", "Endpoint removed", endpoint=name, correlation_id=self.correlation_id)
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # --- the monitored endpoint ----------------------------------------------------------------

    def probe(self, name: str) -> None:
        if not NAME.match(name):
            return self.error(404, "Unknown route")
        endpoint = get_or_create(name)
        if endpoint is None:
            return self.error(503, "Lab is full")
        with lock:
            endpoint["hits"] += 1
            endpoint["last_hit_at"] = datetime.now(UTC).isoformat()
            mode, latency = endpoint["mode"], endpoint["latency_ms"]
            code, rate = endpoint["status_code"], endpoint["error_rate"]

        fail = mode == "down" or (mode == "flaky" and random.random() < rate)
        if mode in ("healthy", "slow") and latency:
            time.sleep(latency / 1000)
        if fail:
            with lock:
                endpoint["failures"] += 1
            log("WARNING", "Probe answered with an injected failure", endpoint=name, mode=mode, status_code=code)
            return self.send_json(code, {"status": "unhealthy", "endpoint": name, "mode": mode})
        try:
            self.send_json(200, {"status": "ok", "endpoint": name, "mode": mode})
        except (BrokenPipeError, ConnectionResetError):
            log("INFO", "Prober hung up before the answer", endpoint=name, latency_ms=latency)


if __name__ == "__main__":
    server = Server(("0.0.0.0", PORT), Handler)
    log("INFO", "MiniOps Lab listening", port=PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
