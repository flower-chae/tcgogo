# Backend Agent 아키텍처 가이드

> 이 프로젝트의 백엔드 에이전트 구조와 코드 따라가는 방법을 정리한 문서

---

## 1. 전체 흐름 한눈에 보기

```
사용자 (프론트엔드)
  │
  ▼
FastAPI 라우터 (testcase.py)
  │ POST /api/v1/testcase/extract-fr-nfr
  │ POST /api/v1/testcase/{id}/generate
  │ POST /api/v1/testcase/{id}/validate
  │
  ▼
BackgroundTask (비동기 백그라운드)
  │ _run_extract_fr_nfr()
  │ _run_generation()
  │ _run_validation()
  │
  ▼
에이전트 공개 API (testcase_agent.py)
  │ extract_fr_nfr(requirement, session_id)
  │ generate_testcases(requirement, fr_nfr, session_id)
  │ validate_testcases(requirement, fr_nfr, testcases, session_id)
  │
  ▼
_invoke_agent_with_fallback()
  │ 모델 Fallback 체인: gpt-5-nano → gpt-5-mini → gpt-4.1 → gpt-4o
  │ contextvars로 세션 컨텍스트 설정
  │
  ▼
DeepAgent (create_deep_agent)
  │ LangGraph CompiledStateGraph
  │ 에이전트 루프: 모델 호출 → 도구 선택 → 도구 실행 → 결과 확인 → 반복
  │
  ▼
커스텀 도구 (@tool)                     세션 컨텍스트 (contextvars)
  ├─ save_requirements() ──────────────→ ctx["fr"], ctx["nfr"]에 축적
  ├─ save_testcases() ─────────────────→ ctx["testcases"]에 축적
  ├─ check_coverage() ←────────────────── ctx에서 읽어서 계산
  ├─ get_progress() ←──────────────────── ctx에서 읽어서 반환
  └─ save_validation() ────────────────→ ctx["validation"]에 저장
  │
  ▼
결과 반환 (ctx dict)
  │
  ▼
DB 저장 (asyncpg → PostgreSQL)
  │ testcase_sessions 테이블
  │ fr_nfr, testcases, validation 컬럼 (JSONB)
  │
  ▼
프론트엔드 폴링 → 결과 표시
```

---

## 2. 파일 구조

```
backend/src/
├── main.py                      # FastAPI 앱 진입점 (lifespan, 미들웨어, 라우터 등록)
├── agents/
│   └── testcase_agent.py        # ★ 핵심: DeepAgent + 커스텀 도구 정의
├── routers/
│   ├── testcase.py              # API 엔드포인트 + 백그라운드 태스크
│   └── sample.py                # 헬스체크
├── db/
│   ├── database.py              # asyncpg 커넥션 풀, 테이블 생성
│   └── models.py                # Pydantic 요청/응답 모델
├── core/
│   ├── cors.py                  # CORS 설정
│   ├── exceptions.py            # 전역 예외 핸들러
│   └── logging.py               # Loguru 설정
└── middleware/
    └── logging_middleware.py     # 요청/응답 로깅
```

---

## 3. 코드 따라가기: 요구사항 입력부터 TC 생성까지

### Step 1: 사용자가 요구사항을 입력

프론트엔드에서 `POST /api/v1/testcase/extract-fr-nfr` 호출

### Step 2: 라우터가 백그라운드 태스크 시작

```
파일: routers/testcase.py (line 178)
함수: extract_fr_nfr_endpoint()
```

```python
@router.post("/extract-fr-nfr", status_code=202)
async def extract_fr_nfr_endpoint(body, background_tasks):
    session_id = uuid.uuid4()
    # DB에 세션 생성 (status="pending")
    await conn.execute("INSERT INTO testcase_sessions ...")
    # 백그라운드 태스크 등록 → 즉시 202 응답 반환
    background_tasks.add_task(_run_extract_fr_nfr, session_id, body.requirement)
    return {"id": session_id, "status": "extracting"}
```

**핵심**: 202를 즉시 반환하고, 실제 작업은 백그라운드에서 진행.
프론트엔드는 폴링(GET /{session_id})으로 상태 확인.

### Step 3: 백그라운드 태스크가 에이전트 호출

```
파일: routers/testcase.py (line 64)
함수: _run_extract_fr_nfr()
```

```python
async def _run_extract_fr_nfr(session_id, requirement):
    await conn.execute("UPDATE ... SET status = 'extracting'")
    try:
        # ★ 에이전트 호출 (session_id를 thread_id로 전달)
        fr_nfr = await extract_fr_nfr(requirement, str(session_id))
        await conn.execute("UPDATE ... SET fr_nfr = $1, status = 'extracted'")
    except:
        await conn.execute("UPDATE ... SET status = 'failed'")
```

**핵심**: DB 상태를 extracting → extracted (또는 failed)로 업데이트.

### Step 4: 에이전트가 도구를 자율적으로 호출

```
파일: agents/testcase_agent.py (line 405)
함수: extract_fr_nfr()
```

```python
async def extract_fr_nfr(requirement, session_id):
    prompt = "Analyze the following requirement document..."

    ctx = await _invoke_agent_with_fallback(
        prompt, session_id,
        validate_fn=lambda c: len(c["fr"]) > 0 or len(c["nfr"]) > 0,
    )

    return {"fr": ctx["fr"], "nfr": ctx["nfr"]}
```

**핵심**: 텍스트 응답을 파싱하지 않음. 도구가 컨텍스트에 축적한 결과를 읽음.

### Step 5: Fallback 체인 + 컨텍스트 관리

```
파일: agents/testcase_agent.py (line 329)
함수: _invoke_agent_with_fallback()
```

```python
async def _invoke_agent_with_fallback(prompt, session_id, initial_ctx, validate_fn):
    for i, model_name in enumerate(MODEL_CHAIN):
        ctx = _fresh_context(initial_ctx)    # 깨끗한 컨텍스트
        _current_context.set(ctx)            # contextvars에 설정

        agent = _get_agent(model_name)
        await agent.ainvoke({"messages": [...]}, config=config)

        if validate_fn and not validate_fn(ctx):
            raise ValueError("Agent did not use tools")

        return ctx  # 도구로 축적된 결과
```

**핵심**:
1. 각 시도마다 깨끗한 컨텍스트 (실패 시 오염 방지)
2. `contextvars`로 비동기 안전하게 컨텍스트 공유
3. `validate_fn`으로 "도구 미사용" 감지 → fallback 트리거

### Step 6: 에이전트 내부에서 일어나는 일

```
DeepAgent 에이전트 루프 (LangGraph):

┌────────────────────────────────────────────────┐
│ 1. 모델이 프롬프트를 받고 사고                    │
│    "30페이지 문서니까 섹션별로 나눠야겠다"          │
│                                                 │
│ 2. 모델이 도구 호출을 결정                        │
│    → save_requirements("1장: 인증", "{fr: [...]}")│
│                                                 │
│ 3. 도구 실행 (우리 코드)                          │
│    ctx["fr"].extend(new_fr)                     │
│    → "Saved 5 FR and 2 NFR. Total: 5 FR, 2 NFR"│
│                                                 │
│ 4. 도구 결과를 모델에 전달                         │
│                                                 │
│ 5. 모델이 다시 사고                               │
│    "2장도 분석해야지"                             │
│    → save_requirements("2장: 결제", ...)          │
│    (2→3→4 반복)                                  │
│                                                 │
│ 6. 모델이 "더 이상 호출할 도구 없음" 판단           │
│    → 최종 텍스트 응답 반환 (이건 무시)              │
└────────────────────────────────────────────────┘
```

---

## 4. 커스텀 도구 5개 상세

### 4.1 save_requirements

```
역할: FR/NFR을 세션 컨텍스트에 축적
호출 시점: 에이전트가 요구사항 문서를 분석할 때
호출 횟수: 짧은 문서 1회, 긴 문서 섹션별 여러 회
```

```python
@tool
def save_requirements(section_name: str, requirements_json: str) -> str:
    # requirements_json 예시:
    # {"fr": [{"id": "FR-01", "title": "로그인", "description": "...", "priority": "high"}],
    #  "nfr": [{"id": "NFR-01", ...}]}

    ctx = _current_context.get()      # contextvars에서 현재 세션 컨텍스트
    data = json.loads(requirements_json)
    ctx["fr"].extend(data["fr"])       # 축적 (덮어쓰기 아님)
    ctx["nfr"].extend(data["nfr"])
    return "Saved 3 FR and 1 NFR..."   # 에이전트에게 결과 알림
```

### 4.2 save_testcases

```
역할: 테스트 케이스를 세션 컨텍스트에 축적
호출 시점: 에이전트가 TC를 생성할 때
호출 횟수: FR/NFR 그룹별 여러 회 (한번에 전부 X)
```

- 그룹별로 나눠서 호출 → TC 품질 유지
- ID가 없으면 자동 생성 (`TC-001`, `TC-002`, ...)
- `fr_nfr_ref`가 문자열이면 배열로 정규화

### 4.3 check_coverage

```
역할: 현재 축적된 TC의 FR/NFR 커버리지 % 계산
호출 시점: TC 생성 후 검증 시
반환값: {"coverage_percent": 75.0, "uncovered_ids": ["FR-05", "NFR-03"], ...}
```

- 에이전트가 이 결과를 보고 "80% 미만이면 추가 TC 생성" 판단
- 커버리지 = (TC가 참조하는 FR/NFR 수) / (전체 FR/NFR 수)

### 4.4 get_progress

```
역할: 현재까지 축적된 FR/NFR/TC 개수 확인
호출 시점: 에이전트가 중간 진행 상황을 확인할 때
```

### 4.5 save_validation

```
역할: 최종 검증 결과 저장
호출 시점: validate_testcases() 호출 시
저장 형태: {"coverage_score": 0.85, "missing_areas": [...], "feedback": "...", "is_sufficient": true}
```

---

## 5. 상태 관리 계층

```
┌─────────────────────────────────────────────────────┐
│ 1. contextvars (_current_context)                    │
│    용도: 도구 간 결과 공유 (에이전트 한 번 실행 중)      │
│    수명: 에이전트 invoke 1회                           │
│    저장: fr[], nfr[], testcases[], validation         │
│    특징: 비동기 태스크별 격리 (동시 세션 충돌 없음)       │
├─────────────────────────────────────────────────────┤
│ 2. MemorySaver (_checkpointer)                       │
│    용도: thread_id별 대화 히스토리                      │
│    수명: 서버 실행 중 (재시작 시 초기화)                 │
│    특징: extract→generate→validate 단계 간 컨텍스트 유지│
├─────────────────────────────────────────────────────┤
│ 3. CompositeBackend (StateBackend + StoreBackend)    │
│    용도: 에이전트의 파일 기반 메모리                     │
│    기본 경로 → StateBackend (스레드 내 임시)            │
│    /memories/ → StoreBackend (세션 간 공유)            │
├─────────────────────────────────────────────────────┤
│ 4. PostgreSQL (asyncpg)                              │
│    용도: 최종 결과 영속 저장                            │
│    테이블: testcase_sessions                          │
│    컬럼: fr_nfr(JSONB), testcases(JSONB), validation  │
│    특징: 서버 재시작/브라우저 새로고침에도 유지            │
└─────────────────────────────────────────────────────┘
```

---

## 6. 에이전트의 자율 판단 예시

### 짧은 요구사항 (1페이지)

```
에이전트:
  → save_requirements("Full Document", {fr: [FR-01~03], nfr: [NFR-01]})
  → save_testcases("All Requirements", [TC-01~08])
  → check_coverage() → 100%
  → 완료 (총 도구 호출: 3회)
```

### 긴 요구사항 (30페이지 SRS)

```
에이전트:
  → save_requirements("1장: 사용자 인증", {fr: [FR-01~08], nfr: [NFR-01~03]})
  → save_requirements("2장: 결제 처리", {fr: [FR-09~20], nfr: [NFR-04~06]})
  → save_requirements("3장: 관리자", {fr: [FR-21~30], nfr: [NFR-07~08]})
  → get_progress() → fr: 30, nfr: 8
  → save_testcases("인증 기능", [TC-001~015])
  → save_testcases("결제 기능", [TC-016~035])
  → save_testcases("관리자 기능", [TC-036~050])
  → check_coverage() → 72%, uncovered: [NFR-02, NFR-05, FR-15, FR-28]
  → save_testcases("보안 보완", [TC-051~058])
  → save_testcases("성능 보완", [TC-059~065])
  → check_coverage() → 89%
  → 완료 (총 도구 호출: 10회)
```

---

## 7. Fallback + validate_fn 동작

```
시나리오: gpt-5-nano가 도구를 사용하지 않고 텍스트만 반환한 경우

1. gpt-5-nano로 시도
   → 에이전트 실행 완료
   → validate_fn(ctx) 호출: len(ctx["fr"]) == 0 → False
   → ValueError 발생: "Agent did not produce expected results via tools"
   → 로그: "gpt-5-nano 실패"

2. gpt-5-mini로 재시도 (깨끗한 컨텍스트)
   → 에이전트가 save_requirements 도구 호출
   → validate_fn(ctx) 호출: len(ctx["fr"]) == 5 → True
   → 성공! ctx 반환
   → 로그: "Fallback 성공: gpt-5-mini (이전 1개 모델 실패)"
```

---

## 8. DB 테이블 구조

```sql
CREATE TABLE testcase_sessions (
    id              UUID PRIMARY KEY,
    requirement     TEXT NOT NULL,           -- 원본 요구사항 텍스트
    requirement_type VARCHAR(20),            -- 'requirement' | 'SRS' | 'PRD'
    status          VARCHAR(20),             -- pending → extracting → extracted
                                             --   → processing → completed
                                             --   → failed
    fr_nfr          JSONB,                   -- {"fr": [...], "nfr": [...]}
    testcases       JSONB,                   -- [{"id": "TC-01", ...}, ...]
    validation      JSONB,                   -- {"coverage_score": 0.85, ...}
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ
);
```

### 상태 전이

```
POST /extract-fr-nfr:
  pending → extracting → extracted (또는 failed)

POST /{id}/generate:
  extracted → processing → completed (또는 failed)

POST /{id}/validate:
  completed → (validation 컬럼 업데이트)

POST /generate (full pipeline):
  pending → extracting → extracted → processing → completed
```

---

## 9. 실시간 스트리밍 (SSE + asyncio.Queue)

에이전트가 도구를 호출할 때마다 프론트엔드에 실시간으로 진행 상황을 보여준다.

### 동작 흐름

```
1. 프론트엔드 → POST /extract-fr-nfr → 202 응답
2. 프론트엔드 → new EventSource('/stream') → SSE 연결 열기
3. BackgroundTask에서 에이전트 실행:
   agent.astream_events() 루프:
     → on_tool_start: "save_requirements"
       → asyncio.Queue.put({type: "tool_start", message: "FR/NFR 추출 중..."})
     → on_tool_end: "save_requirements"
       → asyncio.Queue.put({type: "tool_end", message: "FR 8개 완료"})
     → on_tool_start: "save_testcases" ...

4. SSE Endpoint에서 Queue.get()으로 이벤트 수신:
   → yield "event: step\ndata: {...}\n\n"   ← 프론트로 전송

5. 프론트엔드 EventSource가 step 이벤트 수신:
   → 로딩 메시지에 단계 추가:
     ✓ FR/NFR 추출 중... → Saved 8 FR and 3 NFR
     ✓ 테스트 케이스 생성 중... → Saved 15 test cases
     ● 커버리지 확인 중...  ← 현재 진행 중

6. done 이벤트 수신 → DB에서 최종 결과 fetch → 결과 카드 표시
```

### 핵심 구성 요소

```
testcase_agent.py:
  _event_queues: dict[str, asyncio.Queue]  ← 세션별 큐
  get_event_queue(session_id) → Queue      ← 큐 가져오기/생성
  _publish_event(session_id, event)        ← 큐에 이벤트 발행
  TOOL_DISPLAY: dict                       ← 도구 이름 → 한국어 메시지 매핑

  _invoke_agent_with_fallback():
    이전: await agent.ainvoke(...)          ← 결과만 받음
    현재: async for event in agent.astream_events(...):  ← 중간 이벤트도 받음
          → on_tool_start → _publish_event()
          → on_tool_end → _publish_event()

routers/testcase.py:
  _run_extract_fr_nfr(): 완료 시 → _publish_event({type: "done"})
  stream_session_status(): Queue.get() → SSE yield

stores/testcase.ts:
  startPolling(): new EventSource() → step/done/error 이벤트 수신
  _addAgentStep(): 로딩 메시지에 진행 단계 추가
  _fallbackToPolling(): SSE 실패 시 기존 2초 폴링으로 전환

pages/index.vue:
  msg.steps 배열을 순회하며 ✓/● 아이콘과 함께 단계 표시
```

### astream_events vs ainvoke 비교

```python
# ainvoke: 결과만 받음 (2단계)
result = await agent.ainvoke({"messages": [...]})
# → 에이전트가 끝날 때까지 아무 정보 없음

# astream_events: 중간 과정도 받음 (3단계)
async for event in agent.astream_events({"messages": [...]}, version="v2"):
    if event["event"] == "on_tool_start":
        print(f"도구 시작: {event['name']}")  # "save_requirements"
    elif event["event"] == "on_tool_end":
        print(f"도구 완료: {event['data']['output']}")  # "Saved 8 FR..."
# → 에이전트가 실행되는 동안 각 단계를 실시간으로 관찰
```

### SSE Fallback 전략

```
1차: EventSource (SSE) 시도
  ├─ 성공 → 실시간 단계 표시
  └─ 실패 (네트워크 문제, SSR 등)
       → _fallbackToPolling()
       → 2초마다 DB 폴링 (기존 방식)
       → 단계 표시 없이 최종 결과만 표시
```

---

## 10. 코드 수정 시 참고

### 도구를 추가하고 싶을 때

```python
# 1. testcase_agent.py에 @tool 함수 정의
@tool
def my_new_tool(arg: str) -> str:
    """Tool description for the agent."""
    ctx = _current_context.get()
    # ... 로직
    return "result"

# 2. AGENT_TOOLS 리스트에 추가
AGENT_TOOLS = [..., my_new_tool]

# 3. SYSTEM_PROMPT에 도구 설명 추가
# 4. 서버 재시작 (에이전트 캐시 초기화)
```

### 모델을 변경하고 싶을 때

```python
# MODEL_CHAIN 순서 변경 또는 모델 추가/제거
MODEL_CHAIN = [
    "openai:gpt-5-nano",    # 1순위
    "openai:gpt-5-mini",    # 2순위
    ...
]

# Azure 전환 시: _create_model()만 수정
def _create_model(model_name: str):
    from langchain_openai import AzureChatOpenAI
    return AzureChatOpenAI(
        azure_deployment="your-deployment",
        use_responses_api=True,
        use_previous_response_id=True,
    )
```

### API 엔드포인트를 추가하고 싶을 때

```
1. db/models.py에 Pydantic 모델 추가
2. routers/testcase.py에 엔드포인트 추가
3. 필요 시 testcase_agent.py에 공개 함수 추가
4. 프론트엔드 stores/testcase.ts에 API 호출 추가
```
