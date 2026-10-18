"""Request-scoped database and temporary local identity dependencies."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.new_session() as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user_id(request: Request, db: DatabaseSession) -> UUID:
    """Resolve only the configured local identity and fail closed elsewhere."""

    settings = request.app.state.settings
    if settings.app_environment != "development" or settings.development_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "identity_unavailable", "message": "Authentication is unavailable."},
        )
    user_id = settings.development_user_id
    found = await db.scalar(text("SELECT id FROM users WHERE id = :id"), {"id": user_id})
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "identity_unavailable", "message": "Authentication is unavailable."},
        )
    return UUID(str(found))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
