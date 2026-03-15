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
| Docker 배포 | backend/frontend Dockerfile + docker-compose.yml | 프로젝트 루트 |
| 학습용 주석 | 전체 코드에 한국어 주석 추가 완료 | 모든 소스 파일 |
| 문서 | backend_agent.md, frontend_study.md, azure_openai_responses.md, teach.md | 프로젝트 루트 |

### 아직 안 한 것 (향후 작업)

- [ ] **실제 동작 테스트**: Docker로 전체 서비스 올려서 end-to-end 테스트 (에이전트가 도구를 제대로 호출하는지)
- [ ] **에이전트 중간 과정 스트리밍**: 도구 호출 로그를 프론트엔드에 실시간 표시
- [ ] **InMemoryStore → PostgresStore**: 서버 재시작해도 에이전트 메모리 유지
- [ ] **MemorySaver → PostgresSaver**: 대화 히스토리 영속화
- [ ] **Azure 전환**: `_create_model()`에서 `AzureChatOpenAI` 사용 (회사 환경)
- [ ] **Jenkins 파이프라인**: Jenkinsfile 작성 (빌드 → 테스트 → 배포)
- [ ] **런타임 DeepAgent Skills**: SKILL.md 작성 (현재는 system_prompt로 대체 중)

---

## 아키텍처 요약

```
사용자 → Nuxt 4 프론트엔드 (포트 3482)
           ↓ API 호출
         FastAPI 백엔드 (포트 3480)
           ↓ BackgroundTask
         DeepAgent (create_deep_agent)
           ↓ 에이전트 루프 (도구 자율 호출)
         커스텀 도구 5개
           ├─ save_requirements  → contextvars에 FR/NFR 축적
           ├─ save_testcases     → contextvars에 TC 축적
           ├─ check_coverage     → 커버리지 % 계산
           ├─ get_progress       → 진행 현황
           └─ save_validation    → 검증 결과 저장
           ↓ 결과
         PostgreSQL (asyncpg, 포트 5432)
```

---

## 핵심 파일 맵

```
backend/src/
├── agents/testcase_agent.py    ★ 에이전트 + 도구 정의 (가장 중요)
├── routers/testcase.py         ★ API 엔드포인트 + 백그라운드 태스크
├── db/database.py                 asyncpg 커넥션 풀
├── db/models.py                   Pydantic 요청/응답 모델
├── main.py                        FastAPI 앱 진입점
├── core/cors.py                   CORS 설정
├── core/exceptions.py             예외 핸들러
├── core/logging.py                Loguru 설정
└── middleware/logging_middleware.py  요청/응답 로깅

frontend/app/
├── pages/index.vue             ★ 메인 페이지 UI (765줄)
├── stores/testcase.ts          ★ Pinia 스토어 (API + 상태 관리)
├── app.vue                        루트 레이아웃
└── assets/css/main.css            글로벌 CSS + 애니메이션

프로젝트 루트:
├── docker-compose.yml             3개 서비스 (postgres, backend, frontend)
├── .env.example                   환경변수 템플릿
├── todo.md                        원본 요구사항 (사용자 작성)
├── claude_todo.md                 ★ 이 파일 (Claude 작업 추적)
├── backend_agent.md               백엔드 에이전트 아키텍처 가이드
├── frontend_study.md              프론트엔드 학습 가이드
├── azure_openai_responses.md      Responses API + Azure 정리
└── teach.md                       기술 결정 이력 + 학습 내용
```

---

## 사용자 선호 & 피드백 기록

| 항목 | 내용 |
|------|------|
| UI 방식 | Tailwind + 인라인 스타일 (Nuxt UI 사용 안 함 — 확정) |
| DB | asyncpg 직접 사용 (SQLAlchemy 금지 — todo.md 요구사항) |
| 주석 | 학습 목적이므로 한국어 주석 충분히 (코드 공부용) |
| 모델 | 회사에서 Azure OpenAI 사용 예정 (gpt-5.2, 5.3-codex, 5.4) |
| 배포 | Jenkins + Docker Compose |
| 프론트 지식 | 초보 (Vue/Nuxt 처음, frontend_study.md 참고) |

---

## 다음 세션에서 할 일 (사용자가 요청하면)

### 우선순위 1: 실제 동작 테스트
```
docker compose up -d --build
→ 요구사항 입력 → FR/NFR 추출 → TC 생성 → 검증
→ 에이전트가 도구를 제대로 호출하는지 확인
→ 문제 있으면 디버깅
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

### 우선순위 4: 에이전트 스트리밍
```
에이전트의 도구 호출 과정을 프론트엔드에 실시간 표시
"save_requirements 호출 중..." → "FR 15개 추출" → "save_testcases 호출 중..."
```
