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
    """Background task: extract FR/NFR and update the DB session."""
    from src.agents.testcase_agent import extract_fr_nfr

    pool = get_pool()

    async with pool.acquire() as conn:
        # Mark as extracting
        await conn.execute(
            "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
            "extracting", session_id,
        )

        try:
            fr_nfr = await extract_fr_nfr(requirement)

            await conn.execute(
                "UPDATE testcase_sessions SET fr_nfr = $1, status = $2, updated_at = NOW() WHERE id = $3",
                fr_nfr, "extracted", session_id,
            )
        except Exception as exc:
            logger.error(f"FR/NFR extraction failed for session {session_id}: {exc}")
            await conn.execute(
                "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
                "failed", session_id,
            )


async def _run_generation(session_id: uuid.UUID) -> None:
    """Background task: generate test cases and update the DB session."""
    from src.agents.testcase_agent import generate_testcases

    pool = get_pool()

    async with pool.acquire() as conn:
        # Mark as processing
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
            testcases = await generate_testcases(row["requirement"], fr_nfr)

            await conn.execute(
                "UPDATE testcase_sessions SET testcases = $1, status = $2, updated_at = NOW() WHERE id = $3",
                testcases, "completed", session_id,
            )
        except Exception as exc:
            logger.error(f"Test case generation failed for session {session_id}: {exc}")
            await conn.execute(
                "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
                "failed", session_id,
            )


async def _run_full_pipeline(session_id: uuid.UUID, requirement: str) -> None:
    """Background task: extract FR/NFR then generate test cases."""
    await _run_extract_fr_nfr(session_id, requirement)
    await _run_generation(session_id)


async def _run_validation(session_id: uuid.UUID) -> None:
    """Background task: validate existing test cases and update the DB session."""
    from src.agents.testcase_agent import validate_testcases

    pool = get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT requirement, fr_nfr, testcases FROM testcase_sessions WHERE id = $1",
            session_id,
        )
        if row is None:
            return

        try:
            fr_nfr = row["fr_nfr"] or {"fr": [], "nfr": []}
            validation = await validate_testcases(
                row["requirement"], fr_nfr, row["testcases"] or [],
            )

            await conn.execute(
                "UPDATE testcase_sessions SET validation = $1, updated_at = NOW() WHERE id = $2",
                validation, session_id,
            )
        except Exception as exc:
            logger.error(f"Validation failed for session {session_id}: {exc}")
            await conn.execute(
                "UPDATE testcase_sessions SET status = $1, updated_at = NOW() WHERE id = $2",
                "failed", session_id,
            )


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
# SSE streaming endpoint
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = {"completed", "failed"}


@router.get("/{session_id}/stream")
async def stream_session_status(session_id: uuid.UUID):
    """SSE endpoint that polls session status every 2 seconds until terminal state."""

    async def event_generator():
        pool = get_pool()
        while True:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, status, fr_nfr, testcases, validation, updated_at FROM testcase_sessions WHERE id = $1",
                    session_id,
                )

            if row is None:
                yield f"event: error\ndata: {json.dumps({'error': 'Session not found'})}\n\n"
                return

            payload = {
                "id": str(row["id"]),
                "status": row["status"],
                "has_fr_nfr": row["fr_nfr"] is not None,
                "has_testcases": row["testcases"] is not None,
                "has_validation": row["validation"] is not None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
            yield f"event: status\ndata: {json.dumps(payload)}\n\n"

            if row["status"] in TERMINAL_STATUSES:
                yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                return

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
