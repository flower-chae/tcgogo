"""
HTTP 요청/응답 로깅 미들웨어
=============================

모든 HTTP 요청과 응답을 자동으로 로그에 기록한다.

미들웨어란?
- 모든 요청/응답이 지나가는 "통로" (양파 껍질 구조)
- 요청이 엔드포인트에 도달하기 전, 응답이 클라이언트에 전달되기 전에
  공통 처리(로깅, 인증, CORS 등)를 수행한다.

요청 흐름:
  클라이언트 → [CORS 미들웨어] → [이 로깅 미들웨어] → [엔드포인트]
                                                      ↓ 처리
  클라이언트 ← [CORS 미들웨어] ← [이 로깅 미들웨어] ← [응답]

이 미들웨어가 기록하는 정보:
  - 요청: HTTP 메서드 + URL 경로 (예: "GET /api/v1/testcase/")
  - 응답: 상태 코드 + 처리 시간 (예: "Status=200 (took: 15.23ms)")
  - 요청 ID: 각 요청에 고유 UUID 부여 (로그 추적용)

로그 출력 예:
  2026-03-15 20:30:00 | INFO | [a1b2c3d4] | Request: POST /api/v1/testcase/extract-fr-nfr
  2026-03-15 20:30:05 | INFO | [a1b2c3d4] | Response: Status=202 (took: 5123.45ms)
"""

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from loguru import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """모든 HTTP 요청/응답을 로깅하는 미들웨어.

    BaseHTTPMiddleware를 상속하면 dispatch() 메서드만 구현하면 된다.
    FastAPI가 모든 요청에 대해 자동으로 dispatch()를 호출한다.
    """

    async def dispatch(self, request: Request, call_next):
        """요청을 받아서 처리하고 응답을 반환한다.

        Args:
            request: HTTP 요청 객체 (method, url, headers 등)
            call_next: 다음 미들웨어 또는 엔드포인트를 호출하는 함수.
                       이걸 호출해야 실제 엔드포인트가 실행된다.
        """
        # 각 요청에 고유 ID 할당 (8자리 UUID)
        # → 같은 요청의 로그 라인을 추적할 수 있다
        # → 예: [a1b2c3d4] Request: ... / [a1b2c3d4] Response: ...
        request_id = str(uuid.uuid4())[:8]

        # logger.contextualize(): 이 블록 안의 모든 로그에 request_id를 자동 추가
        # → 로그 포맷의 {extra[request_id]} 부분에 삽입됨
        with logger.contextualize(request_id=request_id):
            logger.info(f"Request: {request.method} {request.url.path}")
            start_time = time.time()

            # call_next(request): 다음 미들웨어 또는 엔드포인트 실행
            # → 이 줄에서 실제 요청 처리가 일어난다
            # → 반환값은 HTTP 응답 객체
            try:
                response = await call_next(request)
                # 처리 시간 계산 (밀리초)
                process_time = (time.time() - start_time) * 1000
                logger.info(f"Response: Status={response.status_code} (took: {process_time:.2f}ms)")

                return response
            except Exception as e:
                # 미들웨어에서 예외가 발생하면 위로 전파
                # → global_exception_handler가 처리
                raise e
