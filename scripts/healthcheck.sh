#!/usr/bin/env bash
# Verify the stack is healthy after `docker compose up`. Exits non-zero on failure.
set -uo pipefail

GATEWAY="${GATEWAY_URL:-http://localhost:${GATEWAY_PORT:-8080}}"
RETRIES="${RETRIES:-20}"
SERVICES=(target-service monitoring-service incident-service notification-service)

wait_for() {
  local name="$1" check="$2"
  for _ in $(seq "$RETRIES"); do
    if eval "$check" >/dev/null 2>&1; then
      printf '  %-22s ok\n' "$name"
      return 0
    fi
    sleep 3
  done
  printf '  %-22s FAILED\n' "$name"
  return 1
}

echo "Checking MiniOps health..."
failed=0
wait_for gateway "curl -fsS $GATEWAY/health" || failed=1
for svc in "${SERVICES[@]}"; do
  wait_for "$svc" "docker compose exec -T $svc python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=2)\"" || failed=1
done

exit "$failed"
