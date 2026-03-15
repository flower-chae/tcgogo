"""
TestCase API 라우터
===================

이 파일은 TestCase 생성 관련 모든 API 엔드포인트를 정의한다.

전체 흐름:
1. 클라이언트가 POST 요청 → 엔드포인트가 DB에 세션 생성 + 202 즉시 응답
2. BackgroundTasks로 비동기 작업 시작 (에이전트 호출)
3. 클라이언트가 GET으로 폴링하여 작업 완료 확인
4. 완료 시 결과(FR/NFR, TC, Validation)를 읽어감

API 엔드포인트 목록:
  POST /extract-fr-nfr         → FR/NFR 추출 시작
  POST /generate               → 전체 파이프라인 (추출+생성) 시작
  POST /{session_id}/generate  → 기존 세션에서 TC 생성
  POST /{session_id}/validate  → 커버리지 검증 시작
  GET  /                       → 세션 목록 조회 (최근 20개)
  GET  /{session_id}           → 세션 상세 조회
  GET  /{session_id}/stream    → SSE 스트리밍 (폴링 대안)

비동기 처리 패턴:
  클라이언트 → POST → [세션 생성] → 202 즉시 응답
                      [BackgroundTask 시작]
                      → 에이전트 호출 (수 초~수 분)
                      → DB 업데이트 (status, fr_nfr, testcases 등)
  클라이언트 → GET (폴링) → 상태 확인 → completed이면 결과 읽기
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from src.db.database import get_pool
from src.db.models import (
    ExtractFrNfrRequest,
    GenerateRequest,
    GenerateResponse,
    SessionResponse,
)

# APIRouter: URL 경로별로 엔드포인트를 그룹화하는 FastAPI 기능
# prefix: 이 라우터의 모든 경로 앞에 /api/v1/testcase가 붙는다
# tags: Swagger 문서에서 그룹 이름으로 표시
router = APIRouter(prefix="/api/v1/testcase", tags=["testcase"])


# ---------------------------------------------------------------------------
# Helper: convert asyncpg Record to dict with JSON deserialisation
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record to a plain dict."""
    if row is None:
        return {}
    return dict(row)


def _maybe_parse_json(value):
    """Parse a JSON string if needed, or return as-is if already parsed."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _row_to_session_response(row) -> SessionResponse:
    d = _row_to_dict(row)
    return SessionResponse(
        id=d["id"],
        requirement=d.get("requirement"),
        requirement_type=d.get("requirement_type"),
        status=d.get("status"),
        fr_nfr=_maybe_parse_json(d.get("fr_nfr")),
        testcases=_maybe_parse_json(d.get("testcases")),
        validation=_maybe_parse_json(d.get("validation")),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------


async def _run_extract_fr_nfr(session_id: uuid.UUID, requirement: str) -> None:
    """Background task: FR/NFR 추출 + 완료/실패 이벤트를 큐에 발행.

    실시간 스트리밍 흐름:
    1. DB status를 extracting으로 변경
    2. extract_fr_nfr() 호출 → 내부에서 astream_events()로 도구 이벤트 발행
    3. 완료 시 done 이벤트 발행 (SSE가 이걸 받아서 프론트에 최종 결과 전송)
    4. 실패 시 error 이벤트 발행
    """
    from src.agents.testcase_agent import extract_fr_nfr, _publish_event, cleanup_event_queue

    sid = str(session_id)
    pool = get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
            "extracting", session_id,
        )

        try:
            fr_nfr = await extract_fr_nfr(requirement, sid)

            await conn.execute(
                "UPDATE testcase_sessions SET fr_nfr = $1, status = $2, updated_at = NOW() WHERE id = $3",
                fr_nfr, "extracted", session_id,
            )

            # 완료 이벤트 발행 → SSE가 이걸 받아서 프론트엔드에 결과 전송
            await _publish_event(sid, {
                "type": "done",
                "status": "extracted",
                "message": f"FR {len(fr_nfr.get('fr', []))}개, NFR {len(fr_nfr.get('nfr', []))}개 추출 완료",
            })
        except Exception as exc:
            logger.error(f"FR/NFR extraction failed for session {session_id}: {exc}")
            await conn.execute(
                "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
                "failed", session_id,
            )
            await _publish_event(sid, {
                "type": "error",
                "message": f"FR/NFR 추출 실패: {str(exc)[:200]}",
            })


async def _run_generation(session_id: uuid.UUID) -> None:
    """Background task: TC 생성 + 완료/실패 이벤트를 큐에 발행."""
    from src.agents.testcase_agent import generate_testcases, _publish_event

    sid = str(session_id)
    pool = get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
            "processing", session_id,
        )

        try:
            row = await conn.fetchrow(
                "SELECT requirement, fr_nfr FROM testcase_sessions WHERE id = $1",
                session_id,
            )
            if row is None:
                return

            fr_nfr = row["fr_nfr"] or {"fr": [], "nfr": []}
            testcases = await generate_testcases(row["requirement"], fr_nfr, sid)

            await conn.execute(
                "UPDATE testcase_sessions SET testcases = $1, status = $2, updated_at = NOW() WHERE id = $3",
                testcases, "completed", session_id,
            )

            await _publish_event(sid, {
                "type": "done",
                "status": "completed",
                "message": f"테스트 케이스 {len(testcases)}개 생성 완료",
            })
        except Exception as exc:
            logger.error(f"Test case generation failed for session {session_id}: {exc}")
            await conn.execute(
                "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
                "failed", session_id,
            )
            await _publish_event(sid, {
                "type": "error",
                "message": f"TC 생성 실패: {str(exc)[:200]}",
            })


async def _run_full_pipeline(session_id: uuid.UUID, requirement: str) -> None:
    """Background task: extract FR/NFR then generate test cases."""
    await _run_extract_fr_nfr(session_id, requirement)
    # extract가 실패했으면 여기서 DB status가 이미 failed
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM testcase_sessions WHERE id = $1", session_id
        )
        if row and row["status"] == "failed":
            return  # extract 실패 시 generate 건너뜀
    await _run_generation(session_id)


async def _run_validation(session_id: uuid.UUID) -> None:
    """Background task: 커버리지 검증 + 완료/실패 이벤트를 큐에 발행."""
    from src.agents.testcase_agent import validate_testcases, _publish_event

    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT requirement, fr_nfr, testcases FROM testcase_sessions WHERE id = $1",
            session_id,
        )
        if row is None:
            return

        sid = str(session_id)

        try:
            fr_nfr = row["fr_nfr"] or {"fr": [], "nfr": []}
            validation = await validate_testcases(
                row["requirement"], fr_nfr, row["testcases"] or [], sid,
            )

            await conn.execute(
                "UPDATE testcase_sessions SET validation = $1, updated_at = NOW() WHERE id = $2",
                validation, session_id,
            )

            await _publish_event(sid, {
                "type": "done",
                "status": "validated",
                "message": f"검증 완료: 커버리지 {validation.get('coverage_score', 0) * 100:.0f}%",
            })
        except Exception as exc:
            logger.error(f"Validation failed for session {session_id}: {exc}")
            await conn.execute(
                "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
                "failed", session_id,
            )
            await _publish_event(sid, {
                "type": "error",
                "message": f"검증 실패: {str(exc)[:200]}",
            })


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/extract-fr-nfr", response_model=GenerateResponse, status_code=202)
async def extract_fr_nfr_endpoint(
    body: ExtractFrNfrRequest,
    background_tasks: BackgroundTasks,
):
    """Start async FR/NFR extraction and return immediately."""
    pool = get_pool()
    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO testcase_sessions (id, requirement, requirement_type, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            session_id, body.requirement, body.requirement_type, "pending", now, now,
        )

    background_tasks.add_task(_run_extract_fr_nfr, session_id, body.requirement)

    return GenerateResponse(id=session_id, status="extracting")


@router.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate_testcases_endpoint(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """Start async test-case generation (creates a new session) and return immediately."""
    pool = get_pool()
    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO testcase_sessions (id, requirement, requirement_type, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            session_id, body.requirement, body.requirement_type, "pending", now, now,
        )

    background_tasks.add_task(_run_full_pipeline, session_id, body.requirement)

    return GenerateResponse(id=session_id, status="pending")


@router.post("/{session_id}/generate", response_model=GenerateResponse, status_code=202)
async def generate_from_session(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
):
    """Trigger test-case generation from an existing session's FR/NFR list."""
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, fr_nfr FROM testcase_sessions WHERE id = $1",
            session_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not row["fr_nfr"]:
        raise HTTPException(
            status_code=400,
            detail="Session must have extracted FR/NFR before generating test cases. "
                   "Run extract-fr-nfr first.",
        )

    background_tasks.add_task(_run_generation, session_id)

    return GenerateResponse(id=row["id"], status="processing")


@router.get("/", response_model=list[SessionResponse])
async def list_sessions():
    """Return the 20 most recent test-case sessions."""
    pool = get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM testcase_sessions ORDER BY created_at DESC LIMIT 20"
        )

    return [_row_to_session_response(r) for r in rows]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: uuid.UUID):
    """Get a single test-case session by ID."""
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM testcase_sessions WHERE id = $1",
            session_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return _row_to_session_response(row)


@router.post("/{session_id}/validate")
async def validate_session(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
):
    """Trigger validation of an existing session's test cases."""
    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, testcases, validation FROM testcase_sessions WHERE id = $1",
            session_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if row["status"] != "completed" or not row["testcases"]:
        raise HTTPException(
            status_code=400,
            detail="Session must be in 'completed' status with generated test cases before validation.",
        )

    background_tasks.add_task(_run_validation, session_id)

    return {
        "id": row["id"],
        "validation": row["validation"],
        "message": "Validation started in background.",
    }


# ---------------------------------------------------------------------------
# SSE 스트리밍 엔드포인트 (실시간 에이전트 진행 상황)
# ---------------------------------------------------------------------------
# 이전: 2초마다 DB 폴링 → "processing..." 만 표시
# 현재: asyncio.Queue에서 실시간 이벤트 수신 → 도구 호출 과정을 단계별로 표시
#
# SSE (Server-Sent Events)란?
# - HTTP 연결을 유지하면서 서버 → 클라이언트로 단방향 이벤트를 전송하는 기술
# - WebSocket과 달리 단방향이지만, 구현이 간단하고 HTTP 호환
# - 프론트엔드에서 EventSource API로 수신
#
# 이벤트 종류:
#   event: step    → 에이전트의 중간 과정 (도구 시작/완료)
#   event: done    → 작업 완료 (최종 결과)
#   event: error   → 에러 발생
#
# 프론트엔드 수신 예:
#   const es = new EventSource('/api/v1/testcase/{id}/stream')
#   es.addEventListener('step', (e) => { /* 단계 표시 */ })
#   es.addEventListener('done', (e) => { /* 결과 표시 */ })

TERMINAL_STATUSES = {"completed", "failed"}


@router.get("/{session_id}/stream")
async def stream_session_status(session_id: uuid.UUID):
    """SSE 엔드포인트: 에이전트의 도구 호출 과정을 실시간으로 스트리밍한다.

    동작 흐름:
    1. 프론트엔드가 EventSource로 이 엔드포인트에 연결
    2. BackgroundTask에서 에이전트가 실행되며 이벤트를 asyncio.Queue에 push
    3. 이 엔드포인트가 Queue에서 이벤트를 pop하여 SSE로 전송
    4. done/error 이벤트가 오면 스트림 종료

    Fallback: Queue에서 60초간 이벤트가 없으면 DB 상태를 확인하여
              이미 완료되었는지 체크 (BackgroundTask가 먼저 끝난 경우 대비)
    """
    from src.agents.testcase_agent import get_event_queue, cleanup_event_queue

    sid = str(session_id)

    async def event_generator():
        queue = get_event_queue(sid)

        # 먼저 DB에서 현재 상태 확인 (이미 완료되었을 수 있음)
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM testcase_sessions WHERE id = $1", session_id
            )

        if row is None:
            yield f"event: error\ndata: {json.dumps({'error': 'Session not found'})}\n\n"
            return

        # 이미 완료된 세션이면 즉시 done 이벤트
        if row["status"] in TERMINAL_STATUSES:
            yield f"event: done\ndata: {json.dumps({'type': 'done', 'status': row['status']})}\n\n"
            return

        # Queue에서 이벤트를 실시간으로 읽어서 SSE로 전송
        try:
            while True:
                try:
                    # 60초 타임아웃: 이벤트가 없으면 DB 폴링으로 fallback
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    # 타임아웃 시 DB에서 상태 직접 확인
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow(
                            "SELECT status FROM testcase_sessions WHERE id = $1",
                            session_id,
                        )
                    if row and row["status"] in TERMINAL_STATUSES:
                        yield f"event: done\ndata: {json.dumps({'type': 'done', 'status': row['status']})}\n\n"
                        return
                    # 아직 진행 중이면 heartbeat 보내고 계속 대기
                    yield f"event: heartbeat\ndata: {json.dumps({'type': 'heartbeat'})}\n\n"
                    continue

                event_type = event.get("type", "step")

                if event_type in ("done", "error"):
                    # 완료 또는 에러 → 스트림 종료
                    yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                    return
                else:
                    # 도구 시작/완료 등 중간 이벤트 → step으로 전송
                    yield f"event: step\ndata: {json.dumps(event)}\n\n"

        finally:
            # 스트림 종료 시 큐 정리 (메모리 해제)
            cleanup_event_queue(sid)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
