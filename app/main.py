from contextlib import asynccontextmanager

from fastapi import FastAPI
from guard.middleware import SecurityMiddleware
from guard.models import SecurityConfig

from app.api import insurance, sample
from app.core.config import get_settings
from app.core.engine_cache import dispose_all_engines
from app.core.logger_config import configure_logging
from app.middleware.request_id import RequestContextMiddleware

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    dispose_all_engines()


app = FastAPI(
    title="Multi-Tenant SaaS (100 Tenants Ready)",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    SecurityMiddleware,
    config=SecurityConfig(
        rate_limit=settings.IP_RATE_LIMIT_PER_MINUTE,
        rate_limit_window=60,
        enable_redis=True,
        redis_url=settings.REDIS_URL,
        redis_prefix="guard:security:",
        enable_penetration_detection=False,
    ),
)

app.include_router(sample.router)
app.include_router(insurance.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
