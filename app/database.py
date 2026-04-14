from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import text
from uuid import UUID, uuid4
import sqlalchemy as sa
from typing import AsyncGenerator

from .config import settings


# Base класс для всех моделей
class Base(DeclarativeBase):
    id: Mapped[UUID] = mapped_column(sa.UUID, primary_key=True, default=uuid4)


# Async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True
)

# Async session factory
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Alias for get_session (backward compatibility)"""
    async for session in get_session():
        yield session

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения сессии БД"""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Создание таблиц при запуске приложения"""
    async with engine.begin() as conn:
        # Импорт всех моделей для создания таблиц
        from .models import (
            housing, work, contractor, plan, 
            fact, reconciliation, alert
        )
        await conn.run_sync(Base.metadata.create_all)


async def check_db_connection():
    """Проверка подключения к БД"""
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False