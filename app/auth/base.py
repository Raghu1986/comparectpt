from abc import ABC, abstractmethod
from typing import Dict


class AuthProvider(ABC):

    @abstractmethod
    async def decode_token(self, token: str) -> Dict:
        pass

    @abstractmethod
    async def validate_user(self, payload: Dict) -> Dict:
        pass

    @abstractmethod
    async def validate_app(self, payload: Dict) -> Dict:
        pass