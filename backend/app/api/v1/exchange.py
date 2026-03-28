"""거래소 계정 관리 API."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ALLOWED_EXCHANGE_IDS
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.security import decrypt_api_key, encrypt_api_key
from app.database import get_db
from app.dependencies import get_current_user
from app.models.exchange_account import ExchangeAccount
from app.models.user import User

router = APIRouter(prefix="/exchange", tags=["exchange"])


class ExchangeAccountCreate(BaseModel):
    exchange_id: str
    label: str
    api_key: str
    api_secret: str
    is_testnet: bool = False


class ExchangeAccountResponse(BaseModel):
    id: uuid.UUID
    exchange_id: str
    label: str
    is_testnet: bool
    is_active: bool
    last_synced_at: str | None

    model_config = {"from_attributes": True}


@router.get("/accounts", response_model=list[ExchangeAccountResponse])
async def list_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> list[ExchangeAccountResponse]:
    result = await db.execute(
        select(ExchangeAccount).where(ExchangeAccount.user_id == current_user.id)
    )
    accounts = result.scalars().all()
    return [
        ExchangeAccountResponse(
            id=a.id,
            exchange_id=a.exchange_id,
            label=a.label,
            is_testnet=a.is_testnet,
            is_active=a.is_active,
            last_synced_at=a.last_synced_at.isoformat() if a.last_synced_at else None,
        )
        for a in accounts
    ]


@router.post("/accounts", response_model=ExchangeAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: ExchangeAccountCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> ExchangeAccountResponse:
    if data.exchange_id not in ALLOWED_EXCHANGE_IDS:
        from app.core.exceptions import BadRequestException
        raise BadRequestException(
            f"exchange_id must be one of {ALLOWED_EXCHANGE_IDS}"
        )

    account = ExchangeAccount(
        id=uuid.uuid4(),
        user_id=current_user.id,
        exchange_id=data.exchange_id,
        label=data.label,
        api_key_encrypted=encrypt_api_key(data.api_key),
        api_secret_encrypted=encrypt_api_key(data.api_secret),
        is_testnet=data.is_testnet,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return ExchangeAccountResponse(
        id=account.id,
        exchange_id=account.exchange_id,
        label=account.label,
        is_testnet=account.is_testnet,
        is_active=account.is_active,
        last_synced_at=None,
    )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(ExchangeAccount).where(ExchangeAccount.id == account_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise NotFoundException(f"Exchange account {account_id} not found")
    if account.user_id != current_user.id:
        raise ForbiddenException()
    await db.delete(account)
    await db.commit()


@router.get("/supported")
async def supported_exchanges() -> dict:
    """지원하는 거래소 목록을 반환합니다."""
    return {"exchanges": sorted(ALLOWED_EXCHANGE_IDS)}
