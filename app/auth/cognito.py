import json

import httpx
from fastapi import HTTPException, status
from jose import jwt

from app.core.redis import redis_client

from .base import AuthProvider


class CognitoAuthProvider(AuthProvider):
    def __init__(
        self,
        *,
        region: str,
        user_pool_id: str,
        user_client_id: str | None = None,
        m2m_client_id: str | None = None,
        required_m2m_scopes: set[str] | None = None,
    ):
        self.region = region
        self.user_pool_id = user_pool_id
        self.user_client_id = user_client_id
        self.m2m_client_id = m2m_client_id
        self.required_m2m_scopes = required_m2m_scopes or set()
        self.issuer = (
            f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        )
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self.jwks_cache_key = f"auth:cognito:jwks:{user_pool_id}"

    async def _get_jwks(self) -> dict:
        cached = await redis_client.get(self.jwks_cache_key)
        if cached:
            return json.loads(cached)

        async with httpx.AsyncClient() as client:
            keys = (await client.get(self.jwks_url)).json()

        await redis_client.set(
            self.jwks_cache_key,
            json.dumps(keys),
            ex=3600,
        )
        return keys

    async def decode_token(self, token: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
            jwks = await self._get_jwks()
            key = next(
                (
                    jwk
                    for jwk in jwks.get("keys", [])
                    if jwk.get("kid") == header.get("kid")
                ),
                None,
            )

            if not key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Signing key not found",
                )

            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False},
            )

            self._validate_client_binding(payload)
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    def _validate_client_binding(self, payload: dict) -> None:
        token_use = payload.get("token_use")

        if token_use == "id":
            if self.user_client_id and payload.get("aud") != self.user_client_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Cognito audience",
                )
            return

        client_id = payload.get("client_id")
        expected_client_ids = {
            client_id_value
            for client_id_value in [self.user_client_id, self.m2m_client_id]
            if client_id_value
        }
        if expected_client_ids and client_id not in expected_client_ids:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Cognito client",
            )

    async def validate_user(self, payload: dict) -> dict:
        token_use = payload.get("token_use")
        client_id = payload.get("client_id")
        audience = payload.get("aud")

        is_user_token = False
        if token_use == "id":
            is_user_token = not self.user_client_id or audience == self.user_client_id
        elif token_use == "access":
            has_username = bool(
                payload.get("username") or payload.get("cognito:username")
            )
            is_user_token = (
                (not self.user_client_id or client_id == self.user_client_id)
                and has_username
            )

        if not is_user_token:
            raise HTTPException(
                status_code=403,
                detail="User token required",
            )

        return {
            "auth_type": "user",
            "provider": "cognito",
            "subject": payload.get("sub"),
            "email": payload.get("email"),
            "username": payload.get("cognito:username") or payload.get("username"),
            "scopes": payload.get("scope", "").split(),
            "claims": payload,
        }

    async def validate_app(self, payload: dict) -> dict:
        if payload.get("token_use") != "access":
            raise HTTPException(
                status_code=403,
                detail="Client credential token required",
            )

        client_id = payload.get("client_id")
        if self.m2m_client_id and client_id != self.m2m_client_id:
            raise HTTPException(
                status_code=403,
                detail="Configured M2M client required",
            )

        scopes = set(payload.get("scope", "").split())
        if self.required_m2m_scopes and not self.required_m2m_scopes.issubset(scopes):
            raise HTTPException(
                status_code=403,
                detail="Required M2M scopes missing",
            )

        return {
            "auth_type": "app",
            "provider": "cognito",
            "client_id": client_id,
            "scopes": sorted(scopes),
            "claims": payload,
        }
