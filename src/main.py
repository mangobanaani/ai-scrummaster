import logging
from fastapi import FastAPI
from src.config import settings
from src.webhook_router import router

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

app = FastAPI(title="Agentic Scrum Master", version="0.1.0")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
