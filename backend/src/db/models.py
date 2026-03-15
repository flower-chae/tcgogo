"""
Pydantic 요청/응답 모델
========================

FastAPI에서 요청 본문(Request Body)과 응답(Response)의 형태를 정의한다.

Pydantic이란?
- Python의 데이터 검증 라이브러리
- 클래스를 정의하면 자동으로:
  1. 타입 검증 (문자열이어야 하는데 숫자가 오면 에러)
  2. JSON 직렬화/역직렬화
  3. Swagger 문서 자동 생성

FastAPI + Pydantic:
- 엔드포인트의 매개변수 타입으로 Pydantic 모델을 지정하면
  FastAPI가 자동으로 요청 본문을 파싱하고 검증해준다.

예:
  @router.post("/extract-fr-nfr")
  async def extract(body: ExtractFrNfrRequest):  ← Pydantic 모델
      body.requirement  # 자동 파싱된 값

주의: 여기는 API 모델만 정의. DB 모델(ORM)은 사용하지 않음 (asyncpg + raw SQL).
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 요청 모델 (클라이언트 → 서버)
# ---------------------------------------------------------------------------

class ExtractFrNfrRequest(BaseModel):
    """FR/NFR 추출 요청 본문

    사용 엔드포인트: POST /api/v1/testcase/extract-fr-nfr
    """
    requirement: str  # 요구사항 원문 텍스트 (필수)
    # Literal: 허용되는 값을 제한 (이 세 값만 가능)
    requirement_type: Literal["requirement", "SRS", "PRD"] = "requirement"  # 기본값: "requirement"


class GenerateFromSessionRequest(BaseModel):
    """세션에서 TC 생성 요청 (현재 본문 없음, URL 경로에 session_id 포함)"""
    pass


class GenerateRequest(BaseModel):
    """전체 파이프라인 실행 요청 본문 (FR/NFR 추출 + TC 생성)

    사용 엔드포인트: POST /api/v1/testcase/generate
    """
    requirement: str
    requirement_type: Literal["requirement", "SRS", "PRD"] = "requirement"


# ---------------------------------------------------------------------------
# 응답 모델 (서버 → 클라이언트)
# ---------------------------------------------------------------------------

class GenerateResponse(BaseModel):
    """비동기 작업 시작 응답 (202 Accepted)

    작업이 백그라운드에서 진행되므로, 세션 ID와 현재 상태만 반환한다.
    클라이언트는 이 ID로 폴링하여 완료를 확인한다.
    """
    id: uuid.UUID  # 생성된 세션 UUID
    status: str    # 현재 상태 (예: "extracting", "processing")


class ValidationResult(BaseModel):
    """커버리지 검증 결과"""
    coverage_score: float    # 0.0 ~ 1.0 (예: 0.85 = 85%)
    missing_areas: list[str] # 누락된 영역 목록
    feedback: str            # AI의 상세 피드백
    is_sufficient: bool      # 충분한지 여부


class SessionResponse(BaseModel):
    """세션 상세 응답 (DB의 testcase_sessions 행 하나에 대응)

    사용 엔드포인트: GET /api/v1/testcase/{session_id}
                    GET /api/v1/testcase/ (목록, 이 모델의 배열)
    """
    id: uuid.UUID
    requirement: str | None = None
    requirement_type: str | None = None
    status: str | None = None
    # dict[str, Any]: {"fr": [...], "nfr": [...]} 형태
    fr_nfr: dict[str, Any] | None = None
    # list[Any]: [{"id": "TC-01", ...}, ...] 형태
    testcases: list[Any] | None = None
    # dict[str, Any]: {"coverage_score": 0.85, ...} 형태
    validation: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
