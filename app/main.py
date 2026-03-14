from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.main import api_router
from app.broker import broker
from app.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if not broker.is_worker_process:
        init_db()
        await broker.startup()
    
    yield
    
    if not broker.is_worker_process:
        await broker.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}
