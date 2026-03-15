import { defineStore } from 'pinia'

interface FrNfrItem {
  id: string
  title: string
  description: string
  priority: string
}

interface TestCase {
  id: string
  title: string
  description: string
  preconditions: string
  steps: string[]
  expected_result: string
  priority: string
  category: string
  fr_nfr_ref: string[]
}

interface ValidationResult {
  coverage_score: number
  missing_areas: string[]
  feedback: string
  is_sufficient: boolean
}

interface Session {
  id: string
  requirement: string
  requirement_type: string
  status: string
  fr_nfr: { fr: FrNfrItem[], nfr: FrNfrItem[] } | null
  testcases: TestCase[] | null
  validation: ValidationResult | null
  created_at: string
  updated_at: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  type: 'text' | 'fr_nfr' | 'testcases' | 'validation' | 'loading'
  data?: any
  timestamp: Date
  actionType?: 'generate' | 'validate'
}

export type { FrNfrItem, TestCase, ValidationResult, Session, ChatMessage }

let msgCounter = 0
function newMsgId(): string {
  return `msg-${++msgCounter}-${Date.now()}`
}

export const useTestcaseStore = defineStore('testcase', {
  state: () => ({
    sessions: [] as Session[],
    currentSession: null as Session | null,
    messages: [] as ChatMessage[],
    loading: false,
    polling: false,
    error: null as string | null,
    _pollTimer: null as ReturnType<typeof setInterval> | null,
    _pendingLoadingMsgId: null as string | null,
  }),

  getters: {
    sortedSessions(): Session[] {
      return [...this.sessions].sort((a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
    }
  },

  actions: {
    async fetchSessions() {
      const config = useRuntimeConfig()
      try {
        const data = await $fetch<Session[]>(`${config.public.apiBase}/testcase/`)
        this.sessions = data
      } catch (e: any) {
        this.error = e.message || 'Failed to fetch sessions'
      }
    },

    async fetchSession(id: string) {
      const config = useRuntimeConfig()
      try {
        const data = await $fetch<Session>(`${config.public.apiBase}/testcase/${id}`)
        this.currentSession = data
        return data
      } catch (e: any) {
        this.error = e.message || 'Failed to fetch session'
      }
    },

    stopPolling() {
      if (this._pollTimer) {
        clearInterval(this._pollTimer)
        this._pollTimer = null
      }
      this.polling = false
    },

    startPolling(sessionId: string, expectedStatus: string) {
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

    _addLoadingMsg(content: string) {
      const msg: ChatMessage = {
        id: newMsgId(),
        role: 'assistant',
        content,
        type: 'loading',
        timestamp: new Date()
      }
      this.messages.push(msg)
      this._pendingLoadingMsgId = msg.id
    },

    _replaceLoadingMsg(update: Partial<ChatMessage>) {
      if (!this._pendingLoadingMsgId) return
      const idx = this.messages.findIndex(m => m.id === this._pendingLoadingMsgId)
      if (idx >= 0) {
        this.messages[idx] = {
          ...this.messages[idx],
          ...update,
          timestamp: new Date()
        } as ChatMessage
      }
      this._pendingLoadingMsgId = null
    },

    addUserMessage(content: string) {
      this.messages.push({
        id: newMsgId(),
        role: 'user',
        content,
        type: 'text',
        timestamp: new Date()
      })
    },

    async extractFrNfr(requirement: string, requirementType: string) {
      const config = useRuntimeConfig()
      this.loading = true
      this.error = null

      this.addUserMessage(requirement)
      this._addLoadingMsg('Analyzing your document to extract Functional and Non-Functional Requirements...')

      try {
        const data = await $fetch<{ id: string, status: string }>(`${config.public.apiBase}/testcase/extract-fr-nfr`, {
          method: 'POST',
          body: { requirement, requirement_type: requirementType }
        })
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
        await this.fetchSessions()
        this.startPolling(data.id, 'extracted')
        return data
      } catch (e: any) {
        this.error = e.data?.detail || e.message || 'Failed to extract FR/NFR'
        this._replaceLoadingMsg({
          type: 'text',
          content: `Error: ${this.error}`
        })
      } finally {
        this.loading = false
      }
    },

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
        this.startPolling(sessionId, 'completed')
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
        this.startPolling(sessionId, 'validated')
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

    buildMessagesFromSession(session: Session) {
      this.messages = []

      // User message with requirement
      this.addUserMessage(session.requirement)

      // FR/NFR results
      if (session.fr_nfr) {
        this.messages.push({
          id: newMsgId(),
          role: 'assistant',
          content: 'Here are the extracted Functional and Non-Functional Requirements:',
          type: 'fr_nfr',
          data: session.fr_nfr,
          actionType: (!session.testcases || session.testcases.length === 0) ? 'generate' : undefined,
          timestamp: new Date(session.created_at)
        })
      } else if (session.status === 'extracting') {
        this._addLoadingMsg('Analyzing your document to extract Functional and Non-Functional Requirements...')
      }

      // Test cases
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

      // Validation
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

    async selectSession(session: Session) {
      this.stopPolling()
      const fresh = await this.fetchSession(session.id)
      if (fresh) {
        this.buildMessagesFromSession(fresh)
        // Resume polling if in-progress
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

    clearChat() {
      this.stopPolling()
      this.currentSession = null
      this.messages = []
      this.error = null
    }
  }
})
