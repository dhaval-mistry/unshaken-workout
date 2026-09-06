"""SQLAlchemy database lifecycle helpers."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class Database:
    """Owns the async engine and lightweight database readiness probe."""

    def __init__(self, database_url: str) -> None:
        """Create an engine without opening a connection during application startup."""

        self.engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def check_connection(self) -> bool:
        """Return whether PostgreSQL accepts a minimal database query."""

        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:  # Database details are intentionally withheld from readiness clients.
            return False
        return True

    async def dispose(self) -> None:
        """Close pooled connections during controlled application shutdown."""

        await self.engine.dispose()

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a future request-scoped session with deterministic cleanup."""

        async with self.session_factory() as session:
            yield session
