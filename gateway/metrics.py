from prometheus_client import Counter, Histogram, Gauge

REQUEST_COUNT = Counter(
    "inference_requests_total",
    "Total inference requests",
    ["model", "backend", "status"],
)

REQUEST_LATENCY = Histogram(
    "inference_request_duration_seconds",
    "Request latency in seconds",
    ["model", "backend"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

QUEUE_DEPTH = Gauge(
    "inference_queue_depth",
    "Current queue depth per backend",
    ["backend"],
)

BACKEND_HEALTH = Gauge(
    "inference_backend_healthy",
    "Backend health status (1=healthy, 0=unhealthy)",
    ["backend", "model"],
)

TOKENS_PER_SECOND = Histogram(
    "inference_tokens_per_second",
    "Token generation throughput",
    ["model", "backend"],
    buckets=[1, 5, 10, 20, 50, 100, 200],
)

ROUTING_DECISIONS = Counter(
    "inference_routing_decisions_total",
    "Routing decisions made",
    ["algorithm", "selected_backend"],
)
