import logging

from fastapi import FastAPI

from app.api.routes import reels
from app.core.config import settings

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Event-driven backend for downloading Instagram Reels.",
)

app.include_router(reels.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
