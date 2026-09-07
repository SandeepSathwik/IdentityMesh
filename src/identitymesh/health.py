"""Health response models and dependency probe contracts."""

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict

DependencyProbe = Callable[[], Awaitable[bool]]


class HealthResponse(BaseModel):
    """Public liveness response without sensitive implementation details."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Public readiness response."""

    model_config = ConfigDict(extra="forbid")

    status: str
    dependencies: dict[str, str]


async def evaluate_probes(probes: dict[str, DependencyProbe]) -> tuple[bool, dict[str, str]]:
    """Evaluate dependency probes without exposing exception details."""

    results: dict[str, str] = {}
    ready = True

    for name, probe in probes.items():
        try:
            dependency_ready = await probe()
        except Exception:  # A dependency exception must degrade readiness safely.
            dependency_ready = False

        results[name] = "ready" if dependency_ready else "unavailable"
        ready = ready and dependency_ready

    return ready, results
