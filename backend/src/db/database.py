"""
PostgreSQL 데이터베이스 연결 관리
=================================

asyncpg를 사용하여 PostgreSQL에 비동기로 연결한다.
SQLAlchemy(ORM)를 사용하지 않고 raw SQL로 직접 쿼리한다 (todo.md 요구사항).

왜 asyncpg인가?
- Python에서 가장 빠른 PostgreSQL 비동기 드라이버
- FastAPI의 async/await 패턴과 자연스럽게 호환
- 커넥션 풀을 자체 지원하여 별도 풀 라이브러리 불필요

커넥션 풀이란?
- DB 연결을 미리 여러 개 만들어두고 재사용하는 패턴
- 매 요청마다 연결/해제하면 느리고 리소스 낭비
- 풀에서 빌려쓰고 반납하는 방식으로 성능 향상
"""

import json
import os

import asyncpg
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
# → OPENAI_API_KEY, DATABASE_URL 등을 읽어옴
load_dotenv()

# DATABASE_URL: PostgreSQL 연결 문자열
# 형식: postgresql://유저:비밀번호@호스트:포트/DB이름
# 로컬: postgresql://deepagent:deepagent1234@localhost:5432/deepagent
# Docker: postgresql://deepagent:deepagent1234@postgres:5432/deepagent
#          (컨테이너 네트워크에서는 서비스명 'postgres'로 접근)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://deepagent:deepagent1234@localhost:5432/deepagent",
)

# 모듈 레벨 변수: 커넥션 풀 인스턴스
# → init_db()에서 생성, close_pool()에서 해제
# → get_pool()로 다른 모듈에서 접근
_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    """커넥션 풀을 생성하고 필요한 테이블을 만든다.

    main.py의 lifespan에서 앱 시작 시 1회 호출된다.

    동작:
    1. asyncpg 커넥션 풀 생성 (dsn=DATABASE_URL)
    2. 각 커넥션에 JSON/JSONB 코덱 설정 (자동 직렬화/역직렬화)
    3. testcase_sessions 테이블이 없으면 생성 (IF NOT EXISTS)
    """
    global _pool

    async def _init_connection(conn):
        """각 커넥션이 생성될 때 실행되는 초기화 함수.

        JSON/JSONB 타입을 Python dict ↔ JSON 문자열로 자동 변환하도록 설정.
        → DB에서 JSONB 컬럼을 읽으면 자동으로 dict/list가 됨
        → dict/list를 JSONB 컬럼에 쓰면 자동으로 JSON 문자열로 변환됨
        """
        await conn.set_type_codec(
            'jsonb', encoder=json.dumps, decoder=json.loads,
            schema='pg_catalog',
        )
        await conn.set_type_codec(
            'json', encoder=json.dumps, decoder=json.loads,
            schema='pg_catalog',
        )

    # 커넥션 풀 생성
    # dsn: 연결 문자열
    # init: 각 커넥션 생성 시 실행할 함수
    _pool = await asyncpg.create_pool(dsn=DATABASE_URL, init=_init_connection)

    # 테이블 생성 (없으면)
    # IF NOT EXISTS: 이미 있으면 무시 (멱등성)
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
    """커넥션 풀을 정리한다. 앱 종료 시 호출."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """현재 커넥션 풀을 반환한다.

    라우터 등 다른 모듈에서 DB 접근 시 사용:
      pool = get_pool()
      async with pool.acquire() as conn:
          rows = await conn.fetch("SELECT * FROM ...")

    Raises:
        RuntimeError: init_db()가 호출되지 않은 경우
    """
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_db() first.")
    return _pool
