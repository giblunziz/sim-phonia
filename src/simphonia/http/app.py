from fastapi import FastAPI

from simphonia.http.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="simphonia", version="0.1.0")
    app.include_router(router)
    return app
