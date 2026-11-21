from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anyio import create_task_group, sleep
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app import database
from app.config import get_settings
from app.database import create_db_and_tables
from app.provider_settings import router as provider_settings_router
from app.routers import (
    accounts,
    chat,
    collections,
    documents,
    extract,
    oauth,
    search,
    trash,
)
from app.work_queue import process_next
from app.workspace import WORKSPACE_API, workspace_middleware
from app.workspace import router as workspace_router

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    while True:
        try:
            worked = await run_in_threadpool(process_next)
        except Exception:
            logger.exception("Background worker poll failed")
            worked = False
        await sleep(0.1 if worked else 1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await run_in_threadpool(create_db_and_tables)
    async with create_task_group() as tasks:
        tasks.start_soon(run_worker)
        try:
            yield
        finally:
            tasks.cancel_scope.cancel()


app = FastAPI(
    title="PageIndex Document RAG API",
    version="0.1.0",
    lifespan=lifespan,
    max_body_size=2 * 1024**2,
)

app.middleware("http")(workspace_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(f"{WORKSPACE_API}/"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
        )
    return await request_validation_exception_handler(request, exc)


app.include_router(workspace_router)
app.include_router(provider_settings_router)
app.include_router(accounts.router)
app.include_router(oauth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(search.router)
app.include_router(extract.router)
app.include_router(collections.router)
app.include_router(trash.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": app.title,
        "version": app.version,
        "docs": app.docs_url or "/docs",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> JSONResponse:
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
