"""
DeepAgent + 커스텀 도구 기반 TestCase 생성 에이전트 (2단계)
==========================================================

1단계에서는 DeepAgent를 "똑똑한 LLM 호출기"로만 사용했다.
→ 프롬프트를 보내고 JSON 텍스트 응답을 받아서 파싱하는 구조
→ 에이전트가 스스로 판단/분할/재시도하지 않음
→ 30페이지 SRS 같은 대규모 요구사항에 대응 불가

2단계에서는 커스텀 도구(@tool)를 정의하고 에이전트가 자율적으로 호출한다.
→ 에이전트가 문서를 섹션별로 나눠서 분석 (save_requirements 여러 번 호출)
→ FR/NFR 그룹별로 TC 생성 (save_testcases 여러 번 호출)
→ 커버리지 검증 후 부족하면 자동 보완 (check_coverage → save_testcases 반복)
→ create_react_agent처럼 에이전트가 도구 호출 순서/횟수를 스스로 결정

비유:
- 1단계: "이 문서 분석해서 JSON으로 줘" (수동 지시)
- 2단계: "이 문서 분석해" → 에이전트가 알아서 도구를 골라서 작업 (자율 판단)

아키텍처:
                                ┌─ save_requirements (FR/NFR 축적)
  사용자 → DeepAgent → 도구 선택 ├─ save_testcases (TC 축적)
                                ├─ check_coverage (커버리지 계산)
                                ├─ get_progress (진행 상황 확인)
                                └─ save_validation (검증 결과 저장)

  도구 호출 결과는 contextvars로 관리되는 세션 컨텍스트에 축적된다.
  에이전트가 작업을 끝내면, 축적된 결과를 읽어서 DB에 저장한다.
"""

import contextvars
import copy
import json
import re
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
# contextvars를 사용하는 이유:
# - asyncio에서 태스크별로 격리된 컨텍스트를 제공한다
# - 세션 A의 백그라운드 태스크와 세션 B의 백그라운드 태스크가 동시 실행되어도
#   각각 자기만의 _current_context를 가진다 (충돌 없음)
# - 에이전트 → 도구 호출 시 같은 async 태스크 내이므로 컨텍스트가 공유됨
_current_context: contextvars.ContextVar[dict] = contextvars.ContextVar("agent_context")


# ---------------------------------------------------------------------------
# 커스텀 도구 정의 (@tool)
# ---------------------------------------------------------------------------
# 이 도구들은 create_deep_agent(tools=[...])에 전달되어 에이전트가 사용한다.
# 에이전트(LLM)가 "어떤 도구를 호출할지, 몇 번 호출할지"를 스스로 판단한다.
#
# 이전 방식 (create_react_agent)과 같은 원리:
#   agent = create_react_agent(model, tools=[tool1, tool2])
# DeepAgent는 여기에 TodoList, SubAgent 등 미들웨어를 자동 추가해준다.
#
# 도구의 인자는 JSON string을 사용한다 (gpt-5-nano 호환성을 위해)
# → 복잡한 중첩 스키마보다 JSON 문자열이 소형 모델에서 더 안정적


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

    # ID 중복 방지: 이미 축적된 ID는 건너뛴다
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

    # ID 보정 및 fr_nfr_ref 정규화
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

    # 실제 존재하는 FR/NFR만 카운트
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


# 에이전트에 전달할 도구 목록
AGENT_TOOLS = [save_requirements, save_testcases, check_coverage, get_progress, save_validation]


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
    """모델별 DeepAgent 인스턴스를 캐시하여 반환한다.

    1단계와의 차이: tools=AGENT_TOOLS를 전달하여
    에이전트가 커스텀 도구를 자율적으로 호출할 수 있다.

    create_deep_agent(tools=[...])의 내부 동작:
    1. 커스텀 도구 + DeepAgent 빌트인 도구(write_todos, ls, read_file 등)를 합침
    2. model.bind_tools(all_tools)로 모델에 도구 스키마를 바인딩
    3. LangGraph 에이전트 루프: 모델 호출 → 도구 선택 → 도구 실행 → 결과 반환 → 반복
    """
    if model_name not in _agents:
        logger.info(f"DeepAgent 생성 (2단계 도구 기반): model={model_name}")
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
# Fallback이 적용된 에이전트 호출 (도구 결과는 컨텍스트에 축적)
# ---------------------------------------------------------------------------


def _fresh_context(initial: dict | None = None) -> dict:
    """깨끗한 세션 컨텍스트를 생성한다."""
    base = {"fr": [], "nfr": [], "testcases": [], "validation": None}
    if initial:
        # deep copy로 원본 오염 방지
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
    """MODEL_CHAIN의 모델들을 순서대로 시도한다. 도구 결과는 컨텍스트에 축적된다.

    1단계와의 차이:
    - 텍스트 응답 대신 도구로 축적된 컨텍스트를 반환한다.
    - validate_fn으로 "에이전트가 도구를 실제로 사용했는지" 검증한다.
    - 각 시도마다 깨끗한 컨텍스트로 시작한다 (실패한 시도의 부분 결과 오염 방지).

    Args:
        prompt: 에이전트에게 보낼 사용자 메시지
        session_id: 대화 컨텍스트 식별자 (세션 UUID)
        initial_ctx: 초기 컨텍스트 (기존 FR/NFR이나 TC가 있는 경우)
        validate_fn: 컨텍스트 검증 함수. ctx를 받아 bool을 반환.
                     False면 "도구를 사용하지 않음"으로 판단하여 fallback 시도.

    Returns:
        도구 호출로 축적된 세션 컨텍스트 dict
    """
    last_error = None

    for i, model_name in enumerate(MODEL_CHAIN):
        # 각 시도마다 깨끗한 컨텍스트 → 실패한 시도의 부분 결과가 다음 시도에 영향 없음
        ctx = _fresh_context(initial_ctx)
        _current_context.set(ctx)

        thread_id = session_id if i == 0 else f"{session_id}_retry_{i}"
        config = {"configurable": {"thread_id": thread_id}}

        try:
            agent = _get_agent(model_name)
            await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
            )

            # 에이전트가 도구를 실제로 사용했는지 검증
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

    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 공개 API: 라우터의 백그라운드 태스크에서 호출하는 함수들
# ---------------------------------------------------------------------------
# 함수 시그니처는 1단계와 동일 → 라우터 변경 최소화
#
# 1단계: 프롬프트 → 텍스트 응답 → JSON 파싱
# 2단계: 프롬프트 → 에이전트가 도구로 결과 축적 → 컨텍스트에서 결과 읽기
# ---------------------------------------------------------------------------


async def extract_fr_nfr(requirement: str, session_id: str) -> dict:
    """요구사항 문서에서 FR/NFR을 추출한다.

    2단계 동작 방식:
    1. 에이전트에게 요구사항 분석을 지시
    2. 에이전트가 스스로 판단하여 save_requirements 도구를 호출
       - 짧은 문서: 1번 호출
       - 긴 문서: 섹션별로 여러 번 호출
    3. 도구 호출 결과가 _current_context에 축적됨
    4. 축적된 컨텍스트에서 FR/NFR을 읽어서 반환

    Args:
        requirement: 요구사항/SRS/PRD 원문 텍스트
        session_id: DB 세션 UUID 문자열

    Returns:
        {"fr": [...], "nfr": [...]}
    """
    prompt = (
        "Analyze the following requirement document and extract ALL "
        "Functional Requirements (FR) and Non-Functional Requirements (NFR).\n\n"
        "Use the save_requirements tool to save your findings. "
        "For large documents, split by sections and call save_requirements multiple times.\n\n"
        f"REQUIREMENT DOCUMENT:\n{requirement}"
    )

    logger.info(f"[session={session_id}] FR/NFR 추출 시작 (2단계 도구 기반)")

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
    """FR/NFR을 기반으로 테스트 케이스를 생성한다.

    2단계 동작 방식:
    1. 기존 FR/NFR을 초기 컨텍스트에 로드
    2. 에이전트에게 TC 생성을 지시
    3. 에이전트가 스스로:
       - FR/NFR을 그룹별로 나눠서 save_testcases 여러 번 호출
       - check_coverage로 커버리지 검증
       - 80% 미만이면 추가 TC 생성 (자동 보완 루프)
    4. 최종 축적된 TC 반환
    """
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

    logger.info(f"[session={session_id}] 테스트 케이스 생성 시작 (2단계 도구 기반)")

    # 기존 FR/NFR을 초기 컨텍스트에 로드 → check_coverage가 정확히 계산 가능
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
    """테스트 케이스의 커버리지를 검증한다.

    2단계 동작 방식:
    1. 기존 FR/NFR + TC를 초기 컨텍스트에 로드
    2. 에이전트가 check_coverage 도구로 메트릭 확인
    3. 에이전트가 종합 분석 후 save_validation 도구로 결과 저장
    """
    prompt = (
        "Validate the test case coverage against the requirements.\n\n"
        "STEPS:\n"
        "1. Call check_coverage to get current metrics\n"
        "2. Analyze the coverage results\n"
        "3. Call save_validation with your assessment\n\n"
        f"REQUIREMENT:\n{requirement}"
    )

    logger.info(f"[session={session_id}] 커버리지 검증 시작 (2단계 도구 기반)")

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
