from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
# from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.deps.db import get_common_db, get_tenant_db
from app.models import User, Invoice
from app.auth.dependencies import require_user, require_app, security
from app.external.aws.cognito import get_cognito_user_details

router = APIRouter(prefix="/sample", tags=["sample"])


@router.get("/combined-read")
async def combined_read(
    common_db: AsyncSession = Depends(get_common_db),
    tenant_db: AsyncSession = Depends(get_tenant_db),
):
    users = (await common_db.exec(select(User))).all()
    invoices = (await tenant_db.exec(select(Invoice))).all()

    return {"users": users, "invoices": invoices}



@router.get("/user/profile")
async def profile(user=Depends(require_user)):
    return {
        "provider": user["provider"],
        "user_id": user["subject"],
        "email": user.get("email"),
        "username": user.get("username"),
        "scopes": user.get("scopes", []),
    }


@router.get("/user/cognito-details")
async def cognito_details(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user=Depends(require_user),
):
    if user.get("provider") != "cognito":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is only available for Cognito-authenticated users.",
        )

    access_token = credentials.credentials
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bearer access token is required.",
        )

    try:
        cognito_user = await get_cognito_user_details(access_token=access_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch Cognito user details: {exc}",
        ) from exc

    return {
        "provider": user["provider"],
        "user_id": user["subject"],
        "username": cognito_user.username,
        "email": cognito_user.attributes.get("email") or user.get("email"),
        "enabled": cognito_user.enabled,
        "user_status": cognito_user.user_status,
        "created_at": cognito_user.user_create_date,
        "updated_at": cognito_user.user_last_modified_date,
        "attributes": cognito_user.attributes,
    }


@router.get("/internal/sync")
async def sync(app=Depends(require_app)):
    return {
        "status": "internal access granted",
        "provider": app["provider"],
        "client_id": app.get("client_id"),
        "scopes": app.get("scopes", []),
    }
