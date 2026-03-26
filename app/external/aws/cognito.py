from dataclasses import dataclass
from typing import Any

import aioboto3

from app.core.config import get_settings

settings = get_settings()


@dataclass(slots=True)
class CognitoUserDetails:
    username: str
    enabled: bool
    user_status: str | None
    user_create_date: Any | None
    user_last_modified_date: Any | None
    attributes: dict[str, str]
    raw: dict[str, Any]


class AsyncCognitoClient:
    def __init__(
        self,
        *,
        region_name: str | None = None,
    ) -> None:
        self._region_name = region_name or settings.COGNITO_REGION or settings.AWS_REGION
        self._session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=self._region_name,
        )

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self._region_name:
            kwargs["region_name"] = self._region_name
        return kwargs

    def client(self):
        return self._session.client("cognito-idp", **self._client_kwargs())

    @staticmethod
    def _attributes_to_dict(attributes: list[dict[str, Any]] | None) -> dict[str, str]:
        if not attributes:
            return {}
        return {
            str(attribute["Name"]): str(attribute.get("Value", ""))
            for attribute in attributes
            if attribute.get("Name")
        }

    async def get_user(self, *, access_token: str) -> CognitoUserDetails:
        async with self.client() as cognito_client:
            response = await cognito_client.get_user(
                AccessToken=access_token,
            )

        return CognitoUserDetails(
            username=response["Username"],
            enabled=bool(response.get("Enabled", True)),
            user_status=response.get("UserStatus"),
            user_create_date=response.get("UserCreateDate"),
            user_last_modified_date=response.get("UserLastModifiedDate"),
            attributes=self._attributes_to_dict(response.get("UserAttributes")),
            raw=response,
        )


async def get_cognito_user_details(*, access_token: str) -> CognitoUserDetails:
    return await AsyncCognitoClient().get_user(access_token=access_token)


__all__ = [
    "AsyncCognitoClient",
    "CognitoUserDetails",
    "get_cognito_user_details",
]
