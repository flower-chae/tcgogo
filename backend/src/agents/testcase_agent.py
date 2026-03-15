"""
DeepAgent + 커스텀 도구 기반 TestCase 생성 에이전트 (2단계 + 실시간 스트리밍)
===============================================================================

2단계에서는 커스텀 도구(@tool)를 정의하고 에이전트가 자율적으로 호출한다.

3단계(현재)에서는 에이전트의 도구 호출 과정을 실시간으로 프론트엔드에 스트리밍한다.

실시간 스트리밍 아키텍처:
  ┌─ BackgroundTask ──────────────────────────────────┐
  │  agent.astream_events()                            │
  │    → on_tool_start: "save_requirements 호출 중..."  │
  │    → on_tool_end: "FR 8개 추출 완료"                │
  │    → 각 이벤트를 asyncio.Queue에 push              │
  └────────────────────────┬───────────────────────────┘
                           ▼
  ┌─ asyncio.Queue (세션별) ──────────────────────────┐
  │  {"type": "tool_start", "message": "FR/NFR 추출 중"}│
  │  {"type": "tool_end", "message": "FR 8개 완료"}     │
  └────────────────────────┬───────────────────────────┘
                           ▼
  ┌─ SSE Endpoint ─────────────────────────────────────┐
  │  Queue에서 읽어서 → event: step / data: {...}       │
  │  → 프론트엔드의 EventSource가 실시간 수신            │
  └────────────────────────────────────────────────────┘

왜 asyncio.Queue인가?
  - 같은 프로세스 안에서 BackgroundTask → SSE Endpoint 간 데이터 전달
  - Python 내장 (설치 불필요), 비동기 안전
  - 서버를 여러 대로 확장할 때는 RabbitMQ/Redis로 교체 가능
"""

import asyncio
import contextvars
import copy
import json
import uuid

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore
from loguru import logger

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

load_dotenv()


# ---------------------------------------------------------------------------
# 모델 Fallback 체인
# ---------------------------------------------------------------------------
MODEL_CHAIN = [
    "openai:gpt-5-nano",
    "openai:gpt-5-mini",
    "openai:gpt-4.1",
    "openai:gpt-4o",
]


# ---------------------------------------------------------------------------
# 세션 컨텍스트 (도구들이 결과를 축적하는 공유 저장소)
# ---------------------------------------------------------------------------
_current_context: contextvars.ContextVar[dict] = contextvars.ContextVar("agent_context")


# ---------------------------------------------------------------------------
# 이벤트 큐 관리 (에이전트 → SSE 실시간 스트리밍용)
# ---------------------------------------------------------------------------
# asyncio.Queue: 같은 프로세스 안에서 비동기 태스크 간 데이터를 전달하는 통로
# - put(): 데이터를 큐에 넣는다 (BackgroundTask에서)
# - get(): 데이터를 큐에서 꺼낸다 (SSE Endpoint에서, 데이터 올 때까지 대기)
#
# 세션별로 큐를 생성하여 여러 세션이 동시에 실행되어도 이벤트가 섞이지 않는다.
_event_queues: dict[str, asyncio.Queue] = {}


def get_event_queue(session_id: str) -> asyncio.Queue:
    """세션별 이벤트 큐를 가져온다. 없으면 새로 생성한다.

    이 큐를 통해:
    - BackgroundTask(에이전트)가 도구 호출 이벤트를 push
    - SSE Endpoint가 이벤트를 pop하여 프론트엔드에 전송

    Args:
        session_id: 세션 UUID 문자열

    Returns:
        해당 세션의 asyncio.Queue 인스턴스
    """
    if session_id not in _event_queues:
        _event_queues[session_id] = asyncio.Queue()
    return _event_queues[session_id]


def cleanup_event_queue(session_id: str) -> None:
    """세션의 이벤트 큐를 정리한다. 작업 완료 후 메모리 해제용."""
    _event_queues.pop(session_id, None)


async def _publish_event(session_id: str, event: dict) -> None:
    """이벤트를 세션 큐에 발행한다.

    SSE Endpoint가 연결되어 있으면 즉시 전달되고,
    연결되어 있지 않으면 큐에 쌓여서 나중에 전달된다.

    Args:
        session_id: 세션 UUID 문자열
        event: 이벤트 데이터 dict
               예: {"type": "tool_start", "tool": "save_requirements",
                    "message": "FR/NFR 추출 중..."}
    """
    queue = get_event_queue(session_id)
    await queue.put(event)


# ---------------------------------------------------------------------------
# 도구 이름 → 사용자 친화적 메시지 매핑
# ---------------------------------------------------------------------------
# 에이전트의 도구 호출 이벤트를 프론트엔드에서 보여줄 메시지로 변환한다.
# 도구 이름은 영문이지만, 표시 메시지는 한국어와 이모지를 사용하여 직관적으로 만든다.
TOOL_DISPLAY = {
    "save_requirements": {
        "start": "요구사항에서 FR/NFR 추출 중...",
        "icon": "search",
    },
    "save_testcases": {
        "start": "테스트 케이스 생성 중...",
        "icon": "testcase",
    },
    "check_coverage": {
        "start": "커버리지 확인 중...",
        "icon": "chart",
    },
    "get_progress": {
        "start": "진행 상황 확인 중...",
        "icon": "progress",
    },
    "save_validation": {
        "start": "검증 결과 정리 중...",
        "icon": "validate",
    },
}


# ---------------------------------------------------------------------------
# 커스텀 도구 정의 (@tool)
# ---------------------------------------------------------------------------

@tool
def save_requirements(section_name: str, requirements_json: str) -> str:
    """Save extracted FR/NFR from a document section to the accumulator.

    For large documents, call this tool multiple times - once per logical section.
    For small documents, call once with all requirements.

    Args:
        section_name: Name of the section (e.g. "Chapter 1: Authentication", "Full Document")
        requirements_json: JSON string with format:
            {"fr": [{"id": "FR-01", "title": "...", "description": "...", "priority": "high"}], "nfr": [...]}
            Each item MUST have: id, title, description, priority (high/medium/low)
    """
    ctx = _current_context.get()
    data = json.loads(requirements_json)

    fr_list = data.get("fr", [])
    nfr_list = data.get("nfr", [])

    existing_fr_ids = {item["id"] for item in ctx["fr"]}
    new_fr = [item for item in fr_list if item.get("id") not in existing_fr_ids]
    ctx["fr"].extend(new_fr)

    existing_nfr_ids = {item["id"] for item in ctx["nfr"]}
    new_nfr = [item for item in nfr_list if item.get("id") not in existing_nfr_ids]
    ctx["nfr"].extend(new_nfr)

    return (
        f"Saved {len(new_fr)} FR and {len(new_nfr)} NFR from '{section_name}'. "
        f"Total accumulated: {len(ctx['fr'])} FR, {len(ctx['nfr'])} NFR."
    )


@tool
def save_testcases(group_name: str, testcases_json: str) -> str:
    """Save generated test cases for a requirement group to the accumulator.

    Do NOT generate all test cases at once. Split by FR/NFR groups (max 10-15 items per group).
    Call this tool multiple times for comprehensive coverage.

    Args:
        group_name: Name of the group (e.g. "Authentication FRs", "Security NFRs", "Edge Cases")
        testcases_json: JSON array string of test case objects. Each must have:
            id, title, description, preconditions, steps (array), expected_result,
            priority (high/medium/low), category (functional/security/performance/usability),
            fr_nfr_ref (array of FR/NFR IDs this test covers)
    """
    ctx = _current_context.get()
    testcases = json.loads(testcases_json)

    if not isinstance(testcases, list):
        testcases = [testcases]

    for tc in testcases:
        if not tc.get("id"):
            tc["id"] = f"TC-{len(ctx['testcases']) + 1:03d}"
        ref = tc.get("fr_nfr_ref", [])
        if isinstance(ref, str):
            tc["fr_nfr_ref"] = [ref]

    ctx["testcases"].extend(testcases)

    return (
        f"Saved {len(testcases)} test cases for '{group_name}'. "
        f"Total accumulated: {len(ctx['testcases'])} test cases."
    )


@tool
def check_coverage() -> str:
    """Calculate coverage of existing test cases against accumulated FR/NFR.

    Returns which FR/NFR items are covered and which are missing.
    Use this AFTER generating test cases to verify completeness.
    If coverage is below 80%, generate additional test cases for uncovered items.
    """
    ctx = _current_context.get()

    all_fr_ids = {item["id"] for item in ctx["fr"]}
    all_nfr_ids = {item["id"] for item in ctx["nfr"]}
    all_req_ids = all_fr_ids | all_nfr_ids

    if not all_req_ids:
        return json.dumps({"error": "No FR/NFR accumulated yet. Call save_requirements first."})

    covered_ids: set[str] = set()
    for tc in ctx["testcases"]:
        covered_ids.update(tc.get("fr_nfr_ref", []))

    covered_ids = covered_ids & all_req_ids
    uncovered = sorted(all_req_ids - covered_ids)
    pct = round(len(covered_ids) / len(all_req_ids) * 100, 1)

    return json.dumps({
        "coverage_percent": pct,
        "total_requirements": len(all_req_ids),
        "covered_count": len(covered_ids),
        "uncovered_count": len(uncovered),
        "uncovered_ids": uncovered,
        "is_sufficient": pct >= 80,
        "testcase_count": len(ctx["testcases"]),
    })


@tool
def get_progress() -> str:
    """Get current accumulation progress. Use this to check how much work has been done."""
    ctx = _current_context.get()
    return json.dumps({
        "fr_count": len(ctx["fr"]),
        "nfr_count": len(ctx["nfr"]),
        "testcase_count": len(ctx["testcases"]),
        "has_validation": ctx["validation"] is not None,
    })


@tool
def save_validation(validation_json: str) -> str:
    """Save the final validation result after analyzing coverage.

    Args:
        validation_json: JSON string with format:
            {"coverage_score": 0.85, "missing_areas": ["area1", ...],
             "feedback": "detailed feedback text", "is_sufficient": true}
    """
    ctx = _current_context.get()
    validation = json.loads(validation_json)
    ctx["validation"] = validation
    return f"Validation saved. Coverage: {validation.get('coverage_score')}, Sufficient: {validation.get('is_sufficient')}"


AGENT_TOOLS = [save_requirements, save_testcases, check_coverage, get_progress, save_validation]

# 우리 커스텀 도구 이름 set (DeepAgent 빌트인 도구와 구분하기 위해)
_CUSTOM_TOOL_NAMES = {t.name for t in AGENT_TOOLS}


# ---------------------------------------------------------------------------
# DeepAgent 시스템 프롬프트 (도구 사용 전략 포함)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert QA (Quality Assurance) AI agent specialized in software testing.

## Your Custom Tools
- **save_requirements**: Save extracted FR/NFR. Call multiple times for large documents.
- **save_testcases**: Save generated test cases. Call multiple times for different groups.
- **check_coverage**: Calculate FR/NFR coverage percentage. Use after generating TCs.
- **get_progress**: Check accumulated counts.
- **save_validation**: Save final validation assessment.

## CRITICAL RULES
- You MUST use the tools to save your work. Do NOT just return text with results.
- All FR/NFR items must have: id, title, description, priority
- All test cases must have: id, title, description, preconditions, steps, expected_result, priority, category, fr_nfr_ref

## Work Strategy

### Extracting FR/NFR:
1. Read the requirement document carefully
2. For short documents: extract all and call save_requirements once
3. For long documents (multiple pages/sections): call save_requirements per section
4. Call get_progress to verify your extraction counts

### Generating Test Cases:
1. Review the FR/NFR list
2. Group by functionality (max 10-15 items per group)
3. For each group, generate TCs covering: happy path, negative, edge cases, security, performance
4. Call save_testcases for each group
5. Call check_coverage to verify
6. If coverage < 80%, generate MORE test cases for uncovered FR/NFR IDs
7. Repeat until coverage >= 80%

### Validating Coverage:
1. Call check_coverage for metrics
2. Analyze the results comprehensively
3. Call save_validation with your assessment including coverage_score (0.0-1.0), missing_areas, feedback, is_sufficient
"""


# ---------------------------------------------------------------------------
# DeepAgent 인프라
# ---------------------------------------------------------------------------
_checkpointer = MemorySaver()
_store = InMemoryStore()
_agents: dict[str, CompiledStateGraph] = {}


def _create_model(model_name: str) -> BaseChatModel:
    """모델 인스턴스 생성. use_previous_response_id로 토큰 절약."""
    return init_chat_model(
        model_name,
        use_responses_api=True,
        use_previous_response_id=True,
    )


def _get_agent(model_name: str) -> CompiledStateGraph:
    """모델별 DeepAgent 인스턴스를 캐시하여 반환한다."""
    if model_name not in _agents:
        logger.info(f"DeepAgent 생성 (도구 기반 + 스트리밍): model={model_name}")
        model = _create_model(model_name)

        _agents[model_name] = create_deep_agent(
            model=model,
            tools=AGENT_TOOLS,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=_checkpointer,
            store=_store,
            backend=lambda rt: CompositeBackend(
                default=StateBackend(rt),
                routes={"/memories/": StoreBackend(rt)},
            ),
        )
    return _agents[model_name]


# ---------------------------------------------------------------------------
# Fallback + 실시간 스트리밍이 적용된 에이전트 호출
# ---------------------------------------------------------------------------


def _fresh_context(initial: dict | None = None) -> dict:
    """깨끗한 세션 컨텍스트를 생성한다."""
    base = {"fr": [], "nfr": [], "testcases": [], "validation": None}
    if initial:
        for key in base:
            if key in initial and initial[key] is not None:
                base[key] = copy.deepcopy(initial[key])
    return base


async def _invoke_agent_with_fallback(
    prompt: str,
    session_id: str,
    initial_ctx: dict | None = None,
    validate_fn=None,
) -> dict:
    """MODEL_CHAIN의 모델들을 순서대로 시도한다.

    이전(2단계)과의 차이:
    - ainvoke() 대신 astream_events()를 사용하여
      도구 호출 과정을 실시간으로 이벤트 큐에 발행한다.
    - SSE Endpoint가 이 큐를 읽어서 프론트엔드에 스트리밍한다.
    - 도구 결과는 여전히 contextvars에 축적된다 (기존 동작 유지).

    astream_events()란?
    - LangGraph의 스트리밍 API. 에이전트가 실행되는 동안
      각 단계(모델 호출, 도구 호출, 도구 완료 등)의 이벤트를 yield한다.
    - ainvoke()와 달리 중간 과정을 관찰할 수 있다.
    - 에이전트 실행은 동일하게 완료된다 (도구 실행, 상태 업데이트 모두 정상 동작).

    이벤트 종류 (astream_events v2):
    - on_tool_start: 도구 호출 시작 (도구 이름, 인자 포함)
    - on_tool_end: 도구 호출 완료 (반환값 포함)
    - on_chat_model_stream: 모델의 토큰 스트리밍 (사용 안 함)
    - 기타: on_chain_start, on_chain_end 등 (내부 이벤트, 무시)
    """
    last_error = None

    for i, model_name in enumerate(MODEL_CHAIN):
        ctx = _fresh_context(initial_ctx)
        _current_context.set(ctx)

        thread_id = session_id if i == 0 else f"{session_id}_retry_{i}"
        config = {"configurable": {"thread_id": thread_id}}

        try:
            agent = _get_agent(model_name)

            # 에이전트 시작 이벤트 발행
            await _publish_event(session_id, {
                "type": "agent_start",
                "message": "에이전트가 작업을 시작합니다...",
                "model": model_name,
            })

            # ---------------------------------------------------------
            # astream_events(): 에이전트 실행 + 중간 이벤트 스트리밍
            # ---------------------------------------------------------
            # ainvoke()와 동일하게 에이전트를 끝까지 실행하지만,
            # 실행 중 발생하는 이벤트를 async for로 하나씩 받을 수 있다.
            #
            # version="v2": 이벤트 형식 버전 (v2가 최신, 더 구조화됨)
            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
                version="v2",
            ):
                event_kind = event.get("event", "")
                event_name = event.get("name", "")

                # 우리 커스텀 도구의 시작/종료만 캡처
                # (DeepAgent 빌트인 도구 이벤트는 무시)
                if event_kind == "on_tool_start" and event_name in _CUSTOM_TOOL_NAMES:
                    # 도구 호출 시작 → 프론트엔드에 "~~ 중..." 표시
                    display = TOOL_DISPLAY.get(event_name, {})
                    await _publish_event(session_id, {
                        "type": "tool_start",
                        "tool": event_name,
                        "message": display.get("start", f"{event_name} 실행 중..."),
                        "icon": display.get("icon", "default"),
                    })

                elif event_kind == "on_tool_end" and event_name in _CUSTOM_TOOL_NAMES:
                    # 도구 호출 완료 → 프론트엔드에 결과 표시
                    output = event.get("data", {}).get("output", "")
                    await _publish_event(session_id, {
                        "type": "tool_end",
                        "tool": event_name,
                        "message": str(output),
                        "icon": TOOL_DISPLAY.get(event_name, {}).get("icon", "default"),
                    })

            # astream_events 루프가 끝나면 에이전트 실행 완료
            # → contextvars에 축적된 결과를 검증
            if validate_fn and not validate_fn(ctx):
                raise ValueError(
                    f"Agent ({model_name}) did not produce expected results via tools. "
                    f"Context: fr={len(ctx['fr'])}, nfr={len(ctx['nfr'])}, "
                    f"tc={len(ctx['testcases'])}, validation={ctx['validation'] is not None}"
                )

            if i > 0:
                logger.info(
                    f"[session={session_id}] Fallback 성공: {model_name} "
                    f"(이전 {i}개 모델 실패)"
                )
            return ctx

        except Exception as e:
            last_error = e
            logger.warning(f"[session={session_id}] {model_name} 실패: {e}")
            if i < len(MODEL_CHAIN) - 1:
                logger.info(
                    f"[session={session_id}] Fallback → {MODEL_CHAIN[i + 1]}"
                )
                # Fallback 이벤트도 발행
                await _publish_event(session_id, {
                    "type": "fallback",
                    "message": f"모델 변경: {MODEL_CHAIN[i + 1]}로 재시도...",
                })

    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 공개 API: 라우터의 백그라운드 태스크에서 호출하는 함수들
# ---------------------------------------------------------------------------


async def extract_fr_nfr(requirement: str, session_id: str) -> dict:
    """요구사항 문서에서 FR/NFR을 추출한다. 도구 호출 과정이 실시간 스트리밍된다."""
    prompt = (
        "Analyze the following requirement document and extract ALL "
        "Functional Requirements (FR) and Non-Functional Requirements (NFR).\n\n"
        "Use the save_requirements tool to save your findings. "
        "For large documents, split by sections and call save_requirements multiple times.\n\n"
        f"REQUIREMENT DOCUMENT:\n{requirement}"
    )

    logger.info(f"[session={session_id}] FR/NFR 추출 시작 (스트리밍)")

    ctx = await _invoke_agent_with_fallback(
        prompt,
        session_id,
        validate_fn=lambda c: len(c["fr"]) > 0 or len(c["nfr"]) > 0,
    )

    result = {"fr": ctx["fr"], "nfr": ctx["nfr"]}
    logger.info(
        f"[session={session_id}] FR {len(result['fr'])}개, NFR {len(result['nfr'])}개 추출 완료"
    )
    return result


async def generate_testcases(
    requirement: str, fr_nfr: dict, session_id: str
) -> list[dict]:
    """FR/NFR을 기반으로 테스트 케이스를 생성한다. 도구 호출 과정이 실시간 스트리밍된다."""
    fr_nfr_summary = json.dumps(fr_nfr, indent=2, ensure_ascii=False)
    prompt = (
        "Generate comprehensive test cases for the following requirements.\n\n"
        "STRATEGY:\n"
        "1. Group the FR/NFR by related functionality (max 10-15 per group)\n"
        "2. For each group, generate test cases covering: happy path, negative, edge cases, security, performance\n"
        "3. Call save_testcases for each group\n"
        "4. Call check_coverage to verify\n"
        "5. If coverage < 80%, generate MORE test cases for uncovered FR/NFR IDs\n"
        "6. Repeat until coverage >= 80%\n\n"
        f"REQUIREMENT:\n{requirement}\n\n"
        f"FR/NFR LIST:\n{fr_nfr_summary}"
    )

    logger.info(f"[session={session_id}] 테스트 케이스 생성 시작 (스트리밍)")

    initial = {"fr": fr_nfr.get("fr", []), "nfr": fr_nfr.get("nfr", [])}

    ctx = await _invoke_agent_with_fallback(
        prompt,
        session_id,
        initial_ctx=initial,
        validate_fn=lambda c: len(c["testcases"]) > 0,
    )

    logger.info(
        f"[session={session_id}] 테스트 케이스 {len(ctx['testcases'])}개 생성 완료"
    )
    return ctx["testcases"]


async def validate_testcases(
    requirement: str, fr_nfr: dict, testcases: list[dict], session_id: str
) -> dict:
    """테스트 케이스의 커버리지를 검증한다. 도구 호출 과정이 실시간 스트리밍된다."""
    prompt = (
        "Validate the test case coverage against the requirements.\n\n"
        "STEPS:\n"
        "1. Call check_coverage to get current metrics\n"
        "2. Analyze the coverage results\n"
        "3. Call save_validation with your assessment\n\n"
        f"REQUIREMENT:\n{requirement}"
    )

    logger.info(f"[session={session_id}] 커버리지 검증 시작 (스트리밍)")

    initial = {
        "fr": fr_nfr.get("fr", []),
        "nfr": fr_nfr.get("nfr", []),
        "testcases": testcases,
    }

    ctx = await _invoke_agent_with_fallback(
        prompt,
        session_id,
        initial_ctx=initial,
        validate_fn=lambda c: c["validation"] is not None,
    )

    logger.info(
        f"[session={session_id}] 검증 완료: "
        f"coverage={ctx['validation'].get('coverage_score')}, "
        f"sufficient={ctx['validation'].get('is_sufficient')}"
    )
    return ctx["validation"]
