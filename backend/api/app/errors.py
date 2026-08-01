from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class CarePathError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def error_response(code: str, message: str, request_id: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


async def handle_carepath_error(request: Request, exc: CarePathError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.code, exc.message, get_request_id(request)),
    )


async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    code_by_status: dict[int, str] = {
        HTTPStatus.NOT_FOUND: "not_found",
        HTTPStatus.METHOD_NOT_ALLOWED: "method_not_allowed",
    }
    code = code_by_status.get(exc.status_code, "http_error")
    try:
        message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        message = "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(code, message, get_request_id(request)),
        headers=exc.headers,
    )


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    del exc
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=error_response(
            "validation_error",
            "Request validation failed",
            get_request_id(request),
        ),
    )
