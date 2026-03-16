import aioboto3
import json
import structlog
from app.core.redis import redis_client
from app.core.config import get_settings

settings = get_settings()
logger = structlog.get_logger()

async def get_database_config_from_env() -> dict:
    logger.info("fetching_database_config_from_env")
    secret_dict= settings.DATABASE_CONFIG
    logger.info("database_config_fetched_from_env")
    return secret_dict

async def get_database_config_from_aws() -> dict:
    logger.info("fetching_database_config_from_aws")

    async with aioboto3.Session().client(
        "secretsmanager",
        region_name=settings.AWS_REGION,
    ) as client:
        response = await client.get_secret_value(
            SecretId=settings.SECRET_NAME
        )

    secret_dict = json.loads(response["SecretString"])
    logger.info("database_config_fetched_from_aws")
    return secret_dict

async def load_database_config() -> dict:
    cached = await redis_client.get("database_config")

    if cached:
        logger.info("secret_cache_hit")
        return json.loads(cached)

    logger.info("secret_cache_miss_fetching_from_aws")


    if settings.DB_CRED_SOURCE.upper() == "AWS_SECRET_MANAGER":
        secret_dict = await get_database_config_from_aws()
    else:
        secret_dict = await get_database_config_from_env()    


    await redis_client.set(
        "database_config",
        json.dumps(secret_dict),
        ex=settings.SECRET_CACHE_TTL,
    )

    logger.info("secret_loaded_and_cached")

    return secret_dict
