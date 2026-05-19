from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gateway_port: int = 8000
    health_check_interval: int = 5
    health_check_timeout: int = 2
    max_queue_depth: int = 100
    routing_algorithm: str = "weighted_latency"
    backend_discovery: str = "kubernetes"
    ollama_namespace: str = "default"
    ollama_service_label: str = "app=ollama"
    latency_weight: float = 0.4
    queue_depth_weight: float = 0.4
    error_rate_weight: float = 0.2
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_time: int = 30


settings = Settings()
