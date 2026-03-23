from app.core.config import get_settings
from .cognito import CognitoAuthProvider
from .entra import EntraAuthProvider

settings = get_settings()

if settings.AUTH_PROVIDER.lower() == "cognito":
    if not settings.COGNITO_REGION or not settings.COGNITO_USER_POOL_ID:
        raise ValueError(
            "COGNITO_REGION and COGNITO_USER_POOL_ID are required when AUTH_PROVIDER=cognito"
        )

    provider = CognitoAuthProvider(
        region=settings.COGNITO_REGION,
        user_pool_id=settings.COGNITO_USER_POOL_ID,
        user_client_id=settings.COGNITO_USER_CLIENT_ID,
        m2m_client_id=settings.COGNITO_M2M_CLIENT_ID,
        required_m2m_scopes=settings.cognito_m2m_required_scopes,
    )
else:
    if not settings.ENTRA_TENANT_ID or not settings.ENTRA_AUDIENCE:
        raise ValueError(
            "ENTRA_TENANT_ID and ENTRA_AUDIENCE are required when AUTH_PROVIDER=entra"
        )

    provider = EntraAuthProvider(
        tenant_id=settings.ENTRA_TENANT_ID,
        audience=settings.ENTRA_AUDIENCE,
    )
