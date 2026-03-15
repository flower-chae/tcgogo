# ============================================
# Backend Dockerfile (FastAPI + DeepAgent)
# ============================================
# 빌드: docker compose build backend
# 단독: docker build -t deepagent-backend ./backend
# ============================================

FROM python:3.11-slim AS base

# uv 설치 (pip보다 빠른 Python 패키지 매니저)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 의존성 먼저 복사 → Docker 레이어 캐싱 활용
# (코드가 바뀌어도 의존성이 같으면 재설치 안 함)
COPY pyproject.toml uv.lock ./

# 의존성 설치 (--frozen: lockfile 그대로 사용, --no-dev: 개발용 제외)
RUN uv sync --frozen --no-dev

# 소스코드 복사
COPY src/ ./src/

# 포트 노출
EXPOSE 3480

# 실행
# --host 0.0.0.0: 컨테이너 외부에서 접근 가능하도록
# --workers 1: 단일 워커 (DeepAgent 인메모리 상태 공유를 위해)
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3480"]
