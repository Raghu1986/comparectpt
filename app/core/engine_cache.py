from collections import OrderedDict
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from app.core.config import get_settings
import structlog

settings = get_settings()
logger = structlog.get_logger()

_ENGINE_CACHE: OrderedDict[str, AsyncEngine] = OrderedDict()


def get_or_create_engine(db_url: str) -> AsyncEngine:
    if db_url in _ENGINE_CACHE:
        logger.info("engine_cache_hit")
        _ENGINE_CACHE.move_to_end(db_url)
        return _ENGINE_CACHE[db_url]

    if len(_ENGINE_CACHE) >= settings.MAX_ENGINES:
        _, old_engine = _ENGINE_CACHE.popitem(last=False)
        old_engine.sync_engine.dispose()
        logger.warning("engine_evicted_lru")

    logger.info("engine_created")

    engine = create_async_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        connect_args={
            "prepared_statement_cache_size": 0
        },        
    )

    _ENGINE_CACHE[db_url] = engine
    return engine


def dispose_all_engines():
    for engine in _ENGINE_CACHE.values():
        engine.sync_engine.dispose()
    _ENGINE_CACHE.clear()
