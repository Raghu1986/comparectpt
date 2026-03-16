import httpx
import json
from jose import jwt
from fastapi import HTTPException, status
from app.core.redis import redis_client
from .base import AuthProvider


class EntraAuthProvider(AuthProvider):

    def __init__(self, tenant_id: str, audience: str):
        self.tenant_id = tenant_id
        self.audience = audience
        self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        self.openid_url = f"{self.issuer}/.well-known/openid-configuration"
        self.jwks_cache_key = "auth:entra:jwks"

    async def _get_jwks(self):
        cached = await redis_client.get(self.jwks_cache_key)
        if cached:
            return json.loads(cached)

        async with httpx.AsyncClient() as client:
            openid = (await client.get(self.openid_url)).json()
            jwks_uri = openid["jwks_uri"]
            keys = (await client.get(jwks_uri)).json()

        await redis_client.set(
            self.jwks_cache_key,
            json.dumps(keys),
            ex=3600,
        )

        return keys

    async def decode_token(self, token: str):

        try:
            jwks = await self._get_jwks()

            payload = jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
            )

            return payload

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    async def validate_user(self, payload):
        if "scp" not in payload:
            raise HTTPException(
                status_code=403,
                detail="User token required",
            )
        return payload

    async def validate_app(self, payload):
        if "roles" not in payload:
            raise HTTPException(
                status_code=403,
                detail="Client credential token required",
            )
        return payload