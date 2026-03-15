import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from loguru import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 각 요청에 고유 ID 할당
        request_id = str(uuid.uuid4())[:8]

        with logger.contextualize(request_id=request_id):
            logger.info(f"Request: {request.method} {request.url.path}")
            start_time = time.time()

            # 다음 미들웨어 또는 엔드포인트 실행
            try:
                response = await call_next(request)
                process_time = (time.time() - start_time) * 1000  # 밀리초 단위
                logger.info(f"Response: Status={response.status_code} (took: {process_time:.2f}ms)")

                return response
            except Exception as e:
                # BaseHTTPMiddleware 버그로 인해 여기서 Exception 처리 필요
                # return await general_exception_handler(request, e)
                raise e