import random

from .backends import Backend, BackendPool
from .config import settings
from .metrics import ROUTING_DECISIONS


class RoutingStrategy:
    """Intelligent routing with weighted scoring based on latency, queue depth, and error rate."""

    def select(self, backends: list[Backend], model: str | None = None) -> Backend | None:
        if not backends:
            return None

        if settings.routing_algorithm == "round_robin":
            return self._round_robin(backends)
        elif settings.routing_algorithm == "least_connections":
            return self._least_connections(backends)
        else:
            return self._weighted_latency(backends)

    def _weighted_latency(self, backends: list[Backend]) -> Backend:
        scores = []
        for backend in backends:
            latency_score = 1.0 / (1.0 + backend.stats.latency_p95)
            queue_score = 1.0 / (1.0 + backend.stats.queue_depth)
            error_score = 1.0 - backend.stats.error_rate

            weighted = (
                settings.latency_weight * latency_score
                + settings.queue_depth_weight * queue_score
                + settings.error_rate_weight * error_score
            )
            scores.append((backend, weighted))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_candidates = scores[: max(1, len(scores) // 2)]

        # Weighted random among top candidates to avoid thundering herd
        total_score = sum(s for _, s in top_candidates)
        if total_score == 0:
            selected = random.choice(top_candidates)[0]
        else:
            r = random.uniform(0, total_score)
            cumulative = 0.0
            selected = top_candidates[0][0]
            for backend, score in top_candidates:
                cumulative += score
                if r <= cumulative:
                    selected = backend
                    break

        ROUTING_DECISIONS.labels(
            algorithm="weighted_latency",
            selected_backend=selected.id,
        ).inc()
        return selected

    def _least_connections(self, backends: list[Backend]) -> Backend:
        selected = min(backends, key=lambda b: b.stats.queue_depth)
        ROUTING_DECISIONS.labels(
            algorithm="least_connections",
            selected_backend=selected.id,
        ).inc()
        return selected

    def _round_robin(self, backends: list[Backend]) -> Backend:
        if not hasattr(self, "_rr_index"):
            self._rr_index = 0
        self._rr_index = (self._rr_index + 1) % len(backends)
        selected = backends[self._rr_index]
        ROUTING_DECISIONS.labels(
            algorithm="round_robin",
            selected_backend=selected.id,
        ).inc()
        return selected


router = RoutingStrategy()


def select_backend(pool: BackendPool, model: str | None = None) -> Backend | None:
    available = pool.get_available(model=model)
    if not available:
        return None
    return router.select(available, model=model)
