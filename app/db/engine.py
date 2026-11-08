"""Async SQLAlchemy engine & session factory."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


def make_engine():
    s = get_settings()
    return create_async_engine(s.database_url, pool_size=s.db_pool_size, pool_pre_ping=True)


engine = make_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with SessionFactory() as session:
        yield session
