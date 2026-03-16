from fastapi import Depends
from fastapi.security import HTTPBearer
from .manager import provider

security = HTTPBearer()


async def verify_token(credentials=Depends(security)):
    token = credentials.credentials
    return await provider.decode_token(token)


async def require_user(payload=Depends(verify_token)):
    return await provider.validate_user(payload)


async def require_app(payload=Depends(verify_token)):
    return await provider.validate_app(payload)