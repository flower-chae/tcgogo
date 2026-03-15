# Claude TODO - DeepAgent 프로젝트 실제 작업 목록

> todo.md 요구사항 vs 현재 구현 상태를 비교하여 정리한 실제 해야 할 작업들

---

## 1. DeepAgent + OpenAI Responses API 전환 ✅ 완료

**이전**: `openai` SDK 직접 호출 (`AsyncOpenAI()` → `client.chat.completions.create()`)
**현재**: `create_deep_agent(model="openai:gpt-5-nano")` + Responses API 자동 활성화

### 완료된 작업
- [x] `testcase_agent.py` 전면 재작성 — DeepAgent 기반
- [x] Responses API 자동 활성화 + `use_previous_response_id=True` (토큰 절약)
- [x] MemorySaver + thread_id(=session_id)로 대화 컨텍스트 자동 유지
- [x] CompositeBackend 구성 (StateBackend + StoreBackend)
- [x] 라우터에서 session_id를 에이전트에 전달하도록 수정

### 문제점 (1단계의 한계)
현재는 DeepAgent를 **"똑똑한 LLM 호출기"로만 사용** 중:
- 커스텀 도구(@tool) 없이 프롬프트 → JSON 텍스트 응답만 받는 구조
- 에이전트가 스스로 판단/분할/재시도하지 않음
- 30페이지 SRS 같은 대규모 요구사항에 대응 불가 (한번에 처리해야 하므로)
- DeepAgent의 TodoList, SubAgent 등 핵심 기능 미활용

---

## 2. 도구 기반 에이전트 전환 (2단계) ✅ 완료

**현재**: 고정 파이프라인 (extract 1회 → generate 1회 → validate 1회)
**목표**: 에이전트가 도구를 자율적으로 선택/반복하여 대규모 요구사항 대응

### 왜 필요한가

```
30페이지 SRS → FR 47개 → TC 100개+ 예상

현재 방식의 한계:
- 한번의 LLM 호출로 47개 FR 추출 → 누락 발생
- 한번의 LLM 호출로 100개+ TC 생성 → 품질 저하
- 커버리지 부족해도 자동 보완 불가

에이전트 방식:
- 문서를 섹션별로 나눠서 FR/NFR 추출 (여러 번 호출)
- FR 그룹별로 TC 생성 (품질 유지)
- 커버리지 검증 후 부족하면 자동으로 TC 추가 생성
```

### 설계

#### 정의할 커스텀 도구 (@tool)

```python
@tool
def analyze_requirement_section(section_text: str, section_name: str) -> str:
    """요구사항 문서의 한 섹션에서 FR/NFR을 추출한다.
    대규모 문서는 섹션별로 나눠서 이 도구를 여러 번 호출한다."""

@tool
def generate_testcases_for_group(
    requirement_context: str,
    fr_nfr_ids: list[str],
    focus_area: str
) -> str:
    """특정 FR/NFR 그룹에 대한 테스트 케이스를 생성한다.
    한번에 모든 TC를 만들지 않고, 그룹별로 나눠서 호출한다.
    focus_area: functional, security, performance, edge_case 등"""

@tool
def validate_coverage(
    fr_nfr_summary: str,
    testcases_summary: str
) -> str:
    """현재까지 생성된 TC의 커버리지를 검증한다.
    부족한 영역을 반환하면 에이전트가 추가 TC 생성을 판단한다."""

@tool
def merge_results(partial_results: list[str]) -> str:
    """여러 번의 도구 호출 결과를 하나로 합친다."""
```

#### 에이전트 동작 흐름 (에이전트가 스스로 판단)

```
사용자: "이 30페이지 SRS를 분석해줘"

에이전트 사고:
  "30페이지라 한번에 하면 누락될 수 있다"
  → analyze_requirement_section("1장: 사용자 인증", ...)
  → analyze_requirement_section("2장: 결제 처리", ...)
  → analyze_requirement_section("3장: 관리자 기능", ...)
  → merge_results([1장 결과, 2장 결과, 3장 결과])
  "FR 47개, NFR 12개 추출됐다. TC를 만들자"
  "한번에 100개는 품질이 떨어지니 그룹별로 나누자"
  → generate_testcases_for_group(FR-01~15, "functional")
  → generate_testcases_for_group(FR-16~30, "functional")
  → generate_testcases_for_group(FR-31~47, "functional")
  → generate_testcases_for_group(NFR-01~12, "performance")
  "커버리지 확인해보자"
  → validate_coverage(...)
  "보안 쪽이 65%밖에 안 된다"
  → generate_testcases_for_group(보안 관련 FR, "security")
  → validate_coverage(...)  ← 재검증
  "87% 달성, 충분하다"
  → 최종 결과 반환
```

### 완료된 작업

- [x] 커스텀 도구 5개 정의: save_requirements, save_testcases, check_coverage, get_progress, save_validation
- [x] `create_deep_agent(tools=AGENT_TOOLS)` 에 도구 연결
- [x] 시스템 프롬프트에 도구 사용 전략 가이드 추가 (분할/반복/커버리지 80% 루프)
- [x] contextvars로 세션별 도구 결과 축적 (비동기 안전)
- [x] validate_fn으로 에이전트가 도구를 실제 사용했는지 검증 (미사용 시 fallback)
- [x] 공개 API 시그니처 유지 → 라우터/프론트엔드 변경 없음
- [ ] (향후) 에이전트의 중간 과정(도구 호출 로그)을 프론트엔드에 스트리밍

### 변경 대상 파일
- `backend/src/agents/testcase_agent.py` — 도구 정의 + 에이전트 재구성
- `backend/src/routers/testcase.py` — 백그라운드 태스크 흐름 수정
- 프론트엔드는 API 계약 유지하면 변경 최소화

### 이전 방식 (LangGraph create_react_agent)과의 비교

```python
# 이전 (LangGraph 직접)
from langgraph.prebuilt import create_react_agent
agent = create_react_agent(model, tools=[...])

# 현재 (DeepAgent — LangGraph 위에 미들웨어 자동 구성)
from deepagents import create_deep_agent
agent = create_deep_agent(model=model, tools=[...])
# → TodoListMiddleware, SubAgentMiddleware 등이 자동 추가됨
# → 에이전트가 write_todos로 작업 계획을 세우고, task로 서브에이전트 위임 가능
```

---

## 3. LangChain Skills 활용

**현재**: Claude Code Skills (langchain-skills 11개)는 개발 보조용으로 설치/활용 중
**참고**: 런타임 에이전트용 Skills(SKILL.md)는 현재 시스템 프롬프트로 충분

### 상태
- [x] Claude Code Skills 11개 설치 완료 (deep-agents-core, deep-agents-memory 등)
- [x] 개발 시 Claude Code가 자동으로 적절한 스킬을 로드하여 코드 품질 향상
- [ ] (선택) 런타임 DeepAgent용 커스텀 SKILL.md 작성 — 현재는 system_prompt로 대체

---

## 4. DeepAgent Memory 구현 ✅ 기본 구현 완료

**이전**: DB에 세션 데이터(requirement, fr_nfr, testcases, validation) JSONB로 단순 저장
**현재**: MemorySaver(세션 내 대화 메모리) + CompositeBackend(영속 메모리) + DB(결과 저장) 3계층

### 완료된 작업
- [x] MemorySaver: thread_id(=session_id)별 대화 히스토리 자동 관리
- [x] CompositeBackend: StateBackend(임시) + StoreBackend(영속) 경로 라우팅
- [x] `use_previous_response_id=True`: OpenAI 서버 측 대화 상태 유지 (토큰 절약)

### 향후 개선
- [ ] InMemoryStore → PostgresStore 전환 (서버 재시작 시에도 메모리 유지)
- [ ] MemorySaver → PostgresSaver 전환 (대화 히스토리 영속화)

---

## 5. 모델 Fallback 구현 ✅ 완료

- [x] MODEL_CHAIN 4단계: `openai:gpt-5-nano` → `gpt-5-mini` → `gpt-4.1` → `gpt-4o`
- [x] `_invoke_with_fallback()`: 실패 시 자동 다음 모델 시도
- [x] 향후 Azure 전환 시 `AzureChatOpenAI`로 교체만 하면 됨

---

## 6. 학습용 주석 보강 ✅ 완료

- [x] 코드 전반에 DeepAgent/Responses API 학습용 한국어 주석
- [x] teach.md에 핵심 개념 정리
- [x] azure_openai_responses.md 작성 (Responses API 장점 + Azure 지원 현황)

---

## 작업 우선순위

| 순서 | 작업 | 상태 |
|------|------|------|
| 1 | DeepAgent + Responses API 전환 | ✅ 완료 (1단계) |
| 2 | 도구 기반 에이전트 전환 (2단계) | ✅ 완료 |
| 3 | Skills 활용 | ✅ Claude Code Skills 활용 중 |
| 4 | Memory 구현 | ✅ 기본 구현 완료 |
| 5 | 모델 Fallback | ✅ 완료 |
| 6 | 주석 보강 | ✅ 완료 |

---

## 현재 잘 되어 있는 것 (건드리지 않을 것)

- FastAPI 구조 (라우터, 미들웨어, 예외처리, 로깅)
- asyncpg 직접 사용 (SQLAlchemy 미사용 — todo.md 요구사항 충족)
- **프론트엔드 UI/UX** — Tailwind + 인라인 스타일 방식 유지 (GitHub Dark 테마, ChatGPT 스타일 채팅 인터페이스, Nuxt UI 사용하지 않음)
- Pinia 상태관리 + 폴링 로직
- Docker Compose PostgreSQL 설정
- 비동기 백그라운드 태스크 처리
