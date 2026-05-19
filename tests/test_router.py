import pytest

from gateway.backends import Backend, BackendStats
from gateway.router import RoutingStrategy


@pytest.fixture
def backends():
    return [
        Backend(
            id="backend-0",
            url="http://localhost:11434",
            models=["tinyllama"],
            stats=BackendStats(latency_p95=0.1, queue_depth=2),
        ),
        Backend(
            id="backend-1",
            url="http://localhost:11435",
            models=["tinyllama", "phi"],
            stats=BackendStats(latency_p95=0.5, queue_depth=5),
        ),
        Backend(
            id="backend-2",
            url="http://localhost:11436",
            models=["tinyllama"],
            stats=BackendStats(latency_p95=0.2, queue_depth=1),
        ),
    ]


@pytest.fixture
def router():
    return RoutingStrategy()


def test_weighted_latency_prefers_low_latency_low_queue(router, backends):
    selections = {}
    for _ in range(100):
        selected = router._weighted_latency(backends)
        selections[selected.id] = selections.get(selected.id, 0) + 1

    # backend-0 (low latency, low queue) and backend-2 (low latency, lowest queue)
    # should be selected more often than backend-1 (high latency, high queue)
    assert selections.get("backend-1", 0) < selections.get("backend-0", 0)
    assert selections.get("backend-1", 0) < selections.get("backend-2", 0)


def test_least_connections_selects_min_queue(router, backends):
    selected = router._least_connections(backends)
    assert selected.id == "backend-2"


def test_empty_backends_returns_none(router):
    result = router.select([])
    assert result is None


def test_model_filtering(backends):
    phi_backends = [b for b in backends if "phi" in b.models]
    assert len(phi_backends) == 1
    assert phi_backends[0].id == "backend-1"


def test_circuit_breaker_excludes_backend(backends):
    import time

    backends[0].trip_circuit_breaker()
    available = [b for b in backends if b.is_available]
    assert len(available) == 2
    assert all(b.id != "backend-0" for b in available)


def test_error_rate_calculation():
    stats = BackendStats(error_count=3, success_count=7)
    assert stats.error_rate == pytest.approx(0.3)


def test_latency_recording():
    stats = BackendStats()
    for latency in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        stats.record_latency(latency)
    assert stats.latency_p95 == pytest.approx(1.0)
