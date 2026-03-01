from collections.abc import AsyncIterator

from fastapi import HTTPException
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import settings

# Shared async pool used by FastAPI dependencies.
pool: AsyncConnectionPool | None = None


async def init_db_pool() -> None:
    global pool

    # Keep app booting in non-DB contexts; endpoints will fail explicitly if used.
    if not settings.database_url:
        return

    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        open=False,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()


async def close_db_pool() -> None:
    global pool

    if pool is None:
        return

    await pool.close()
    pool = None


async def get_db_connection() -> AsyncIterator[AsyncConnection]:
    # Centralized guard to avoid obscure None-type errors in route handlers.
    if pool is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured")

    async with pool.connection() as connection:
        yield connection
