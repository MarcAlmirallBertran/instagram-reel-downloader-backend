from fastapi import APIRouter

from app.api.routes import download_reel

api_router = APIRouter()
api_router.include_router(download_reel.router)