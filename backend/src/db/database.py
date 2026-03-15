import json
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://deepagent:deepagent1234@localhost:5432/deepagent",
)

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """Create the connection pool and ensure the table exists."""
    global _pool
    async def _init_connection(conn):
        """Set up JSON/JSONB codecs so asyncpg auto-parses them."""
        await conn.set_type_codec(
            'jsonb', encoder=json.dumps, decoder=json.loads,
            schema='pg_catalog',
        )
        await conn.set_type_codec(
            'json', encoder=json.dumps, decoder=json.loads,
            schema='pg_catalog',
        )

    _pool = await asyncpg.create_pool(dsn=DATABASE_URL, init=_init_connection)

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS testcase_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                requirement TEXT NOT NULL,
                requirement_type VARCHAR(20) NOT NULL DEFAULT 'requirement',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                fr_nfr JSONB,
                testcases JSONB,
                validation JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)


async def close_pool() -> None:
    """Gracefully close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the current connection pool. Raises if not initialised."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_db() first.")
    return _pool
