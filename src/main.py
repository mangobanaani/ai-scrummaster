import logging
from fastapi import FastAPI
from src.config import settings
from src.webhook_router import router

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

app = FastAPI(title="Agentic Scrum Master", version="0.2.1")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/healthz")
async def healthz():
    # Platform convention (fabric scaffold probes /healthz by default).
    return await health()


@app.get("/readyz")
async def readyz():
    return {"status": "ok"}
