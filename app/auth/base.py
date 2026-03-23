from abc import ABC, abstractmethod
from typing import Any


class AuthProvider(ABC):

    @abstractmethod
    async def decode_token(self, token: str) -> dict[str, Any]:
        pass

    @abstractmethod
    async def validate_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        pass

    @abstractmethod
    async def validate_app(self, payload: dict[str, Any]) -> dict[str, Any]:
        pass