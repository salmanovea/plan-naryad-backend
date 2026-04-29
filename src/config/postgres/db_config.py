import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.logger import LoggerProvider
from src.config.settings import app_config

log = LoggerProvider().get_logger(__name__)

database_url = URL.create(**app_config.get_db_creds)
async_engine = create_async_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=15,
    max_overflow=30,
    pool_timeout=100.0,
    echo=app_config.db_show_queries,
)
async_session = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            log.warning("Session rollback because of exception: %s", e)
            log.error(f"Unexpected error occurred: {str(e)}\n{traceback.format_exc()}")
            await session.rollback()
            raise e
        finally:
            await session.close()


async def get_session():
    async with get_async_session() as session:
        yield session
