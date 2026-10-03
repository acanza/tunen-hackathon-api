"""FastAPI application bootstrap for the frozen-store POC."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the POC application without registering routes yet."""

    return FastAPI(
        title="Tunen Soil API",
        description="Read-only API for the frozen soil layers store.",
        version="0.1.0",
    )


app = create_app()
