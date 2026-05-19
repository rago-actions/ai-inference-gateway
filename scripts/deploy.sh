#!/bin/bash
set -euo pipefail

echo "=== AI Inference Gateway - Deploy ==="

# Build gateway image
echo "[1/5] Building gateway Docker image..."
docker build -t ai-inference-gateway:latest -f docker/Dockerfile .

# Create namespace
echo "[2/5] Creating namespace..."
kubectl apply -f k8s/base/namespace.yaml

# Deploy Ollama backends
echo "[3/5] Deploying Ollama inference backends..."
kubectl apply -f k8s/base/ollama-statefulset.yaml

# Wait for Ollama pods
echo "       Waiting for Ollama pods to be ready..."
kubectl wait --for=condition=ready pod -l app=ollama -n ai-inference --timeout=120s

# Pull model into each Ollama pod
echo "       Pulling TinyLlama model into backends..."
for i in 0 1 2; do
    kubectl exec -n ai-inference ollama-$i -- ollama pull tinyllama &
done
wait

# Deploy gateway
echo "[4/5] Deploying inference gateway..."
kubectl apply -f k8s/base/gateway-deployment.yaml
kubectl apply -f k8s/base/hpa.yaml

# Deploy monitoring
echo "[5/5] Deploying monitoring stack..."
kubectl apply -f k8s/monitoring/prometheus-config.yaml
kubectl apply -f k8s/monitoring/grafana.yaml

# Wait for gateway
kubectl wait --for=condition=ready pod -l app=inference-gateway -n ai-inference --timeout=60s

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Access points:"
echo "  Gateway:    kubectl port-forward svc/inference-gateway 8000:8000 -n ai-inference"
echo "  Prometheus: kubectl port-forward svc/prometheus 9090:9090 -n ai-inference"
echo "  Grafana:    kubectl port-forward svc/grafana 3000:3000 -n ai-inference"
echo ""
echo "Test:"
echo "  curl -X POST http://localhost:8000/v1/completions \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"model\": \"tinyllama\", \"prompt\": \"Hello!\", \"max_tokens\": 50}'"
