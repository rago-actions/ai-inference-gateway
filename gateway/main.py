import asyncio
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from prometheus_client import make_asgi_app

from .backends import backend_pool
from .config import settings
from .health import health_router
from .metrics import QUEUE_DEPTH, REQUEST_COUNT, REQUEST_LATENCY, TOKENS_PER_SECOND
from .router import select_backend

app = FastAPI(title="AI Inference Gateway", version="1.0.0")
app.include_router(health_router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

http_client = httpx.AsyncClient(timeout=60.0)


@app.on_event("startup")
async def startup():
    await register_backends()
    asyncio.create_task(backend_pool.run_health_checks())


async def register_backends():
    """Register backends from environment or K8s service discovery."""
    import os

    backend_urls = os.environ.get(
        "BACKEND_URLS", "http://ollama-0:11434,http://ollama-1:11434,http://ollama-2:11434"
    )
    for i, url in enumerate(backend_urls.split(",")):
        url = url.strip()
        await backend_pool.register(
            backend_id=f"ollama-{i}",
            url=url,
            models=["tinyllama", "phi"],
        )


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    model = body.get("model")

    backend = select_backend(backend_pool, model=model)
    if not backend:
        raise HTTPException(
            status_code=503,
            detail=f"No available backend for model '{model}'",
        )

    backend.stats.queue_depth += 1
    QUEUE_DEPTH.labels(backend=backend.id).set(backend.stats.queue_depth)
    start_time = time.time()

    try:
        ollama_payload = {
            "model": model or "tinyllama",
            "prompt": body.get("prompt", ""),
            "stream": body.get("stream", False),
            "options": {"num_predict": body.get("max_tokens", 100)},
        }

        if body.get("stream"):
            return StreamingResponse(
                _stream_response(backend, ollama_payload, start_time),
                media_type="text/event-stream",
            )

        resp = await http_client.post(
            f"{backend.url}/api/generate",
            json=ollama_payload,
        )

        latency = time.time() - start_time
        backend.stats.record_latency(latency)
        backend.stats.success_count += 1
        backend.stats.error_count = 0

        REQUEST_LATENCY.labels(model=model, backend=backend.id).observe(latency)
        REQUEST_COUNT.labels(model=model, backend=backend.id, status="success").inc()

        result = resp.json()
        tokens = result.get("eval_count", 0)
        if tokens > 0 and latency > 0:
            TOKENS_PER_SECOND.labels(model=model, backend=backend.id).observe(
                tokens / latency
            )

        return {
            "id": f"cmpl-{backend.id}-{int(start_time)}",
            "object": "text_completion",
            "model": model,
            "choices": [
                {
                    "text": result.get("response", ""),
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": result.get("prompt_eval_count", 0),
                "completion_tokens": tokens,
                "total_tokens": result.get("prompt_eval_count", 0) + tokens,
            },
            "latency_ms": round(latency * 1000, 2),
            "backend": backend.id,
        }

    except (httpx.RequestError, httpx.TimeoutException) as e:
        latency = time.time() - start_time
        backend.stats.error_count += 1
        REQUEST_COUNT.labels(model=model, backend=backend.id, status="error").inc()
        REQUEST_LATENCY.labels(model=model, backend=backend.id).observe(latency)

        if backend.stats.error_count >= settings.circuit_breaker_threshold:
            backend.trip_circuit_breaker()

        raise HTTPException(status_code=502, detail=f"Backend error: {e}")

    finally:
        backend.stats.queue_depth -= 1
        QUEUE_DEPTH.labels(backend=backend.id).set(backend.stats.queue_depth)


async def _stream_response(backend, payload, start_time):
    try:
        async with http_client.stream(
            "POST", f"{backend.url}/api/generate", json=payload
        ) as resp:
            async for chunk in resp.aiter_lines():
                yield f"data: {chunk}\n\n"
        latency = time.time() - start_time
        backend.stats.record_latency(latency)
        backend.stats.success_count += 1
        REQUEST_LATENCY.labels(
            model=payload["model"], backend=backend.id
        ).observe(latency)
        REQUEST_COUNT.labels(
            model=payload["model"], backend=backend.id, status="success"
        ).inc()
    except (httpx.RequestError, httpx.TimeoutException):
        backend.stats.error_count += 1
        REQUEST_COUNT.labels(
            model=payload["model"], backend=backend.id, status="error"
        ).inc()


@app.get("/v1/models")
async def list_models():
    models = set()
    for backend in backend_pool.backends.values():
        models.update(backend.models)
    return {
        "object": "list",
        "data": [{"id": m, "object": "model"} for m in sorted(models)],
    }


@app.get("/v1/backends")
async def list_backends():
    return {
        "backends": [
            {
                "id": b.id,
                "url": b.url,
                "state": b.state.value,
                "models": b.models,
                "stats": {
                    "latency_p95": round(b.stats.latency_p95, 4),
                    "latency_p99": round(b.stats.latency_p99, 4),
                    "queue_depth": b.stats.queue_depth,
                    "error_rate": round(b.stats.error_rate, 4),
                },
            }
            for b in backend_pool.backends.values()
        ]
    }
