from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_CRED_SOURCE: str = "CONFIG"
    DATABASE_CONFIG: dict[str, str] = {}

    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_REQUEST_TIMEOUT_SECONDS: float = 120.0

    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str | None = None
    SECRET_NAME: str = "database"

    REDIS_URL: str  # rediss://:password@host:port/db

    MAX_ENGINES: int = 20  # Maximum number of distinct tenant DB engines cached per worker process.
    DB_POOL_SIZE: int = 5  # Number of persistent connections per engine. Each tenant DB engine maintains a pool of 5 open connections.
    DB_MAX_OVERFLOW: int = 10  # Extra temporary connections allowed beyond pool size.

    SECRET_CACHE_TTL: int = 300  # seconds How long (seconds) Redis caches the AWS secret.300 seconds = 5 minutes
    TENANT_RATE_LIMIT_PER_MINUTE: int = 120
    IP_RATE_LIMIT_PER_MINUTE: int = 300  # Per IP

    AUTH_PROVIDER: str = "entra"

    ENTRA_TENANT_ID: str | None = None
    ENTRA_AUDIENCE: str | None = None

    COGNITO_REGION: str | None = None
    COGNITO_USER_POOL_ID: str | None = None
    COGNITO_USER_CLIENT_ID: str | None = None
    COGNITO_M2M_CLIENT_ID: str | None = None
    COGNITO_M2M_REQUIRED_SCOPES: str = ""  # Comma-separated list of required scopes for M2M tokens, e.g. "scope1,scope2"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cognito_m2m_required_scopes(self) -> set[str]:
        return {
            scope.strip()
            for scope in self.COGNITO_M2M_REQUIRED_SCOPES.split(",")
            if scope.strip()
        }

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = Settings()
