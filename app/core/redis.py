import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()

redis_client = redis.from_url(
    settings.REDIS_URL, # must start with rediss://
    decode_responses=True,
    # ssl_cert_reqs=None,# only if TLS
    socket_timeout=5,
    retry_on_timeout=True
)
