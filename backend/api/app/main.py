import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .errors import (
    CarePathError,
    error_response,
    handle_carepath_error,
    handle_http_exception,
    handle_validation_error,
)
from .evidence_routes import router as evidence_router
from .health import router as health_router
from .health_data_routes import router as health_data_router
from .llm.provider import JsonObject, LLMProvider
from .llm.registry import get_provider
from .logging import configure_logging, reset_request_id, set_request_id
from .routes import router as api_router

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
logger = logging.getLogger("carepath.api")


def normalize_request_id(value: str | None, *, max_length: int) -> str:
    if value and len(value) <= max_length and REQUEST_ID_PATTERN.fullmatch(value) is not None:
        return value
    return str(uuid.uuid4())


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", "<unmatched>")


def configure_reviewer_web(application: FastAPI, directory: str | None) -> None:
    if directory is None:
        return

    reviewer_dir = Path(directory).expanduser().resolve()
    index_path = reviewer_dir / "index.html"
    if not reviewer_dir.is_dir() or not index_path.is_file():
        raise ValueError("reviewer_web_dir must contain an Expo Web index.html")

    @application.get("/", include_in_schema=False)
    async def reviewer_root() -> FileResponse:
        return FileResponse(index_path, media_type="text/html")

    for url_prefix, child_name in (("/_expo", "_expo"), ("/assets", "assets")):
        child_dir = reviewer_dir / child_name
        if child_dir.is_dir():
            application.mount(
                url_prefix,
                StaticFiles(directory=child_dir),
                name=f"reviewer-{child_name}",
            )


def create_app(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_provider = (
            provider if provider is not None else get_provider(resolved_settings.llm_provider)
        )
        try:
            if resolved_settings.privacy_mode == "local_strict" and not resolved_provider.is_local:
                raise ValueError("local_strict requires an operator-controlled local LLM provider")
            application.state.provider = resolved_provider
            yield
        finally:
            await resolved_provider.aclose()

    application = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    application.state.settings = resolved_settings
    application.exception_handler(CarePathError)(handle_carepath_error)
    application.exception_handler(StarletteHTTPException)(handle_http_exception)
    application.exception_handler(RequestValidationError)(handle_validation_error)

    @application.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = normalize_request_id(
            request.headers.get(resolved_settings.request_id_header),
            max_length=resolved_settings.request_id_max_length,
        )
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started_at = time.perf_counter()

        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.error(
                    "request_failed",
                    extra={
                        "component": "api",
                        "route": route_template(request),
                        "status_code": HTTPStatus.INTERNAL_SERVER_ERROR,
                        "error_code": "internal_error",
                        "error_class": type(exc).__name__,
                    },
                )
                response = JSONResponse(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    content=error_response(
                        "internal_error",
                        "Internal server error",
                        request_id,
                    ),
                )

            response.headers[resolved_settings.request_id_header] = request_id
            logger.info(
                "request_completed",
                extra={
                    "component": "api",
                    "route": route_template(request),
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            return response
        finally:
            reset_request_id(token)

    application.include_router(api_router)
    application.include_router(health_data_router)
    application.include_router(evidence_router)
    application.include_router(health_router)

    @application.get("/health")
    async def health(request: Request) -> JsonObject:
        active_provider = cast(LLMProvider, request.app.state.provider)
        return await active_provider.health_check()

    configure_reviewer_web(application, resolved_settings.reviewer_web_dir)
    return application


app = create_app()
