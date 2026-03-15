# Claude TODO - DeepAgent 프로젝트

> 다음 세션의 Claude가 이 파일을 먼저 읽고 현재 상태를 파악한다.

---

## 프로젝트 한줄 요약

LangChain DeepAgent + OpenAI Responses API로 요구사항(SRS/PRD)에서 TestCase를 생성하는 AI 웹앱.

---

## 현재 상태 (2026-03-15 기준)

### 완료된 작업 ✅

| 작업 | 핵심 내용 | 관련 파일 |
|------|----------|----------|
| DeepAgent 전환 | `AsyncOpenAI` 직접 호출 → `create_deep_agent()` 기반 | `testcase_agent.py` |
| Responses API | `use_previous_response_id=True`로 토큰 절약 | `testcase_agent.py` |
| 도구 기반 에이전트 (2단계) | 5개 커스텀 @tool 정의, 에이전트가 자율 호출 | `testcase_agent.py` |
| 모델 Fallback | gpt-5-nano → gpt-5-mini → gpt-4.1 → gpt-4o | `testcase_agent.py` |
| Memory | MemorySaver + CompositeBackend (InMemory) | `testcase_agent.py` |
| 실시간 SSE 스트리밍 | asyncio.Queue + astream_events → 도구 호출 과정 실시간 표시 | `testcase_agent.py`, `testcase.py`, `testcase.ts`, `index.vue` |
| text shimmer 효과 | 에이전트 처리 중 텍스트에 빛이 흐르는 효과 (Claude Code 스타일) | `index.vue`, `main.css` |
| Docker 배포 | backend/frontend Dockerfile + docker-compose.yml | 프로젝트 루트 |
| 학습용 주석 | 전체 코드에 한국어 주석 추가 완료 | 모든 소스 파일 |
| 문서 | backend_agent.md, frontend_study.md, azure_openai_responses.md, teach.md, how_to_frontend.md | 프로젝트 루트 |

### 아직 안 한 것 (향후 작업)

- [ ] **실제 end-to-end 테스트**: Docker로 전체 서비스 올려서 30페이지급 요구사항 테스트
- [ ] **InMemoryStore → PostgresStore**: 서버 재시작해도 에이전트 메모리 유지
- [ ] **MemorySaver → PostgresSaver**: 대화 히스토리 영속화
- [ ] **Azure 전환**: `_create_model()`에서 `AzureChatOpenAI` 사용 (회사 환경)
- [ ] **Jenkins 파이프라인**: Jenkinsfile 작성 (빌드 → 테스트 → 배포)
- [ ] **런타임 DeepAgent Skills**: SKILL.md 작성 (현재는 system_prompt로 대체 중)

---

## 아키텍처 요약

```
사용자 → Nuxt 4 프론트엔드 (포트 3482)
           ↓ POST API 호출 (202 즉시 응답)
           ↓ EventSource SSE 연결 (/stream)
         FastAPI 백엔드 (포트 3480)
           ↓ BackgroundTask
         DeepAgent (create_deep_agent + astream_events)
           ↓ 에이전트 루프 (도구 자율 호출 + 이벤트 발행)
         커스텀 도구 5개 → contextvars에 결과 축적
           ↓                ↓
         asyncio.Queue → SSE로 프론트엔드에 실시간 전송
           ↓                (text shimmer 효과로 상태 표시)
         PostgreSQL (asyncpg, 포트 5432)
```

---

## 핵심 파일 맵

```
backend/src/
├── agents/testcase_agent.py    ★ 에이전트 + 도구 + 이벤트 큐 + astream_events
├── routers/testcase.py         ★ API 엔드포인트 + SSE 스트리밍 + 백그라운드 태스크
├── db/database.py                 asyncpg 커넥션 풀
├── db/models.py                   Pydantic 요청/응답 모델
├── main.py                        FastAPI 앱 진입점
├── core/                          CORS, 예외처리, 로깅
└── middleware/                    요청/응답 로깅

frontend/app/
├── pages/index.vue             ★ 메인 페이지 UI (text shimmer, typing dots)
├── stores/testcase.ts          ★ Pinia 스토어 (EventSource SSE + 폴링 fallback)
├── app.vue                        루트 레이아웃
└── assets/css/main.css            글로벌 CSS + 애니메이션 (shimmer-glow, typing-dot 등)

프로젝트 루트:
├── docker-compose.yml             3개 서비스 (postgres, backend, frontend)
├── .env.example                   환경변수 템플릿
├── todo.md                        원본 요구사항 (사용자 작성)
├── claude_todo.md                 ★ 이 파일 (Claude 작업 추적)
├── backend_agent.md               백엔드 에이전트 아키텍처 가이드
├── frontend_study.md              프론트엔드 학습 가이드
├── how_to_frontend.md             프론트엔드 디자인 지시 가이드 + UI 효과 용어 사전
├── azure_openai_responses.md      Responses API + Azure 정리
└── teach.md                       기술 결정 이력 + 학습 내용
```

---

## 사용자 선호 & 피드백 기록

| 항목 | 내용 |
|------|------|
| UI 방식 | Tailwind + 인라인 스타일 (Nuxt UI 사용 안 함 — 확정) |
| UI 효과 | text shimmer (회색 톤 빛 흐름, 3.5초, 왼→오), typing dots (파란색) |
| 로딩 UX | ChatGPT thinking 스타일 — 하나의 메시지가 교체됨 (단계 누적 X) |
| DB | asyncpg 직접 사용 (SQLAlchemy 금지) |
| 주석 | 한국어로 충분히 (학습 목적) |
| 모델 | 회사에서 Azure OpenAI 사용 예정 (gpt-5.2, 5.3-codex, 5.4) |
| 배포 | Jenkins + Docker Compose |
| CSS 효과 | text shimmer 등 특수 효과는 main.css에 클래스로 정의 (.text-shimmer) |

---

## 다음 세션에서 할 일 (사용자가 요청하면)

### 우선순위 1: 실제 동작 테스트
```
docker compose up -d --build
→ 요구사항 입력 → FR/NFR 추출 → TC 생성 → 검증
→ 에이전트가 도구를 제대로 호출하는지 확인
→ SSE 스트리밍이 정상 동작하는지 확인
→ text shimmer + 메시지 교체가 잘 되는지 확인
```

### 우선순위 2: Azure 전환
```
_create_model()을 AzureChatOpenAI로 변경
MODEL_CHAIN을 Azure 배포 이름으로 변경
.env에 Azure 인증 정보 추가
```

### 우선순위 3: Jenkins 파이프라인
```
Jenkinsfile 작성
빌드 → 테스트 → 이미지 Push → 배포
```
