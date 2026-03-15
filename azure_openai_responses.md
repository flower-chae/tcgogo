# Azure OpenAI Responses API 정리

> OpenAI Responses API의 진짜 장점과 Azure에서의 지원 현황을 정리한 문서

---

## 1. Responses API란? (Chat Completions API와의 차이)

Chat Completions API의 **후속 API**로, OpenAI가 모든 신규 프로젝트에 권장하는 API이다.
Assistants API는 2026년 8월 폐기 예정이며, Responses API로 통합된다.

### 핵심 차이점

| | Chat Completions API | Responses API |
|---|---|---|
| **응답 구조** | `response.choices[0].message` | `response.output` (Item 배열) |
| **빌트인 도구** | 없음 (직접 구현해야 함) | web_search, file_search, code_interpreter 등 내장 |
| **상태 관리** | 매번 전체 메시지 배열 전송 | `previous_response_id`로 서버 측 상태 유지 |
| **캐시 효율** | 40% 수준 | 80% 수준 (OpenAI 내부 테스트) |
| **추론 모델 성능** | 기준 | GPT-5 기준 SWE-bench 3% 향상 (동일 프롬프트) |
| **시스템 프롬프트** | `messages`의 system role | `instructions` 파라미터로 분리 |

---

## 2. Responses API의 진짜 장점

### 장점 1: previous_response_id (토큰 비용 절약)

매번 전체 대화를 다시 보내지 않고, response_id만 넘기면 OpenAI가 이전 대화를 기억한다.

```
Chat Completions (매번 전체 전송):
─────────────────────────────────
1번째 호출: [system + user1]                        → 토큰 100개
2번째 호출: [system + user1 + assistant1 + user2]   → 토큰 300개 💸
3번째 호출: [system + ... + user3]                  → 토큰 600개 💸💸

Responses API (previous_response_id 사용):
─────────────────────────────────
1번째 호출: [instructions + user1]                  → 토큰 100개, response_id="resp_001"
2번째 호출: [user2] + previous_response_id          → 토큰 50개 ✅ (새 메시지만)
3번째 호출: [user3] + previous_response_id          → 토큰 50개 ✅ (새 메시지만)
```

**비용 절약 원리:**
- 캐시된 입력 토큰은 75% 저렴 (예: o4-mini 기준)
- OpenAI 내부 테스트에서 캐시 활용률 40% → 80% 향상
- 특히 멀티턴 대화에서 효과가 극대화됨

**reasoning 모델 추가 이점:**
- `previous_response_id`를 사용하면 이전 reasoning 토큰도 자동 유지
- 별도로 reasoning item을 관리할 필요 없음

### 장점 2: 빌트인 도구 (서버 측에서 실행)

직접 구현 없이 API 파라미터로 도구를 활성화하면, **OpenAI 서버에서 실행**해준다.

```python
# 도구 추가는 tools 배열에 넣기만 하면 됨
response = client.responses.create(
    model="gpt-5",
    tools=[
        {"type": "web_search_preview"},
        {"type": "code_interpreter", "container": {"type": "auto"}},
        {"type": "file_search", "vector_store_ids": ["vs_xxx"]},
    ],
    input="이 데이터를 분석해줘"
)
```

| 빌트인 도구 | 무엇을 해주나 | 직접 구현하면 필요한 것 |
|---|---|---|
| **web_search_preview** | 웹 검색 + 출처 인용 | 검색 API 계약, 크롤링, 파싱 로직 |
| **file_search** | 벡터스토어에서 문서 검색 | 임베딩, 벡터DB, 청크 분할, 검색 로직 |
| **code_interpreter** | Python 코드 실행 (샌드박스) | 컨테이너 관리, 보안 격리, 파일 I/O |
| **image_generation** | 이미지 생성/편집 (gpt-image-1) | 별도 이미지 모델 호출, 프롬프트 연결 |
| **mcp** (remote) | 외부 MCP 서버 연결 | MCP 클라이언트 구현 |

### 장점 3: store 파라미터 (대화 영속화)

```python
response = client.responses.create(
    model="gpt-5",
    store=True,  # OpenAI가 이 대화를 서버에 저장
    input="..."
)
# store=True이면 이 response를 나중에 다시 참조 가능
```

- `store: true` → OpenAI가 대화를 서버에 저장, reasoning/tool 컨텍스트도 보존
- Conversations API와 연계하면 영속적인 대화 관리 가능

---

## 3. Azure OpenAI에서의 지원 현황

### 빌트인 도구 지원

| 빌트인 도구 | Azure 지원 | 상태 | 비고 |
|---|---|---|---|
| **web_search_preview** | ✅ 지원 | GA | `web_search_preview`만 지원 (`web_search`는 미지원) |
| **code_interpreter** | ✅ 지원 | GA | 샌드박스 컨테이너 필요 (`container: {"type": "auto"}`) |
| **file_search** | ✅ 지원 | GA | 벡터스토어 사전 생성 필요 |
| **image_generation** | ❓ 미확인 | — | Azure 문서에서 아직 명시적 언급 없음 |
| **hosted MCP** | ✅ 지원 | GA | 원격 MCP 서버 연결 |
| **local MCP** | ✅ 지원 | GA | 로컬 MCP 서버 연결 |

### Azure에서 web_search 사용 예시

```python
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://ai.azure.com/.default"
)

client = OpenAI(
    base_url="https://YOUR-RESOURCE.openai.azure.com/openai/v1/",
    api_key=token_provider,
)

response = client.responses.create(
    model="gpt-5",  # Azure 배포 이름
    tools=[
        {
            "type": "web_search_preview",
            "user_location": {
                "type": "approximate",
                "country": "KR"
            }
        }
    ],
    input="최신 소프트웨어 테스팅 트렌드를 알려줘"
)
print(response.output_text)
```

### Azure에서 code_interpreter 사용 예시

```python
response = client.responses.create(
    model="gpt-5",
    tools=[
        {
            "type": "code_interpreter",
            "container": {"type": "auto"}  # 자동 샌드박스 컨테이너
        }
    ],
    instructions="데이터 분석 전문가로서 코드를 작성하고 실행하세요.",
    input="1부터 100까지 소수의 분포를 시각화해줘"
)
```

### GPT-5 모델 + Responses API 사용 가능 리전

| 리전 | GPT-5 | GPT-5-mini | GPT-5-nano |
|---|---|---|---|
| **East US 2** | ✅ | ✅ | ✅ |
| **Sweden Central** | ✅ | ✅ | ✅ |
| 기타 리전 | 점진적 확대 중 | | |

**주의:** GPT-5를 Chat Completions 모델로 배포한 후, Responses API 엔드포인트(`/openai/v1/responses`)로 호출하는 방식이다.

---

## 4. 우리 프로젝트에서의 활용

### 현재 구현 (DeepAgent + Responses API)

```python
# testcase_agent.py에서의 사용
from langchain.chat_models import init_chat_model

model = init_chat_model(
    "openai:gpt-5-nano",
    use_responses_api=True,             # Responses API 활성화
    use_previous_response_id=True,      # 서버 측 대화 상태 관리 → 토큰 절약
)
```

DeepAgent가 이 모델을 사용하여:
1. `MemorySaver` → 클라이언트 측 상태 관리 (에이전트 루프 제어)
2. `previous_response_id` → 서버 측 상태 관리 (토큰 비용 절약)
3. 두 가지가 **다른 층**에서 동작하므로 충돌 없음

### Azure 전환 시 변경할 코드

```python
# 현재 (OpenAI 직접)
model = init_chat_model(
    "openai:gpt-5-nano",
    use_responses_api=True,
    use_previous_response_id=True,
)

# Azure 전환 시
from langchain_openai import AzureChatOpenAI

model = AzureChatOpenAI(
    azure_deployment="your-gpt5-deployment",  # Azure 배포 이름
    api_version="2025-04-01-preview",
    use_responses_api=True,
    use_previous_response_id=True,
)

# DeepAgent 코드의 나머지는 변경 없음
agent = create_deep_agent(model=model, ...)
```

### 향후 활용 시나리오

| 시나리오 | 사용할 빌트인 도구 | 기대 효과 |
|---|---|---|
| 요구사항에 언급된 기술 표준 검색 | `web_search_preview` | 최신 표준 기반의 정확한 TestCase |
| 첨부된 SRS/PRD PDF 분석 | `file_search` | 대량 문서에서 FR/NFR 자동 추출 |
| 테스트 커버리지 통계 계산 | `code_interpreter` | Python으로 커버리지 계산/차트 생성 |
| 복잡한 요구사항의 멀티턴 분석 | `previous_response_id` | 토큰 비용 절약 + 컨텍스트 유지 |

---

## 5. 주의사항

### Azure 특이사항
- `web_search`가 아닌 `web_search_preview`만 지원됨
- GPT-5 + Responses API 사용 가능 리전이 아직 제한적
- code_interpreter는 컨테이너 비용이 별도 발생할 수 있음
- 5.3-codex는 Codex 전용 모델이므로 빌트인 도구 지원이 다를 수 있음

### Responses API 일반 주의사항
- 일부 사용자가 Chat Completions 대비 레이턴시 증가를 보고함 (리전별 차이)
- `store: true` 설정 시 OpenAI 서버에 대화가 저장되므로 데이터 보안 정책 확인 필요
- Assistants API는 2026년 8월 폐기 예정 → Responses API로 마이그레이션 필요

### 이미지(멀티모달) 입력 관련
- 이미지 입력(분석)은 Responses API 전용 기능이 **아님** — Chat Completions에서도 동일 지원
- 이미지는 message content에 `image_url` 타입으로 넣으면 됨 (API 종류 무관)
- Responses API만의 이미지 관련 장점은 `image_generation` 빌트인 도구 (이미지 **생성**)

---

## 참고 자료

- [OpenAI: Responses API vs Chat Completions 비교](https://platform.openai.com/docs/guides/responses-vs-chat-completions)
- [OpenAI: Responses API 마이그레이션 가이드](https://platform.openai.com/docs/guides/migrate-to-responses)
- [OpenAI: 대화 상태 관리 (previous_response_id)](https://platform.openai.com/docs/guides/conversation-state)
- [OpenAI: 빌트인 도구 사용법](https://platform.openai.com/docs/guides/tools)
- [OpenAI Cookbook: Reasoning 모델 + Responses API 성능 향상](https://cookbook.openai.com/examples/responses_api/reasoning_items)
- [Azure: Responses API 사용법](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses)
- [Azure: Web Search with Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/web-search)
- [Azure: GPT-5 + Responses API Q&A](https://learn.microsoft.com/en-us/answers/questions/5566802/azure-openai-gpt-5-response-api)
- [Azure: Agents vs Responses API 미래 방향](https://learn.microsoft.com/en-us/answers/questions/5536189/future-of-azure-openai-agents-vs-responses-api-(th)
