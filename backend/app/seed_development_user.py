"""Idempotently create the configured local-only development user."""

import asyncio

from sqlalchemy import text

from app.core.settings import get_settings
from app.infrastructure.db.database import Database


async def seed() -> None:
    settings = get_settings()
    if settings.app_environment != "development" or settings.development_user_id is None:
        raise RuntimeError(
            "Development user seeding is allowed only in development with DEVELOPMENT_USER_ID set"
        )
    database = Database(str(settings.database_url))
    try:
        async with database.new_session() as session:
            await session.execute(
                text(
                    """INSERT INTO users (id, display_name, email)
                    VALUES (:id, :name, :email)
                    ON CONFLICT (id) DO UPDATE SET display_name=excluded.display_name,
                    email=excluded.email, updated_at=now()"""
                ),
                {
                    "id": settings.development_user_id,
                    "name": settings.development_user_display_name,
                    "email": settings.development_user_email,
                },
            )
            await session.commit()
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
