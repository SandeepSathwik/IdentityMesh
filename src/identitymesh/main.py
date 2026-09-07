"""IdentityMesh API application entry point."""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint

from identitymesh import __version__
from identitymesh.config import Settings
from identitymesh.health import DependencyProbe, HealthResponse, ReadinessResponse, evaluate_probes


def create_app(
    settings: Settings | None = None,
    readiness_probes: Mapping[str, DependencyProbe] | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""

    application_settings = settings or Settings()
    probes = dict(readiness_probes or {})

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(
        title="IdentityMesh API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = application_settings

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

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
