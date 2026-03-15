/**
 * Pinia 스토어: TestCase 상태 관리
 * =================================
 *
 * Pinia란?
 *   Vue.js의 공식 상태 관리 라이브러리.
 *   여러 컴포넌트/페이지에서 공유해야 하는 데이터를 한 곳에서 관리한다.
 *
 * 왜 필요한가?
 *   Vue 컴포넌트는 부모→자식으로 props를 전달하는데, 관계없는 컴포넌트 간에
 *   데이터를 공유하려면 "글로벌 저장소"가 필요하다. Pinia가 그 역할을 한다.
 *
 * 이 스토어의 역할:
 *   1. 백엔드 API 호출 (fetch, create, generate, validate)
 *   2. 세션 목록/현재 세션 데이터 보관
 *   3. 채팅 메시지 관리 (사용자 입력 + AI 응답)
 *   4. 비동기 작업 폴링 (2초마다 상태 확인)
 *
 * 사용법 (페이지/컴포넌트에서):
 *   const store = useTestcaseStore()
 *   store.sessions        // 세션 목록 읽기
 *   store.extractFrNfr()  // API 호출
 */

import { defineStore } from 'pinia'

// ---------------------------------------------------------------------------
// 타입 정의 (TypeScript 인터페이스)
// ---------------------------------------------------------------------------
// 인터페이스: 객체가 어떤 형태인지 미리 정의하는 "설계도"
// → 타입 체크, 자동완성, 문서화 역할

/** FR/NFR 항목 하나의 구조 */
interface FrNfrItem {
  id: string           // "FR-01" 또는 "NFR-01"
  title: string        // 짧은 제목
  description: string  // 상세 설명
  priority: string     // "high" | "medium" | "low"
}

/** 테스트 케이스 하나의 구조 */
interface TestCase {
  id: string              // "TC-01"
  title: string           // 짧은 제목
  description: string     // 무엇을 테스트하는지
  preconditions: string   // 사전 조건
  steps: string[]         // 테스트 단계 배열
  expected_result: string // 기대 결과
  priority: string        // "high" | "medium" | "low"
  category: string        // "functional" | "security" | "performance" 등
  fr_nfr_ref: string[]    // 이 TC가 커버하는 FR/NFR ID 배열 (예: ["FR-01", "NFR-02"])
}

/** 커버리지 검증 결과 구조 */
interface ValidationResult {
  coverage_score: number     // 0.0 ~ 1.0 (예: 0.85 = 85%)
  missing_areas: string[]    // 누락된 영역 목록
  feedback: string           // AI의 상세 피드백
  is_sufficient: boolean     // 충분한지 여부
}

/** 백엔드 세션 데이터 구조 (DB 테이블 testcase_sessions와 대응) */
interface Session {
  id: string
  requirement: string               // 원본 요구사항 텍스트
  requirement_type: string          // "requirement" | "SRS" | "PRD"
  status: string                    // "pending" | "extracting" | "extracted" | "processing" | "completed" | "failed"
  fr_nfr: { fr: FrNfrItem[], nfr: FrNfrItem[] } | null  // 추출된 FR/NFR
  testcases: TestCase[] | null      // 생성된 테스트 케이스
  validation: ValidationResult | null  // 검증 결과
  created_at: string                // ISO 날짜 문자열
  updated_at: string
}

/** 에이전트 진행 단계 (실시간 스트리밍용) */
interface AgentStep {
  message: string        // 표시할 메시지 (예: "FR/NFR 추출 중...")
  done: boolean          // 완료 여부 (true: ✅, false: 🔄)
  icon?: string          // 아이콘 타입 (search, testcase, chart 등)
}

/** 채팅 메시지 구조 (프론트엔드 전용, DB에 저장하지 않음) */
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'       // 사용자 메시지 or AI 응답
  content: string                   // 표시할 텍스트
  type: 'text' | 'fr_nfr' | 'testcases' | 'validation' | 'loading'  // 메시지 타입별 렌더링 분기
  data?: any                        // FR/NFR, TC, Validation 데이터 (type에 따라 다름)
  timestamp: Date
  actionType?: 'generate' | 'validate'  // 메시지 하단에 표시할 액션 버튼 종류
  steps?: AgentStep[]               // 에이전트 진행 단계 (loading 타입에서 사용)
}

// 타입을 외부에서도 사용할 수 있도록 export
export type { FrNfrItem, TestCase, ValidationResult, Session, ChatMessage, AgentStep }

// ---------------------------------------------------------------------------
// 메시지 ID 생성 유틸리티
// ---------------------------------------------------------------------------
// 각 채팅 메시지에 고유 ID를 부여한다 (Vue의 v-for에서 :key로 사용)
let msgCounter = 0
function newMsgId(): string {
  return `msg-${++msgCounter}-${Date.now()}`
}

// ---------------------------------------------------------------------------
// Pinia 스토어 정의
// ---------------------------------------------------------------------------
// defineStore('스토어이름', { ... }): Pinia 스토어를 정의한다
// '스토어이름'은 DevTools에서 식별용으로 사용된다
export const useTestcaseStore = defineStore('testcase', {

  // =========================================================================
  // state: 스토어의 데이터 (Vue의 data()와 유사)
  // =========================================================================
  // 여기에 정의한 값들은 반응형(reactive)이다
  // → 값이 바뀌면 이 값을 사용하는 모든 컴포넌트가 자동으로 업데이트됨
  state: () => ({
    sessions: [] as Session[],                    // 전체 세션 목록
    currentSession: null as Session | null,       // 현재 선택된 세션
    messages: [] as ChatMessage[],                // 채팅 메시지 배열
    loading: false,                               // API 호출 중 여부 (버튼 비활성화에 사용)
    polling: false,                               // 폴링/스트리밍 진행 중 여부
    error: null as string | null,                 // 에러 메시지 (토스트 표시)
    _pollTimer: null as ReturnType<typeof setInterval> | null,  // 폴링 타이머 ID (fallback용)
    _eventSource: null as EventSource | null,     // SSE 연결 객체 (실시간 스트리밍용)
    _pendingLoadingMsgId: null as string | null,  // 현재 로딩 메시지의 ID (교체용)
  }),

  // =========================================================================
  // getters: 계산된 속성 (Vue의 computed와 유사)
  // =========================================================================
  // state에서 파생된 값. 캐싱되며 의존하는 state가 변경될 때만 재계산.
  getters: {
    /** 세션을 최신순으로 정렬하여 반환 */
    sortedSessions(): Session[] {
      return [...this.sessions].sort((a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
    }
  },

  // =========================================================================
  // actions: 메서드 (state를 변경하거나 API를 호출하는 함수들)
  // =========================================================================
  actions: {
    // -----------------------------------------------------------------------
    // API 호출: 세션 목록/상세 조회
    // -----------------------------------------------------------------------

    /** 세션 목록 조회 (GET /testcase/) */
    async fetchSessions() {
      // useRuntimeConfig(): nuxt.config.ts의 runtimeConfig에 접근
      // → config.public.apiBase = 'http://localhost:3480/api/v1'
      const config = useRuntimeConfig()
      try {
        // $fetch: Nuxt가 제공하는 HTTP 클라이언트 (fetch API 래퍼)
        // <Session[]>: TypeScript 제네릭 → 응답 타입을 Session 배열로 지정
        const data = await $fetch<Session[]>(`${config.public.apiBase}/testcase/`)
        this.sessions = data  // 반응형 state 업데이트 → UI 자동 갱신
      } catch (e: any) {
        this.error = e.message || 'Failed to fetch sessions'
      }
    },

    /** 세션 상세 조회 (GET /testcase/{id}) */
    async fetchSession(id: string) {
      const config = useRuntimeConfig()
      try {
        const data = await $fetch<Session>(`${config.public.apiBase}/testcase/${id}`)
        this.currentSession = data  // 현재 세션 업데이트
        return data
      } catch (e: any) {
        this.error = e.message || 'Failed to fetch session'
      }
    },

    // -----------------------------------------------------------------------
    // SSE 스트리밍: 에이전트 진행 상황 실시간 수신
    // -----------------------------------------------------------------------
    // 이전: 2초마다 DB 폴링 → "processing..." 만 표시
    // 현재: SSE(Server-Sent Events)로 에이전트의 도구 호출 과정을 실시간 수신
    //
    // SSE란?
    // - 서버 → 클라이언트로 단방향 이벤트를 전송하는 HTTP 기반 기술
    // - 브라우저의 EventSource API로 수신 (자동 재연결 기능 포함)
    // - WebSocket보다 단순하고 HTTP 프록시와 호환됨
    //
    // 이벤트 종류:
    //   step: 에이전트의 중간 과정 (도구 시작/완료)
    //   done: 작업 완료 (최종 결과 로드)
    //   error: 에러 발생

    /** 스트리밍/폴링 중지 */
    stopPolling() {
      // SSE 연결 종료
      if (this._eventSource) {
        this._eventSource.close()
        this._eventSource = null
      }
      // 폴링 타이머 종료 (fallback용)
      if (this._pollTimer) {
        clearInterval(this._pollTimer)
        this._pollTimer = null
      }
      this.polling = false
    },

    /**
     * SSE 스트리밍 시작: 에이전트의 도구 호출 과정을 실시간으로 수신한다.
     *
     * EventSource가 백엔드의 /stream 엔드포인트에 연결하면:
     * 1. step 이벤트 → 로딩 메시지에 진행 단계 추가 (예: "FR/NFR 추출 중...")
     * 2. done 이벤트 → 최종 결과를 DB에서 가져와서 표시
     * 3. error 이벤트 → 에러 메시지 표시
     *
     * SSE 연결이 실패하면 자동으로 폴링(fallback)으로 전환한다.
     *
     * @param sessionId - 세션 UUID
     * @param expectedStatus - 기다리는 완료 상태 ('extracted' | 'completed' | 'validated')
     */
    startPolling(sessionId: string, expectedStatus: string) {
      this.stopPolling()
      this.polling = true

      const config = useRuntimeConfig()
      const streamUrl = `${config.public.apiBase}/testcase/${sessionId}/stream`

      try {
        // -----------------------------------------------------------------
        // EventSource: 브라우저 내장 SSE 클라이언트
        // -----------------------------------------------------------------
        // new EventSource(url): 서버에 HTTP GET 연결을 열고 이벤트를 수신
        // 연결이 끊어지면 자동으로 재연결 시도 (브라우저 내장 기능)
        const es = new EventSource(streamUrl)
        this._eventSource = es

        // -----------------------------------------------------------------
        // step 이벤트: 에이전트의 중간 과정 (도구 시작/완료)
        // -----------------------------------------------------------------
        // 도구 호출 시마다 수신됨. 로딩 메시지에 단계를 추가하여
        // 사용자에게 "에이전트가 지금 뭘 하고 있는지" 보여준다.
        es.addEventListener('step', (e: MessageEvent) => {
          const data = JSON.parse(e.data)
          this._addAgentStep(data)
        })

        // -----------------------------------------------------------------
        // done 이벤트: 작업 완료
        // -----------------------------------------------------------------
        // 에이전트가 모든 도구 호출을 마치고 결과가 DB에 저장된 후 수신.
        // DB에서 최신 세션 데이터를 가져와서 결과 메시지로 교체한다.
        es.addEventListener('done', async (e: MessageEvent) => {
          this.stopPolling()
          // 최종 결과를 DB에서 가져와서 표시
          const session = await this.fetchSession(sessionId)
          if (!session) return

          if (expectedStatus === 'extracted' && session.fr_nfr) {
            this._replaceLoadingMsg({
              type: 'fr_nfr',
              content: 'Here are the extracted Functional and Non-Functional Requirements:',
              data: session.fr_nfr,
              actionType: 'generate'
            })
          } else if (expectedStatus === 'completed' && session.testcases) {
            this._replaceLoadingMsg({
              type: 'testcases',
              content: `Generated ${session.testcases.length} test cases:`,
              data: session.testcases,
              actionType: 'validate'
            })
          } else if (expectedStatus === 'validated' && session.validation) {
            this._replaceLoadingMsg({
              type: 'validation',
              content: 'Validation complete. Here are the coverage results:',
              data: session.validation
            })
          }
          await this.fetchSessions()
        })

        // -----------------------------------------------------------------
        // error 이벤트: 에이전트 실행 중 에러 발생
        // -----------------------------------------------------------------
        es.addEventListener('error', (e: Event) => {
          // EventSource 자체 에러 (연결 실패 등)
          if (es.readyState === EventSource.CLOSED) {
            // SSE 연결 실패 → 폴링으로 fallback
            this._fallbackToPolling(sessionId, expectedStatus)
            return
          }
          // 서버에서 보낸 error 이벤트
          const msgEvent = e as MessageEvent
          if (msgEvent.data) {
            try {
              const data = JSON.parse(msgEvent.data)
              this.stopPolling()
              this._replaceLoadingMsg({
                type: 'text',
                content: data.message || 'Something went wrong.'
              })
              this.fetchSessions()
            } catch {
              // JSON 파싱 실패 시 무시
            }
          }
        })

      } catch {
        // EventSource 생성 자체가 실패 (SSR 환경 등)
        // → 폴링으로 fallback
        this._fallbackToPolling(sessionId, expectedStatus)
      }
    },

    /**
     * SSE 실패 시 기존 폴링 방식으로 fallback.
     * 2초마다 DB를 직접 조회하여 완료를 감지한다.
     */
    _fallbackToPolling(sessionId: string, expectedStatus: string) {
      this.stopPolling()
      this.polling = true
      this.fetchSession(sessionId)

      this._pollTimer = setInterval(async () => {
        const session = await this.fetchSession(sessionId)
        if (!session) return

        if (expectedStatus === 'extracted' && session.status === 'extracted') {
          this.stopPolling()
          this._replaceLoadingMsg({
            type: 'fr_nfr',
            content: 'Here are the extracted Functional and Non-Functional Requirements:',
            data: session.fr_nfr,
            actionType: 'generate'
          })
          await this.fetchSessions()
        } else if (expectedStatus === 'completed' && session.status === 'completed') {
          this.stopPolling()
          this._replaceLoadingMsg({
            type: 'testcases',
            content: `Generated ${session.testcases?.length || 0} test cases:`,
            data: session.testcases,
            actionType: 'validate'
          })
          await this.fetchSessions()
        } else if (expectedStatus === 'validated' && session.validation) {
          this.stopPolling()
          this._replaceLoadingMsg({
            type: 'validation',
            content: 'Validation complete. Here are the coverage results:',
            data: session.validation
          })
          await this.fetchSessions()
        } else if (session.status === 'failed') {
          this.stopPolling()
          this._replaceLoadingMsg({
            type: 'text',
            content: 'Something went wrong while processing your request. Please try again.'
          })
          await this.fetchSessions()
        }
      }, 2000)
    },

    // -----------------------------------------------------------------------
    // 채팅 메시지 관리
    // -----------------------------------------------------------------------

    /**
     * 로딩 메시지 추가 (타이핑 인디케이터 + 상태 텍스트)
     * → 나중에 _replaceLoadingMsg()로 실제 결과 메시지로 교체된다
     */
    _addLoadingMsg(content: string) {
      const msg: ChatMessage = {
        id: newMsgId(),
        role: 'assistant',
        content,
        type: 'loading',  // loading 타입 → 타이핑 인디케이터(●●●) 표시
        timestamp: new Date()
      }
      this.messages.push(msg)
      this._pendingLoadingMsgId = msg.id  // 교체 대상 ID 기록
    },

    /**
     * 에이전트 상태 메시지를 업데이트한다 (ChatGPT thinking 스타일).
     *
     * SSE의 step 이벤트를 받을 때마다 호출된다.
     * 단계를 누적하지 않고, 현재 로딩 메시지의 content를 교체한다.
     * → "요구사항 분석 중..." → "FR/NFR 추출 중..." → "테스트 케이스 생성 중..."
     *
     * ChatGPT의 thinking 표시처럼:
     * - 하나의 메시지만 표시
     * - 새로운 상태가 오면 이전 메시지를 교체
     * - shimmer 애니메이션으로 "처리 중" 느낌
     */
    _addAgentStep(data: { type: string, message: string }) {
      if (!this._pendingLoadingMsgId) return
      const idx = this.messages.findIndex(m => m.id === this._pendingLoadingMsgId)
      if (idx < 0) return

      // content만 교체 → shimmer 애니메이션이 새 텍스트에 적용됨
      const msg = this.messages[idx]
      msg.content = data.message

      // 반응형 업데이트 트리거
      this.messages[idx] = { ...msg }
    },

    /**
     * 로딩 메시지를 실제 결과 메시지로 교체
     *
     * 흐름:
     * 1. API 호출 직후: _addLoadingMsg("Analyzing...") → ●●● 애니메이션 표시
     * 2. 폴링으로 완료 감지: _replaceLoadingMsg({type: 'fr_nfr', data: ...})
     * 3. 로딩 메시지가 FR/NFR 결과 카드로 교체됨
     */
    _replaceLoadingMsg(update: Partial<ChatMessage>) {
      if (!this._pendingLoadingMsgId) return
      const idx = this.messages.findIndex(m => m.id === this._pendingLoadingMsgId)
      if (idx >= 0) {
        // 기존 메시지의 속성을 유지하면서 update의 속성으로 덮어쓴다
        this.messages[idx] = {
          ...this.messages[idx],
          ...update,
          timestamp: new Date()
        } as ChatMessage
      }
      this._pendingLoadingMsgId = null
    },

    /** 사용자 메시지 추가 (채팅 오른쪽에 표시) */
    addUserMessage(content: string) {
      this.messages.push({
        id: newMsgId(),
        role: 'user',
        content,
        type: 'text',
        timestamp: new Date()
      })
    },

    // -----------------------------------------------------------------------
    // API 호출: FR/NFR 추출, TC 생성, 검증
    // -----------------------------------------------------------------------

    /**
     * FR/NFR 추출 시작 (POST /testcase/extract-fr-nfr)
     *
     * 전체 흐름:
     * 1. 사용자 메시지 추가 (채팅에 표시)
     * 2. 로딩 메시지 추가 (●●● 애니메이션)
     * 3. API 호출 → 202 응답 (백엔드에서 비동기 처리 시작)
     * 4. 폴링 시작 → 2초마다 상태 확인
     * 5. 완료 시 로딩 메시지 → FR/NFR 결과 카드로 교체
     */
    async extractFrNfr(requirement: string, requirementType: string) {
      const config = useRuntimeConfig()
      this.loading = true
      this.error = null

      // 채팅에 사용자 메시지와 로딩 표시 추가
      this.addUserMessage(requirement)
      this._addLoadingMsg('Analyzing your document to extract Functional and Non-Functional Requirements...')

      try {
        // 백엔드에 POST 요청 → 202 Accepted 반환 (즉시 응답, 백그라운드 처리)
        const data = await $fetch<{ id: string, status: string }>(`${config.public.apiBase}/testcase/extract-fr-nfr`, {
          method: 'POST',
          body: { requirement, requirement_type: requirementType }
        })

        // 현재 세션 정보를 임시로 설정 (폴링이 완료되면 서버 데이터로 교체)
        this.currentSession = {
          id: data.id,
          requirement,
          requirement_type: requirementType,
          status: data.status,
          fr_nfr: null,
          testcases: null,
          validation: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }
        await this.fetchSessions()  // 사이드바 갱신
        this.startPolling(data.id, 'extracted')  // 폴링 시작 (extracted 상태 대기)
        return data
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to extract FR/NFR'
        this._replaceLoadingMsg({
          type: 'text',
          content: `Error: ${this.error}`
        })
      } finally {
        this.loading = false  // 버튼 활성화
      }
    },

    /**
     * 기존 세션에서 TC 생성 (POST /testcase/{id}/generate)
     *
     * FR/NFR 추출이 완료된 세션에서 "Generate Test Cases" 버튼을 누르면 호출
     */
    async generateFromSession(sessionId: string) {
      const config = useRuntimeConfig()
      this.loading = true
      this.error = null

      this.addUserMessage('Generate comprehensive test cases from the extracted requirements.')
      this._addLoadingMsg('Generating comprehensive test cases based on the FR/NFR analysis...')

      try {
        const data = await $fetch<{ id: string, status: string }>(`${config.public.apiBase}/testcase/${sessionId}/generate`, {
          method: 'POST'
        })
        if (this.currentSession) {
          this.currentSession.status = data.status
        }
        this.startPolling(sessionId, 'completed')  // completed 상태 대기
        return data
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to generate test cases'
        this._replaceLoadingMsg({
          type: 'text',
          content: `Error: ${this.error}`
        })
      } finally {
        this.loading = false
      }
    },

    /**
     * 커버리지 검증 (POST /testcase/{id}/validate)
     *
     * TC 생성이 완료된 세션에서 "Validate Coverage" 버튼을 누르면 호출
     */
    async validateSession(sessionId: string) {
      const config = useRuntimeConfig()
      this.loading = true
      this.error = null

      this.addUserMessage('Validate the test case coverage against the requirements.')
      this._addLoadingMsg('Validating test case coverage against your requirements...')

      try {
        await $fetch(`${config.public.apiBase}/testcase/${sessionId}/validate`, {
          method: 'POST'
        })
        if (this.currentSession) {
          this.currentSession.status = 'validating'
        }
        this.startPolling(sessionId, 'validated')  // validated 상태 대기
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to validate'
        this._replaceLoadingMsg({
          type: 'text',
          content: `Error: ${this.error}`
        })
      } finally {
        this.loading = false
      }
    },

    // -----------------------------------------------------------------------
    // 세션 메시지 복원 (사이드바에서 세션 클릭 시)
    // -----------------------------------------------------------------------

    /**
     * DB에 저장된 세션 데이터로부터 채팅 메시지를 재구성한다.
     *
     * 세션 데이터(fr_nfr, testcases, validation)를 시간순으로
     * 채팅 메시지로 변환하여 대화 히스토리를 복원한다.
     */
    buildMessagesFromSession(session: Session) {
      this.messages = []

      // 1. 사용자의 원본 요구사항 메시지
      this.addUserMessage(session.requirement)

      // 2. FR/NFR 추출 결과 (있는 경우)
      if (session.fr_nfr) {
        this.messages.push({
          id: newMsgId(),
          role: 'assistant',
          content: 'Here are the extracted Functional and Non-Functional Requirements:',
          type: 'fr_nfr',
          data: session.fr_nfr,
          // TC가 아직 없으면 "Generate" 버튼 표시, 있으면 표시 안 함
          actionType: (!session.testcases || session.testcases.length === 0) ? 'generate' : undefined,
          timestamp: new Date(session.created_at)
        })
      } else if (session.status === 'extracting') {
        // 아직 추출 중이면 로딩 메시지 표시
        this._addLoadingMsg('Analyzing your document to extract Functional and Non-Functional Requirements...')
      }

      // 3. TC 생성 결과 (있는 경우)
      if (session.testcases && session.testcases.length > 0) {
        this.messages.push({
          id: newMsgId(),
          role: 'user',
          content: 'Generate comprehensive test cases from the extracted requirements.',
          type: 'text',
          timestamp: new Date(session.created_at)
        })
        this.messages.push({
          id: newMsgId(),
          role: 'assistant',
          content: `Generated ${session.testcases.length} test cases:`,
          type: 'testcases',
          data: session.testcases,
          actionType: !session.validation ? 'validate' : undefined,
          timestamp: new Date(session.created_at)
        })
      } else if (session.status === 'processing' || session.status === 'generating') {
        this.messages.push({
          id: newMsgId(),
          role: 'user',
          content: 'Generate comprehensive test cases from the extracted requirements.',
          type: 'text',
          timestamp: new Date()
        })
        this._addLoadingMsg('Generating comprehensive test cases based on the FR/NFR analysis...')
      }

      // 4. 검증 결과 (있는 경우)
      if (session.validation) {
        this.messages.push({
          id: newMsgId(),
          role: 'user',
          content: 'Validate the test case coverage against the requirements.',
          type: 'text',
          timestamp: new Date(session.created_at)
        })
        this.messages.push({
          id: newMsgId(),
          role: 'assistant',
          content: 'Validation complete. Here are the coverage results:',
          type: 'validation',
          data: session.validation,
          timestamp: new Date(session.created_at)
        })
      }
    },

    /**
     * 사이드바에서 세션 선택 시 호출
     *
     * 1. 최신 세션 데이터를 서버에서 가져온다
     * 2. 채팅 메시지를 재구성한다
     * 3. 진행 중인 작업이 있으면 폴링을 재개한다
     */
    async selectSession(session: Session) {
      this.stopPolling()
      const fresh = await this.fetchSession(session.id)
      if (fresh) {
        this.buildMessagesFromSession(fresh)
        // 진행 중인 상태면 폴링 재개
        if (fresh.status === 'extracting') {
          this.polling = true
          this.startPolling(fresh.id, 'extracted')
        } else if (fresh.status === 'processing' || fresh.status === 'generating') {
          this.polling = true
          this.startPolling(fresh.id, 'completed')
        } else if (fresh.status === 'validating') {
          this.polling = true
          this.startPolling(fresh.id, 'validated')
        }
      }
    },

    /** 새 채팅 시작 (현재 세션 초기화) */
    clearChat() {
      this.stopPolling()
      this.currentSession = null
      this.messages = []
      this.error = null
    }
  }
})
