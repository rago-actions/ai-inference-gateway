import asyncio
import random
import time
from fastapi import FastAPI
import uvicorn

app = FastAPI()

MODELS = ["tinyllama", "phi"]


@app.get("/api/tags")
async def tags():
    return {"models": [{"name": f"{m}:latest"} for m in MODELS]}


@app.post("/api/generate")
async def generate(request: dict):
    model = request.get("model", "tinyllama")
    prompt = request.get("prompt", "")
    num_predict = request.get("options", {}).get("num_predict", 50)

    # Simulate inference latency (50-500ms)
    latency = random.uniform(0.05, 0.5)
    await asyncio.sleep(latency)

    words = ["the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog",
             "AI", "model", "inference", "routing", "gateway", "scales",
             "efficiently", "with", "low", "latency", "and", "high", "throughput"]
    response_text = " ".join(random.choices(words, k=min(num_predict, 50)))

    return {
        "model": model,
        "response": response_text,
        "done": True,
        "eval_count": num_predict,
        "prompt_eval_count": len(prompt.split()),
        "total_duration": int(latency * 1e9),
        "eval_duration": int(latency * 0.8 * 1e9),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=11434)
