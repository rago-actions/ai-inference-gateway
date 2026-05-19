import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx

from .config import settings
from .metrics import BACKEND_HEALTH, QUEUE_DEPTH


class BackendState(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"


@dataclass
class BackendStats:
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    queue_depth: int = 0
    error_count: int = 0
    success_count: int = 0
    last_health_check: float = 0.0
    latency_window: list = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        total = self.error_count + self.success_count
        if total == 0:
            return 0.0
        return self.error_count / total

    def record_latency(self, latency: float):
        self.latency_window.append(latency)
        if len(self.latency_window) > 100:
            self.latency_window = self.latency_window[-100:]
        sorted_latencies = sorted(self.latency_window)
        n = len(sorted_latencies)
        self.latency_p95 = sorted_latencies[int(n * 0.95)] if n > 0 else 0.0
        self.latency_p99 = sorted_latencies[int(n * 0.99)] if n > 0 else 0.0


@dataclass
class Backend:
    id: str
    url: str
    models: list[str] = field(default_factory=list)
    state: BackendState = BackendState.HEALTHY
    stats: BackendStats = field(default_factory=BackendStats)
    circuit_breaker_open_until: float = 0.0

    @property
    def is_available(self) -> bool:
        if self.state != BackendState.HEALTHY:
            return False
        if time.time() < self.circuit_breaker_open_until:
            return False
        return True

    def trip_circuit_breaker(self):
        self.circuit_breaker_open_until = (
            time.time() + settings.circuit_breaker_recovery_time
        )
        self.state = BackendState.UNHEALTHY

    def reset_circuit_breaker(self):
        self.circuit_breaker_open_until = 0.0
        self.state = BackendState.HEALTHY
        self.stats.error_count = 0


class BackendPool:
    def __init__(self):
        self.backends: dict[str, Backend] = {}
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=settings.health_check_timeout)

    async def register(self, backend_id: str, url: str, models: list[str]):
        async with self._lock:
            self.backends[backend_id] = Backend(
                id=backend_id, url=url, models=models
            )

    async def deregister(self, backend_id: str):
        async with self._lock:
            self.backends.pop(backend_id, None)

    def get_available(self, model: str | None = None) -> list[Backend]:
        available = [b for b in self.backends.values() if b.is_available]
        if model:
            available = [b for b in available if model in b.models]
        return available

    async def health_check(self, backend: Backend) -> bool:
        try:
            resp = await self._client.get(f"{backend.url}/api/tags")
            healthy = resp.status_code == 200
            if healthy:
                backend.state = BackendState.HEALTHY
                backend.stats.last_health_check = time.time()
                if resp.status_code == 200:
                    data = resp.json()
                    backend.models = [
                        m["name"].split(":")[0]
                        for m in data.get("models", [])
                    ]
            else:
                backend.stats.error_count += 1
                if backend.stats.error_count >= settings.circuit_breaker_threshold:
                    backend.trip_circuit_breaker()
            BACKEND_HEALTH.labels(
                backend=backend.id,
                model=",".join(backend.models),
            ).set(1 if healthy else 0)
            return healthy
        except (httpx.RequestError, httpx.TimeoutException):
            backend.stats.error_count += 1
            if backend.stats.error_count >= settings.circuit_breaker_threshold:
                backend.trip_circuit_breaker()
            BACKEND_HEALTH.labels(
                backend=backend.id,
                model=",".join(backend.models),
            ).set(0)
            return False

    async def run_health_checks(self):
        while True:
            for backend in list(self.backends.values()):
                if (
                    backend.state == BackendState.UNHEALTHY
                    and time.time() >= backend.circuit_breaker_open_until
                ):
                    await self.health_check(backend)
                elif backend.state == BackendState.HEALTHY:
                    await self.health_check(backend)
                QUEUE_DEPTH.labels(backend=backend.id).set(
                    backend.stats.queue_depth
                )
            await asyncio.sleep(settings.health_check_interval)


backend_pool = BackendPool()
