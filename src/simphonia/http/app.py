import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from simphonia.http import sse
from simphonia.http.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="simphonia", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    async def _capture_loop() -> None:
        sse.set_event_loop(asyncio.get_event_loop())

    return app
