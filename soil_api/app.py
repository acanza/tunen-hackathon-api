"""FastAPI application and public routes for the frozen-store POC."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from .artifacts import resolve_store_artifact
from .database import read_only_connection
from .models import LayersRequest, LayersResponse
from .service import assemble_layers_response


IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
ARTIFACT_MEDIA_TYPES = {
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


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

    @application.get("/static/{artifact_path:path}")
    async def get_static_artifact(artifact_path: str):
        suffix = Path(artifact_path).suffix.lower()
        media_type = ARTIFACT_MEDIA_TYPES.get(suffix)
        if media_type is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        try:
            resolved_path = resolve_store_artifact(artifact_path)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail="artifact not found") from error
        return FileResponse(
            resolved_path,
            media_type=media_type,
            headers={"Cache-Control": IMMUTABLE_CACHE_CONTROL},
        )

    return application


app = create_app()
