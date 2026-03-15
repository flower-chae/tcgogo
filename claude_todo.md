# Claude TODO - DeepAgent 프로젝트 실제 작업 목록

> todo.md 요구사항 vs 현재 구현 상태를 비교하여 정리한 실제 해야 할 작업들

---

## 1. DeepAgent + OpenAI Responses API 전환 (최우선)

**현재**: `openai` SDK 직접 호출 (`AsyncOpenAI()` → `client.chat.completions.create()`)
**목표**: `create_deep_agent()` + OpenAI Responses API 조합으로 전환

### DeepAgent + Responses API 시너지 분석

DeepAgent는 `openai:` 접두사를 붙이면 **자동으로 Responses API를 활성화**한다:
```python
# deepagents/_models.py 내부 동작
if model.startswith("openai:"):
    return init_chat_model(model, use_responses_api=True)
```

#### 조합 시 시너지
| 기능 | DeepAgent 제공 | Responses API 제공 | 시너지 |
|------|---------------|-------------------|--------|
| **Tool Calling** | 커스텀 도구 정의 + 실행 루프 | 빌트인 도구 (web_search, code_interpreter) | 커스텀 도구 + OpenAI 빌트인 도구 동시 사용 가능 |
| **추론** | 멀티스텝 에이전트 루프 (recursion_limit=1000) | reasoning 파라미터 (effort: low/medium/high) | 에이전트 루프 각 단계에서 추론 깊이 조절 가능 |
| **메모리** | StoreBackend/CompositeBackend (DB 연동) | 상태 유지 대화 (response_id 체이닝) | 장기 메모리(DB) + 단기 컨텍스트(API) 이중 구조 |
| **파일** | FilesystemMiddleware (로컬 파일 접근) | file_search (OpenAI 벡터스토어 검색) | 로컬 파일 + 클라우드 문서 동시 검색 |
| **스트리밍** | LangChain 스트리밍 지원 | 기본 스트리밍 | 현재 폴링 방식 → 실시간 스트리밍 전환 가능 |
| **서브에이전트** | SubAgentMiddleware, TodoList | 없음 | DeepAgent가 복잡한 작업 분해 담당 |

#### 구체적 활용 시나리오
1. **web_search**: 요구사항에 언급된 기술 표준/규격을 웹에서 검색하여 더 정확한 TestCase 생성
2. **code_interpreter**: 생성된 TestCase의 커버리지 통계를 코드로 계산/시각화
3. **reasoning effort**: FR/NFR 추출은 `high`, 단순 포맷팅은 `low`로 비용 최적화
4. **response_id 체이닝**: 같은 세션 내 대화를 API 레벨에서도 연결 → 컨텍스트 유지

#### 가능 여부: 완전히 가능
- deepagents 0.4.11 + langchain-openai 1.1.11 모두 Responses API 지원 확인됨
- `create_deep_agent(model="openai:gpt-5-nano")` 한 줄로 활성화

### 작업 내용
- [ ] `testcase_agent.py`의 `AsyncOpenAI()` 직접 호출을 `create_deep_agent(model="openai:gpt-5-nano")` 기반으로 교체
- [ ] FR/NFR 추출, TestCase 생성, 검증 각각을 DeepAgent의 Tool로 정의
- [ ] Responses API 빌트인 도구(web_search 등) 활용 여부 결정 및 연결
- [ ] reasoning effort 파라미터 설정 (작업 난이도별 차등 적용)
- [ ] 현재 폴링 기반 → SSE/스트리밍 기반으로 전환 검토

### 관련 파일
- `backend/src/agents/testcase_agent.py` (212줄) — 핵심 변경 대상

---

## 2. LangChain Skills 활용

**현재**: `deepagents` 패키지 설치만 되어 있고, Skills 참조 없음
**목표**: 공식 Skills를 실제 에이전트에 연결

### 작업 내용
- [ ] 프로젝트에 적합한 공식 Skills 선별 (teach.md에 11개 Skills 설치 기록 있음)
- [ ] 선별한 Skills를 DeepAgent에 SKILL.md 포맷으로 연결
- [ ] Skills 기반으로 에이전트 동작이 실제로 개선되는지 확인

### 참고
- teach.md에 설치된 Skills 목록 있음

---

## 3. DeepAgent Memory 구현

**현재**: DB에 세션 데이터(requirement, fr_nfr, testcases, validation) JSONB로 단순 저장
**목표**: DeepAgent Memory + PostgreSQL 연동

### 작업 내용
- [ ] DeepAgent의 `StoreBackend` 또는 `CompositeBackend`를 PostgreSQL과 연동
- [ ] Responses API의 `use_previous_response_id`로 단기 컨텍스트 유지
- [ ] 이전 세션의 컨텍스트를 에이전트가 참조할 수 있도록 구성 (장기 메모리)
- [ ] 기존 `testcase_sessions` 테이블과의 관계 설계

### 관련 파일
- `backend/src/db/database.py` (62줄)

---

## 4. 모델 Fallback 구현

**현재**: `gpt-5-nano` 하드코딩 (`MODEL = "gpt-5-nano"`)
**목표**: Tool Calling 실패 시 상위 모델로 자동 전환

### 작업 내용
- [ ] 모델 우선순위 리스트 정의: `openai:gpt-5-nano` → `openai:gpt-5-mini` → `openai:gpt-4.1` → `openai:gpt-4o`
- [ ] Tool Calling 실패 감지 로직 추가
- [ ] 실패 시 다음 모델로 재시도하는 fallback 체인 구현
- [ ] 어떤 모델이 사용되었는지 응답에 포함

### 관련 파일
- `backend/src/agents/testcase_agent.py` — `MODEL = "gpt-5-nano"` 부분

---

## 5. 학습용 주석 보강

**현재**: 코드에 일부 한국어 주석 있으나 학습 목적의 상세 설명 부족
**목표**: DeepAgent/LangChain/Responses API 학습 목적에 맞는 충분한 주석

### 작업 내용
- [ ] DeepAgent 전환 후, 각 컴포넌트가 DeepAgent 아키텍처에서 어떤 역할인지 주석
- [ ] Responses API 사용 부분에 Chat Completions API와의 차이점 주석
- [ ] Tool 정의, Skills 연결, Memory 설정 부분에 "왜 이렇게 하는지" 주석
- [ ] teach.md에 DeepAgent + Responses API 전환 과정에서 배운 내용 추가

---

## 작업 우선순위

| 순서 | 작업 | 이유 |
|------|------|------|
| 1 | DeepAgent + Responses API 전환 | todo.md 핵심 목표, 다른 작업의 전제 조건 |
| 2 | Skills 활용 | DeepAgent 전환 후 바로 연결 가능 |
| 3 | Memory 구현 | DeepAgent 전환 후 진행 |
| 4 | 모델 Fallback | DeepAgent Tool Calling 도입 후 의미 있음 |
| 5 | 주석 보강 | 전환 완료 후 정리하며 작성 |

---

## 현재 잘 되어 있는 것 (건드리지 않을 것)

- FastAPI 구조 (라우터, 미들웨어, 예외처리, 로깅)
- asyncpg 직접 사용 (SQLAlchemy 미사용 — todo.md 요구사항 충족)
- **프론트엔드 UI/UX** — Tailwind + 인라인 스타일 방식 유지 (GitHub Dark 테마, ChatGPT 스타일 채팅 인터페이스, Nuxt UI 사용하지 않음)
- Pinia 상태관리 + 폴링 로직
- Docker Compose PostgreSQL 설정
- 비동기 백그라운드 태스크 처리
