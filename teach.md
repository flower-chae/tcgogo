# 알아야 할 사항 모음

## PostgreSQL (Docker)

### 실행 방법
```bash
# 프로젝트 루트(/home/aiqa/source/langchain_deepagent)에서
docker compose up -d
```

### 종료 / 재시작
```bash
docker compose down        # 컨테이너 종료 (데이터 유지)
docker compose down -v     # 컨테이너 + 데이터 모두 삭제
docker compose restart postgres
```

### 상태 확인
```bash
docker compose ps
docker compose logs postgres
```

### 접속 정보
| 항목 | 값 |
|------|-----|
| Host | localhost |
| Port | 5432 |
| DB | deepagent |
| User | deepagent |
| Password | deepagent1234 |
| DATABASE_URL | postgresql://deepagent:deepagent1234@localhost:5432/deepagent |

### 데이터 저장 위치
- Docker 볼륨(`postgres_data`)에 저장됨
- 컨테이너를 재시작해도 데이터가 사라지지 않음
- `docker compose down -v` 를 하면 데이터까지 삭제되므로 주의

### 설정 파일 위치
- `docker-compose.yml` : 프로젝트 루트
- `backend/.env` : DB 연결 정보 포함

### 2단계: 도구 기반 에이전트 전환 (2026-03-15)

1단계에서는 DeepAgent를 "프롬프트 → JSON 텍스트" 파이프라인으로만 사용했다.
2단계에서는 `@tool` 데코레이터로 커스텀 도구를 정의하고 에이전트가 자율적으로 호출한다.

#### 핵심 변경: 도구(@tool) 정의
```python
from langchain.tools import tool

@tool
def save_requirements(section_name: str, requirements_json: str) -> str:
    """Save extracted FR/NFR from a document section."""
    ctx = _current_context.get()  # contextvars로 세션별 컨텍스트
    data = json.loads(requirements_json)
    ctx["fr"].extend(data["fr"])
    return f"Saved {len(data['fr'])} FR ..."

agent = create_deep_agent(
    model=model,
    tools=[save_requirements, save_testcases, check_coverage, ...],  # 도구 전달
)
```

#### 1단계 vs 2단계 비교
| | 1단계 (프롬프트 파이프라인) | 2단계 (도구 기반 에이전트) |
|---|---|---|
| 동작 방식 | 프롬프트 → JSON 텍스트 반환 | 에이전트가 도구를 자율 호출 |
| 대규모 문서 | 한번에 처리 (품질 저하) | 섹션별 분할 처리 |
| 커버리지 보완 | 수동 재시도 | 자동 보완 루프 |
| 결과 저장 | JSON 파싱으로 추출 | 도구가 컨텍스트에 축적 |
| LangGraph 유사 | 단순 invoke | create_react_agent 패턴 |

#### contextvars 패턴 (도구 간 상태 공유)
```python
import contextvars

# 비동기 태스크별로 격리된 컨텍스트
_current_context = contextvars.ContextVar("agent_context")

# 에이전트 호출 전: 컨텍스트 설정
ctx = {"fr": [], "nfr": [], "testcases": [], "validation": None}
_current_context.set(ctx)

# 에이전트 실행 (도구들이 ctx에 결과 축적)
await agent.ainvoke({"messages": [...]})

# 에이전트 완료 후: 컨텍스트에서 결과 읽기
result = {"fr": ctx["fr"], "nfr": ctx["nfr"]}
```

#### validate_fn 패턴 (도구 사용 검증)
```python
# 에이전트가 도구를 실제로 사용했는지 검증
# → 사용 안 했으면 fallback 모델로 재시도
ctx = await _invoke_agent_with_fallback(
    prompt, session_id,
    validate_fn=lambda c: len(c["fr"]) > 0,  # FR이 하나도 없으면 실패
)
```

---

## LangChain Skills (Claude Code 스킬)

### 개념
LangChain/LangGraph/DeepAgents 관련 작업 시 Claude의 성공률을 높여주는 지식 패키지.
Claude Code 스킬 형태의 마크다운 파일로, 설치하면 Claude가 자동으로 적절한 스킬을 로드함.
(일반 29% → 95% 성공률 향상, Claude Sonnet 4.6 기준)

### 설치 방법 (npx 이용)
```bash
# 프로젝트 루트에서 실행 (node/npm 필요)
npx skills add langchain-ai/langchain-skills --skill '*' --yes

# 모든 프로젝트에서 쓰고 싶으면 --global 추가
npx skills add langchain-ai/langchain-skills --skill '*' --yes --global
```

### 설치 위치
```
프로젝트루트/.agents/skills/    ← 실제 파일
프로젝트루트/.claude/skills/    ← Claude Code용 심링크 (자동 생성)
```

### 설치된 스킬 목록 (11개)
| 스킬 | 설명 |
|------|------|
| framework-selection | LangChain/LangGraph/DeepAgents 중 어떤 걸 쓸지 선택 가이드 |
| langchain-dependencies | 의존성 관리 방법 |
| langchain-fundamentals | create_agent(), 미들웨어, 툴 패턴 |
| langchain-middleware | 미들웨어 구현 패턴 |
| langchain-rag | RAG 구현 패턴 |
| langgraph-fundamentals | LangGraph 기초 primitives |
| langgraph-persistence | durable execution, 상태 지속성 |
| langgraph-human-in-the-loop | Human-in-the-loop 패턴 |
| **deep-agents-core** | **DeepAgents 핵심 기능** ← 이 프로젝트 핵심 |
| **deep-agents-memory** | **DeepAgents 메모리 관리** |
| **deep-agents-orchestration** | **DeepAgents 오케스트레이션** |

### 적용 방법
별도 설정 불필요. 설치 후 Claude Code에서 작업 시 자동으로 활성화됨.
DeepAgents/LangChain 관련 코드를 작성하거나 질문하면 Claude가 스킬을 자동 로드.

### 업데이트 / 관리
```bash
npx skills check    # 업데이트 확인
npx skills update   # 업데이트 설치
```

### 참고
- 소스: https://github.com/langchain-ai/langchain-skills
- 블로그: https://blog.langchain.com/langchain-skills/

---

## 전체 서비스 실행 방법

### 1. PostgreSQL 시작
```bash
cd /home/aiqa/source/langchain_deepagent
docker compose up -d
```

### 2. Backend 시작 (FastAPI, 포트 3480)
```bash
cd /home/aiqa/source/langchain_deepagent/backend
uv run uvicorn src.main:app --port=3480 --reload --host 0.0.0.0
```

### 3. Frontend 시작 (Nuxt 4, 포트 3482)
```bash
cd /home/aiqa/source/langchain_deepagent/frontend
npm run dev -- --host 0.0.0.0
```

### 접속
- Frontend: http://localhost:3482
- Backend API: http://localhost:3480/api/v1
- API 문서 (Swagger): http://localhost:3480/docs

---

## DeepAgent + OpenAI Responses API 전환 (2026-03-15)

### 전환 전 (직접 OpenAI SDK 호출)
```python
from openai import AsyncOpenAI
client = AsyncOpenAI()
response = await client.chat.completions.create(
    model="gpt-5-nano",
    messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
)
text = response.choices[0].message.content
```
- 단순한 요청-응답 패턴
- 대화 히스토리 관리 불가
- 모델 변경 시 코드 수정 필요

### 전환 후 (DeepAgent + Responses API)
```python
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    model="openai:gpt-5-nano",  # "openai:" 접두사 → Responses API 자동 활성화
    system_prompt="...",
    checkpointer=MemorySaver(),
)

result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "..."}]},
    config={"configurable": {"thread_id": "session-uuid"}},
)
```

### 핵심 개념 정리

#### 1. Responses API 자동 활성화
- `deepagents/_models.py`의 `resolve_model()` 함수가 핵심
- `"openai:"` 접두사 감지 → `init_chat_model(model, use_responses_api=True)` 호출
- Chat Completions API와 Responses API 차이:
  - Completions: `client.chat.completions.create()` → `response.choices[0].message`
  - Responses: 빌트인 도구, reasoning 파라미터, 스트리밍 기본 동작

#### 2. thread_id = session_id (대화 메모리)
- `MemorySaver`가 thread_id별 메시지 히스토리를 자동 저장
- extract → generate → validate 같은 session_id 사용
- 에이전트가 이전 단계의 분석 내용을 자동으로 기억
- 서버 재시작 시 초기화됨 (프로덕션에서는 PostgresSaver 필요)

#### 3. CompositeBackend (경로별 저장소 분리)
- 기본 경로 → StateBackend (스레드 내 임시, 스레드 종료 시 삭제)
- `/memories/` → StoreBackend (InMemoryStore, 세션 간 공유)
- 웹 서버에서는 FilesystemBackend 사용 금지 (보안)

#### 4. 모델 Fallback 체인
- `openai:gpt-5-nano` → `openai:gpt-5-mini` → `openai:gpt-4.1` → `openai:gpt-4o`
- 첫 모델 실패 시 자동으로 다음 모델 시도
- Fallback 시 별도 thread_id 사용 (상태 오염 방지)

#### 5. create_deep_agent()가 자동으로 해주는 것
- TodoListMiddleware: 작업 계획 관리
- FilesystemMiddleware: 파일 읽기/쓰기 도구 (ls, read_file, write_file 등)
- SubAgentMiddleware: 서브에이전트 위임 (task 도구)
- SummarizationMiddleware: 긴 대화 자동 요약
- AnthropicPromptCachingMiddleware: Anthropic 모델 캐싱 (OpenAI에선 무시)
- PatchToolCallsMiddleware: Tool Call 보정
- recursion_limit=1000 설정

---

## Backend 구조 변경 이력

### SQLAlchemy 제거 (2026-03-14)
- todo.md 요구사항에 따라 SQLAlchemy/Alembic 제거
- asyncpg를 직접 사용하여 raw SQL로 DB 조작
- `database.py`: asyncpg 커넥션 풀 관리
- `models.py`: Pydantic 모델만 정의 (ORM 모델 없음)
- `routers/testcase.py`: 파라미터화된 SQL 쿼리 ($1, $2...) 사용
- SSE 스트리밍 엔드포인트 추가: `GET /api/v1/testcase/{session_id}/stream`

---

## Frontend 구조 (Nuxt 4)

### 기술 스택
- Nuxt 4.4.2 + Nuxt UI + Pinia
- 다크 테마 기본
- Lucide 아이콘

### 구조
```
frontend/app/
├── app.vue              # 루트 레이아웃
├── pages/
│   └── index.vue        # 메인 페이지 (SPA 스타일)
└── stores/
    └── testcase.ts      # Pinia 스토어 (API 연동)
```

### 주요 기능
- 좌측 사이드바: 세션 목록
- 4개 탭: Input → FR/NFR → Test Cases → Validation
- 비동기 처리 후 자동 폴링으로 결과 갱신
- 커버리지 스코어 시각화
