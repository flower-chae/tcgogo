# ============================================
# Frontend Dockerfile (Nuxt 4)
# ============================================
# 멀티스테이지 빌드:
#   1단계(build): npm install + nuxt build
#   2단계(runtime): 빌드 결과물만 복사하여 실행
# ============================================

# --- 1단계: 빌드 ---
FROM node:22-alpine AS build

WORKDIR /app

# 의존성 먼저 복사 → Docker 레이어 캐싱
COPY package.json package-lock.json* ./

RUN npm ci

# 소스코드 복사
COPY . .

# apiBase를 빌드 시 환경변수로 주입
# 기본값: 같은 호스트의 :3480 (docker-compose 환경)
# 브라우저에서 API를 호출하므로 localhost가 아닌 실제 접근 가능한 주소
ARG NUXT_PUBLIC_API_BASE=http://localhost:3480/api/v1
ENV NUXT_PUBLIC_API_BASE=${NUXT_PUBLIC_API_BASE}

RUN npm run build

# --- 2단계: 실행 ---
FROM node:22-alpine AS runtime

WORKDIR /app

# 빌드 결과물만 복사 (node_modules, 소스 불필요)
# Nuxt build 출력: .output/ 디렉토리
COPY --from=build /app/.output .output/

EXPOSE 3482

# Nuxt production 서버 실행
# NITRO_PORT로 포트 지정
ENV NITRO_PORT=3482
ENV NITRO_HOST=0.0.0.0

CMD ["node", ".output/server/index.mjs"]
