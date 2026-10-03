"""FastAPI application and public routes for the frozen-store POC."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .database import read_only_connection
from .models import LayersRequest, LayersResponse
from .service import assemble_layers_response


def _request_exceeds_feature_limit(error: RequestValidationError) -> bool:
    body = error.body
    return isinstance(body, dict) and isinstance(body.get("features"), list) and len(body["features"]) > 200


def create_app() -> FastAPI:
    """Create the POC application and register its public route."""

    application = FastAPI(
        title="Tunen Soil API",
        description="Read-only API for the frozen soil layers store.",
        version="0.1.0",
    )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        error: RequestValidationError,
    ):
        if _request_exceeds_feature_limit(error):
            return JSONResponse(
                status_code=413,
                content={"detail": "a maximum of 200 features is supported"},
            )
        return await request_validation_exception_handler(request, error)

    @application.post("/soil/layers", response_model=LayersResponse)
    async def create_soil_layers(request_body: LayersRequest):
        with read_only_connection() as connection:
            return assemble_layers_response(connection, request_body)

    return application


app = create_app()
