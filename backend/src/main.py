# ============================================
# FastAPI 앱 진입점 (main.py)
# ============================================
# 이 파일은 백엔드 서버의 시작점이다.
# FastAPI 앱 인스턴스를 생성하고, 미들웨어/라우터/예외핸들러를 등록한다.
#
# 실행 방법:
#   uv run uvicorn src.main:app --port=3480 --reload --host 0.0.0.0
#
# 위 명령어의 의미:
#   uvicorn: ASGI 웹 서버 (FastAPI를 실행하는 서버)
#   src.main:app: 이 파일(src/main.py)의 app 변수를 실행
#   --port=3480: 3480번 포트에서 리슨
#   --reload: 코드 변경 시 자동 재시작 (개발용)
#   --host 0.0.0.0: 외부에서도 접근 가능 (기본값은 127.0.0.1)
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

# 로깅 초기화 (앱 시작 시점에 한 번 실행)
# → var/logs/ 디렉토리에 로그 파일 생성
# → 콘솔 출력 설정
setup_logging()


# ---------------------------------------------------------------------------
# Lifespan: 앱 시작/종료 시 실행되는 코드
# ---------------------------------------------------------------------------
# @asynccontextmanager: "시작 시 실행할 코드 / 종료 시 실행할 코드"를 정의
#
# yield 이전: 앱 시작 시 실행 (DB 연결 등)
# yield 이후: 앱 종료 시 실행 (DB 연결 해제 등)
#
# 왜 lifespan을 쓰는가?
# - DB 커넥션 풀을 앱 시작 시 1번만 생성하고, 종료 시 정리
# - 매 요청마다 커넥션을 생성/해제하는 것보다 훨씬 효율적
@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.db.database import close_pool, init_db

    await init_db()    # DB 커넥션 풀 생성 + 테이블 생성
    yield              # 앱 실행 중... (요청 처리)
    await close_pool() # 앱 종료 시 커넥션 풀 정리


# ---------------------------------------------------------------------------
# FastAPI 앱 인스턴스 생성
# ---------------------------------------------------------------------------
# FastAPI(): ASGI 앱 인스턴스 생성
# lifespan: 위에서 정의한 시작/종료 핸들러
app = FastAPI(lifespan=lifespan)

# ---------------------------------------------------------------------------
# 예외 핸들러 등록
# ---------------------------------------------------------------------------
# Exception: 모든 미처리 예외를 잡아서 500 응답으로 변환 (보안: 내부 에러 노출 방지)
# AppException: 의도적으로 발생시킨 예외를 적절한 상태 코드로 변환
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(AppException, app_exception_handler)

# ---------------------------------------------------------------------------
# 미들웨어 등록 (요청 → 미들웨어 체인 → 라우터)
# ---------------------------------------------------------------------------
# 미들웨어: 모든 요청/응답이 지나가는 "통로"
# 순서가 중요하다: 먼저 등록한 미들웨어가 바깥쪽 (양파 껍질 구조)
#
# 요청 흐름:
#   클라이언트 → CORS → LoggingMiddleware → 라우터(엔드포인트)
#                                          → 응답
#              ← CORS ← LoggingMiddleware ← 응답

# CORS 미들웨어: 브라우저의 교차 출처 요청을 허용
# (프론트엔드 localhost:3482 → 백엔드 localhost:3480 요청이 가능하도록)
setup_cors(app)

# 로깅 미들웨어: 모든 요청/응답을 로그에 기록 (요청 ID, 처리 시간 등)
app.add_middleware(LoggingMiddleware)

# ---------------------------------------------------------------------------
# 라우터 등록 (URL 경로 → 처리 함수 매핑)
# ---------------------------------------------------------------------------
# 라우터: URL 경로별로 처리 함수를 모아놓은 그룹
#
# sample_router: /api/v1/sample/ → 헬스체크 등
# testcase_router: /api/v1/testcase/ → FR/NFR 추출, TC 생성, 검증 등
app.include_router(sample_router)
app.include_router(testcase_router)
