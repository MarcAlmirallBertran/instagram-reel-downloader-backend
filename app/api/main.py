from fastapi import APIRouter

from app.api.routes import tasks, users

api_router = APIRouter()
api_router.include_router(tasks.router)
api_router.include_router(users.router)