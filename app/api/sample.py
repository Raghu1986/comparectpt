from fastapi import APIRouter, Depends
# from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.deps.db import get_common_db, get_tenant_db
from app.models import User, Invoice
from app.auth.dependencies import require_user, require_app

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


@router.get("/internal/sync")
async def sync(app=Depends(require_app)):
    return {
        "status": "internal access granted",
        "provider": app["provider"],
        "client_id": app.get("client_id"),
        "scopes": app.get("scopes", []),
    }
