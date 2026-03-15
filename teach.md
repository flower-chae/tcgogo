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
