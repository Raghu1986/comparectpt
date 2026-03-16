from app.core.config import get_settings
from .entra import EntraAuthProvider

settings = get_settings()

# Future switch:
# if settings.AUTH_PROVIDER == "cognito":
#     provider = CognitoAuthProvider(...)
# else:

provider = EntraAuthProvider(
    tenant_id=settings.ENTRA_TENANT_ID,
    audience=settings.ENTRA_AUDIENCE,
)