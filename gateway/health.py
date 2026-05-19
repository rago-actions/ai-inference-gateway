from fastapi import APIRouter

from .backends import backend_pool

health_router = APIRouter()


@health_router.get("/health")
async def health():
    total = len(backend_pool.backends)
    healthy = len(backend_pool.get_available())
    return {
        "status": "healthy" if healthy > 0 else "degraded",
        "backends_total": total,
        "backends_healthy": healthy,
    }


@health_router.get("/ready")
async def ready():
    if len(backend_pool.get_available()) == 0:
        return {"status": "not_ready"}, 503
    return {"status": "ready"}
