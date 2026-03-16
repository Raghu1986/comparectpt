from fastapi import Header, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import AsyncGenerator
import structlog

from app.core.secrets import load_database_config
from app.core.engine_cache import get_or_create_engine

logger = structlog.get_logger()


async def get_common_db() -> AsyncGenerator[AsyncSession, None]:
    database_config = await load_database_config()
    db_url = database_config["common_db"]
    engine = get_or_create_engine(db_url)

    async with AsyncSession(engine) as session:
        yield session


async def get_tenant_db(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> AsyncGenerator[AsyncSession, None]:

    database_config = await load_database_config()
    db_url = database_config.get(x_tenant_id)

    if not db_url:
        logger.warning("invalid_tenant", tenant_id=x_tenant_id)
        raise HTTPException(status_code=400, detail="Invalid tenant")

    structlog.contextvars.bind_contextvars(tenant_id=x_tenant_id)
    logger.info("tenant_resolved")

    engine = get_or_create_engine(db_url)

    async with AsyncSession(engine) as session:
        yield session
