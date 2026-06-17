from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.realtime.server import build_socket_app

settings = get_settings()


def create_fastapi_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
    )
    app.include_router(api_router)
    return app


fastapi_app = create_fastapi_app()
app = build_socket_app(fastapi_app)
