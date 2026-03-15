"""
전역 예외 처리
==============

FastAPI에서 발생하는 예외를 잡아서 적절한 HTTP 응답으로 변환한다.

왜 필요한가?
- 예외가 처리되지 않으면 서버가 500 에러와 함께 스택 트레이스를 노출할 수 있다
- 보안상 내부 에러 정보를 클라이언트에 보여주면 안 된다
- 일관된 에러 응답 형식을 제공하여 프론트엔드가 쉽게 처리할 수 있도록 한다

등록 방법 (main.py에서):
  app.add_exception_handler(Exception, global_exception_handler)
  app.add_exception_handler(AppException, app_exception_handler)

예외 처리 순서:
  1. AppException → app_exception_handler (의도적 에러, 적절한 상태 코드)
  2. Exception → global_exception_handler (예상치 못한 에러, 항상 500)
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from loguru import logger


async def global_exception_handler(request: Request, exc: Exception):
    """모든 미처리 예외를 잡는 최종 핸들러.

    어떤 예외도 여기서 잡히면 500 Internal Server Error로 응답한다.
    실제 에러 내용은 로그에만 기록하고, 클라이언트에는 일반적인 메시지만 반환한다.
    (보안: 스택 트레이스, DB 쿼리 등 내부 정보 노출 방지)
    """
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


class AppException(Exception):
    """애플리케이션 커스텀 예외.

    의도적으로 발생시키는 예외에 사용한다.
    상태 코드와 에러 메시지를 직접 지정할 수 있다.

    사용 예:
      raise AppException(status_code=404, detail="Session not found")
      raise AppException(status_code=400, detail="Invalid requirement type")
    """

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code  # HTTP 상태 코드 (400, 404, 422 등)
        self.detail = detail            # 클라이언트에 반환할 에러 메시지


async def app_exception_handler(request: Request, exc: AppException):
    """AppException을 HTTP 응답으로 변환하는 핸들러.

    global_exception_handler와 달리, 여기서는 에러 메시지를 클라이언트에 반환한다.
    (의도적으로 발생시킨 에러이므로 노출해도 안전)
    """
    logger.warning(f"AppException: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
