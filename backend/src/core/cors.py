from fastapi.middleware.cors import CORSMiddleware


# =============================================================================
# CORS (Cross-Origin Resource Sharing) 미들웨어 설정
# =============================================================================
# CORS란?
#   - 브라우저가 다른 도메인(Origin)의 리소스에 접근할 때 적용되는 보안 정책
#   - 예: http://localhost:3000 (프론트엔드) → http://localhost:8081 (백엔드) 요청 시 필요
#
# 동작 방식:
#   1. 브라우저가 OPTIONS 요청(Preflight)을 먼저 보내 서버가 허용하는지 확인
#   2. 서버가 허용하면 실제 요청(GET, POST 등)을 보냄
# =============================================================================

CORS_CONFIG = {
    "allow_origins": ["*"],
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "max_age": -1,
}


def setup_cors(app):
    app.add_middleware(CORSMiddleware, **CORS_CONFIG)


    # allow_origins: 허용할 출처(Origin) 목록
    #   - ["*"]: 모든 도메인 허용 (개발용, 프로덕션에서는 특정 도메인 지정 권장)
    #   - 예: ["http://localhost:3000", "https://example.com"]
    # allow_origins=["*"],
    
    # allow_credentials: 쿠키, Authorization 헤더 등 인증 정보 포함 허용 여부
    #   - True: 쿠키/인증 정보 허용 (주의: allow_origins=["*"]와 함께 사용 시 보안 위험)
    #   - False: 인증 정보 차단
    # allow_credentials=True,
    
    # allow_methods: 허용할 HTTP 메서드
    #   - ["*"]: 모든 메서드 허용 (GET, POST, PUT, DELETE, PATCH, OPTIONS 등)
    #   - 예: ["GET", "POST"]로 특정 메서드만 허용 가능
    # allow_methods=["*"],
    
    # allow_headers: 허용할 요청 헤더
    #   - ["*"]: 모든 헤더 허용
    #   - 예: ["Content-Type", "Authorization"]로 특정 헤더만 허용 가능
    # allow_headers=["*"],
    
    # max_age: Preflight 요청 결과 캐시 시간 (초)
    #   - -1: 캐시 안 함 (매 요청마다 Preflight 수행, 개발 시 유용)
    #   - 3600: 1시간 캐시 (프로덕션에서 성능 향상)
    # max_age=-1,
