# AI Inference Gateway

An intelligent routing layer for LLM inference workloads, deployed on Kubernetes. Routes requests to backend model-serving pods using latency-aware, health-conscious load balancing with auto-scaling and full observability.

## Architecture

```mermaid
graph TB
    subgraph Clients
        C1[Client 1]
        C2[Client 2]
        C3[Client N]
    end

    subgraph "Kubernetes Cluster (ai-inference namespace)"
        subgraph "Gateway Layer (2 replicas)"
            GW1[Gateway Pod 1<br/>FastAPI + Router]
            GW2[Gateway Pod 2<br/>FastAPI + Router]
        end

        subgraph "Intelligent Router"
            R[Weighted Latency Algorithm<br/>• P95 Latency Score<br/>• Queue Depth Score<br/>• Error Rate Score<br/>• Circuit Breaker]
        end

        subgraph "LLM Backend Fleet (3 replicas, HPA: 2-8)"
            B1[Backend Pod 0<br/>TinyLlama / Phi]
            B2[Backend Pod 1<br/>TinyLlama / Phi]
            B3[Backend Pod 2<br/>TinyLlama / Phi]
        end

        HPA[HorizontalPodAutoscaler<br/>Scale on: queue_depth > 5]
    end

    subgraph "Observability Stack"
        P[Prometheus<br/>Scrape: 5s interval]
        G[Grafana Dashboard<br/>• Request Rate<br/>• P95/P99 Latency<br/>• Queue Depth<br/>• Backend Health<br/>• Routing Decisions<br/>• Tokens/sec]
    end

    C1 --> GW1
    C2 --> GW2
    C3 --> GW1

    GW1 --> R
    GW2 --> R

    R --> B1
    R --> B2
    R --> B3

    HPA -.->|scales| B1
    HPA -.->|scales| B2
    HPA -.->|scales| B3

    GW1 -->|/metrics| P
    GW2 -->|/metrics| P
    P --> G
```

## Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant Gateway as Gateway (FastAPI)
    participant Router as Intelligent Router
    participant Backend as LLM Backend
    participant Metrics as Prometheus

    Client->>Gateway: POST /v1/completions<br/>{model: "tinyllama", prompt: "..."}
    Gateway->>Router: select_backend(model="tinyllama")
    
    Note over Router: Score each healthy backend:<br/>score = 0.4×latency + 0.4×queue + 0.2×error<br/>Weighted random among top 50%

    Router-->>Gateway: backend-2 (best score)
    
    Gateway->>Gateway: queue_depth++ for backend-2
    Gateway->>Backend: POST /api/generate
    Backend-->>Gateway: {response, eval_count, duration}
    Gateway->>Gateway: record_latency(P95/P99)<br/>queue_depth--
    Gateway->>Metrics: observe(latency, tokens/s, routing)
    Gateway-->>Client: {text, usage, latency_ms, backend}
```

## Circuit Breaker

```mermaid
stateDiagram-v2
    [*] --> Healthy
    Healthy --> Healthy: success (reset error count)
    Healthy --> Unhealthy: error_count >= 5
    Unhealthy --> Healthy: recovery_time (30s) elapsed + health check passes
    Unhealthy --> Unhealthy: recovery_time not elapsed
```

## Features

- **Intelligent Routing**: Weighted load balancing based on backend latency (P95), queue depth, model availability, and pod health
- **Multi-Model Support**: Route to different models based on request parameters
- **Auto-Scaling**: HPA scales inference pods based on request queue depth
- **Observability**: Prometheus metrics with Grafana dashboards — latency histograms, throughput, error rates
- **Health-Aware**: Automatic backend removal on failure, gradual re-introduction on recovery
- **Graceful Degradation**: Request queuing and backpressure when all backends are saturated

## Quick Start

### Prerequisites

- Docker Desktop with Kubernetes enabled
- kubectl configured
- Python 3.11+
- Helm (for Prometheus/Grafana)

### Deploy

```bash
# Build gateway image
docker build -t ai-inference-gateway:latest -f docker/Dockerfile .

# Deploy backend LLM pods
kubectl apply -f k8s/base/

# Deploy monitoring stack
kubectl apply -f k8s/monitoring/

# Port-forward gateway
kubectl port-forward svc/inference-gateway 8000:8000

# Port-forward Grafana
kubectl port-forward svc/grafana 3000:3000
```

### Test

```bash
# Send inference request
curl -X POST http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "tinyllama", "prompt": "Hello, world!", "max_tokens": 50}'

# Check routing metrics
curl http://localhost:8000/metrics
```

## Project Structure

```
ai-inference-gateway/
├── gateway/              # FastAPI application
│   ├── main.py          # App entrypoint
│   ├── router.py        # Intelligent routing logic
│   ├── backends.py      # Backend pool management
│   ├── metrics.py       # Prometheus metrics
│   ├── health.py        # Health checking
│   └── config.py        # Configuration
├── k8s/
│   ├── base/            # Core K8s manifests
│   └── monitoring/      # Prometheus + Grafana
├── docker/
│   └── Dockerfile       # Gateway container
├── tests/               # Unit + integration tests
├── scripts/             # Helper scripts
└── README.md
```

## Tech Stack

- **Gateway**: Python 3.11, FastAPI, httpx, prometheus-client
- **Inference Backends**: Ollama (TinyLlama, Phi-2)
- **Orchestration**: Kubernetes, HPA
- **Observability**: Prometheus, Grafana
- **Infrastructure**: Docker, kubectl
