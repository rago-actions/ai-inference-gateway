#!/bin/bash
set -euo pipefail

echo "=== AI Inference Gateway - Load Test ==="
echo "Sending 50 concurrent requests to test routing behavior..."

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"

for i in $(seq 1 50); do
    curl -s -X POST "$GATEWAY_URL/v1/completions" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"tinyllama\", \"prompt\": \"Count to $i\", \"max_tokens\": 20}" \
        -o /dev/null -w "Request $i: HTTP %{http_code} | Time: %{time_total}s | Backend: \n" &
done

wait
echo ""
echo "=== Load test complete ==="
echo ""
echo "Check metrics:"
echo "  curl $GATEWAY_URL/v1/backends"
echo "  curl $GATEWAY_URL/metrics | grep inference_"
