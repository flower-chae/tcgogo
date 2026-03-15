# ============================================
# FastAPI Boilerplate
# ============================================
# 1. 프로젝트 초기화
#    uv init --python=3.11
#
# 2. 의존성 설치
#    uv add "fastapi[standard]" "loguru"
#
# 3. 서버 실행
#    uv run uvicorn src.main:app --port=3480 --reload --host 0.0.0.0
# ============================================

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.cors import setup_cors
from src.core.exceptions import (
    AppException,
    app_exception_handler,
    global_exception_handler,
)
from src.core.logging import setup_logging
from src.middleware import LoggingMiddleware
from src.routers import sample_router, testcase_router

# 로깅 초기화 (앱 시작 시점에 명시적으로 실행)
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.db.database import close_pool, init_db

    await init_db()
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)

# 예외 핸들러 등록
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(AppException, app_exception_handler)

# 미들웨어 등록
setup_cors(app)
app.add_middleware(LoggingMiddleware)

# 라우터 등록
app.include_router(sample_router)
app.include_router(testcase_router)
