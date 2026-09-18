"""IdentityMesh API application entry point."""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from identitymesh import __version__
from identitymesh.api import ApiError, ApplicationServices, build_data_router
from identitymesh.config import Settings
from identitymesh.dependencies import build_readiness_probes
from identitymesh.health import DependencyProbe, HealthResponse, ReadinessResponse, evaluate_probes
from identitymesh.runtime import RuntimeResources, create_runtime

_STATIC_DIRECTORY = Path(__file__).with_name("static")


def create_app(
    settings: Settings | None = None,
    readiness_probes: Mapping[str, DependencyProbe] | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""

    application_settings = settings or Settings()
    probes = dict(
        build_readiness_probes(application_settings)
        if readiness_probes is None
        else readiness_probes
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime: RuntimeResources | None = None
        if services is not None:
            app.state.services = services
        elif application_settings.data_api_enabled:
            runtime = await create_runtime(application_settings)
            app.state.services = runtime.services
        else:
            app.state.services = None
        try:
            yield
        finally:
            app.state.services = None
            if runtime is not None:
                await runtime.close()

    app = FastAPI(
        title="IdentityMesh API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = application_settings
    app.state.services = services
    app.mount("/assets", StaticFiles(directory=_STATIC_DIRECTORY), name="assets")
    app.include_router(build_data_router(application_settings))

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'"
        )
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            headers=error.headers,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(asyncpg.PostgresError)
    async def postgres_error_handler(request: Request, _: asyncpg.PostgresError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "DATA_STORE_UNAVAILABLE",
                    "message": "The identity data store is not available.",
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, _: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_FAILED",
                    "message": "The request did not match the required schema.",
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status="ok", service="identitymesh-api", version=__version__)

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(_STATIC_DIRECTORY / "index.html")

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        responses={503: {"model": ReadinessResponse}},
        tags=["health"],
    )
    async def readiness() -> JSONResponse:
        ready, dependencies = await evaluate_probes(probes)
        response = ReadinessResponse(
            status="ready" if ready else "not_ready",
            dependencies=dependencies,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )

    return app


app = create_app()


def run() -> None:
    """Run the local API server using validated settings."""

    settings = Settings()
    uvicorn.run(
        "identitymesh.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "local",
    )


if __name__ == "__main__":
    run()
