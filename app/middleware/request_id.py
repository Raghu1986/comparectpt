import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())

        structlog.contextvars.bind_contextvars(
            request_id=request_id
        )

        logger.info(
            "request_started",
            path=request.url.path,
            method=request.method,
        )

        response = await call_next(request)

        logger.info(
            "request_completed",
            status_code=response.status_code,
        )

        return response
