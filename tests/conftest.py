import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on the asyncio backend used by the application."""

    return "asyncio"
