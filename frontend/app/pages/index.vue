<script setup lang="ts">
import { useTestcaseStore } from '~/stores/testcase'
import type { Session, TestCase } from '~/stores/testcase'

const store = useTestcaseStore()

// UI state
const sidebarOpen = ref(true)
const requirement = ref('')
const requirementType = ref('requirement')
const chatContainer = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const expandedTestCases = ref<Set<string>>(new Set())
const fileInputRef = ref<HTMLInputElement | null>(null)

const requirementTypes = [
  { label: 'Requirement', value: 'requirement' },
  { label: 'SRS', value: 'srs' },
  { label: 'PRD', value: 'prd' }
]

// Date grouping for sidebar
function groupSessionsByDate(sessions: Session[]) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const weekAgo = new Date(today.getTime() - 7 * 86400000)
  const monthAgo = new Date(today.getTime() - 30 * 86400000)

  const groups: { label: string; sessions: Session[] }[] = [
    { label: 'Today', sessions: [] },
    { label: 'Yesterday', sessions: [] },
    { label: 'Previous 7 Days', sessions: [] },
    { label: 'Previous 30 Days', sessions: [] },
    { label: 'Older', sessions: [] }
  ]

  for (const s of sessions) {
    const d = new Date(s.created_at)
    if (d >= today) groups[0].sessions.push(s)
    else if (d >= yesterday) groups[1].sessions.push(s)
    else if (d >= weekAgo) groups[2].sessions.push(s)
    else if (d >= monthAgo) groups[3].sessions.push(s)
    else groups[4].sessions.push(s)
  }

  return groups.filter(g => g.sessions.length > 0)
}

const sessionGroups = computed(() => groupSessionsByDate(store.sortedSessions))

// Truncate text
function truncate(text: string, len: number) {
  if (!text) return ''
  return text.length > len ? text.substring(0, len) + '...' : text
}

// Priority color
function priorityColor(priority: string) {
  const map: Record<string, string> = {
    high: 'text-red-400', medium: 'text-yellow-400', low: 'text-green-400', critical: 'text-red-500'
  }
  return map[priority?.toLowerCase()] || 'text-gray-400'
}

function priorityBg(priority: string) {
  const map: Record<string, string> = {
    high: 'bg-red-500/10 text-red-400 border-red-500/20',
    medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    low: 'bg-green-500/10 text-green-400 border-green-500/20',
    critical: 'bg-red-500/15 text-red-500 border-red-500/30'
  }
  return map[priority?.toLowerCase()] || 'bg-gray-500/10 text-gray-400 border-gray-500/20'
}

// Coverage percent
function coveragePercent(score: number) {
  return score > 1 ? Math.round(score) : Math.round(score * 100)
}

function coverageColor(pct: number) {
  if (pct >= 80) return 'text-green-400'
  if (pct >= 50) return 'text-yellow-400'
  return 'text-red-400'
}

function coverageBarColor(pct: number) {
  if (pct >= 80) return 'bg-green-500'
  if (pct >= 50) return 'bg-yellow-500'
  return 'bg-red-500'
}

function coverageRingColor(pct: number) {
  if (pct >= 80) return 'border-green-500'
  if (pct >= 50) return 'border-yellow-500'
  return 'border-red-500'
}

// Toggle test case expansion
function toggleTestCase(id: string) {
  if (expandedTestCases.value.has(id)) {
    expandedTestCases.value.delete(id)
  } else {
    expandedTestCases.value.add(id)
  }
}

// Scroll to bottom
function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

// Watch messages to auto-scroll
watch(() => store.messages.length, () => {
  scrollToBottom()
})

watch(() => store.messages.map(m => m.type).join(','), () => {
  scrollToBottom()
})

// Handle submit
async function handleSubmit() {
  const text = requirement.value.trim()
  if (!text || store.loading) return

  if (!store.currentSession) {
    // New session: extract FR/NFR
    await store.extractFrNfr(text, requirementType.value)
    requirement.value = ''
    scrollToBottom()
  }
}

// Handle keyboard
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

// Generate test cases action
async function handleGenerate() {
  if (!store.currentSession) return
  await store.generateFromSession(store.currentSession.id)
  scrollToBottom()
}

// Validate action
async function handleValidate() {
  if (!store.currentSession) return
  await store.validateSession(store.currentSession.id)
  scrollToBottom()
}

// Select session from sidebar
async function selectSession(session: Session) {
  await store.selectSession(session)
  scrollToBottom()
}

// New chat
function startNewChat() {
  store.clearChat()
  requirement.value = ''
  requirementType.value = 'requirement'
  expandedTestCases.value.clear()
}

// File attachment handler
function handleFileAttach() {
  fileInputRef.value?.click()
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (ev) => {
    const text = ev.target?.result as string
    if (text) {
      requirement.value = text
    }
  }
  reader.readAsText(file)
  target.value = ''
}

// Can send check
const canSend = computed(() => {
  return requirement.value.trim().length > 0 && !store.loading && !store.currentSession
})

// Show input bar (always when no session, never when session active - actions are inline)
const showInputBar = computed(() => !store.currentSession)

// Load sessions on mount
onMounted(() => {
  store.fetchSessions()
})
</script>

<template>
  <div class="h-screen flex overflow-hidden" style="background-color: #0d1117;">
    <!-- Sidebar -->
    <aside
      class="flex flex-col shrink-0 transition-all duration-300 ease-in-out overflow-hidden border-r"
      :class="sidebarOpen ? 'w-[280px]' : 'w-0'"
      style="background-color: #161b22; border-color: #30363d;"
    >
      <div class="flex flex-col h-full min-w-[280px]">
        <!-- Sidebar Header -->
        <div class="p-3 flex items-center gap-2">
          <button
            @click="startNewChat"
            class="flex-1 flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors hover:bg-white/5"
            style="border: 1px solid #30363d;"
          >
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Chat
          </button>
          <button
            @click="sidebarOpen = false"
            class="p-2 rounded-lg hover:bg-white/5 transition-colors"
            style="color: #8b949e;"
          >
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>
        </div>

        <!-- Session List -->
        <div class="flex-1 overflow-y-auto px-2 pb-4">
          <div v-if="store.sessions.length === 0" class="text-center px-4 mt-8" style="color: #484f58;">
            <p class="text-sm">No conversations yet</p>
          </div>

          <div v-for="group in sessionGroups" :key="group.label" class="mb-4">
            <div class="px-2 py-1.5 text-xs font-medium" style="color: #484f58;">
              {{ group.label }}
            </div>
            <button
              v-for="session in group.sessions"
              :key="session.id"
              @click="selectSession(session)"
              class="w-full text-left px-3 py-2 rounded-lg text-sm transition-colors mb-0.5 group relative"
              :class="store.currentSession?.id === session.id ? 'bg-white/10' : 'hover:bg-white/5'"
              :style="{ color: store.currentSession?.id === session.id ? '#e6edf3' : '#8b949e' }"
            >
              <p class="truncate pr-2">{{ truncate(session.requirement, 40) }}</p>
            </button>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Top Bar -->
      <header
        class="h-12 flex items-center px-4 gap-3 shrink-0 border-b"
        style="background-color: #0d1117; border-color: #30363d;"
      >
        <button
          v-if="!sidebarOpen"
          @click="sidebarOpen = true"
          class="p-1.5 rounded-lg hover:bg-white/5 transition-colors"
          style="color: #8b949e;"
        >
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <div class="flex items-center gap-2">
          <svg class="w-5 h-5" style="color: #7c6af4;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
          </svg>
          <h1 class="text-sm font-semibold" style="color: #e6edf3;">TestCase Generator AI</h1>
        </div>
        <div class="flex-1" />
        <span
          v-if="store.currentSession"
          class="text-xs px-2 py-0.5 rounded-full"
          :class="{
            'bg-blue-500/10 text-blue-400': ['extracting', 'validating'].includes(store.currentSession.status),
            'bg-yellow-500/10 text-yellow-400': ['processing', 'generating', 'pending'].includes(store.currentSession.status),
            'bg-green-500/10 text-green-400': ['extracted', 'completed'].includes(store.currentSession.status),
            'bg-red-500/10 text-red-400': store.currentSession.status === 'failed'
          }"
        >
          {{ store.currentSession.status }}
        </span>
      </header>

      <!-- Chat Area -->
      <div class="flex-1 overflow-hidden flex flex-col">
        <!-- Messages Container -->
        <div ref="chatContainer" class="flex-1 overflow-y-auto">

          <!-- Welcome Screen (no session, no messages) -->
          <div v-if="store.messages.length === 0 && !store.currentSession" class="h-full flex flex-col items-center justify-center px-4">
            <div class="max-w-2xl w-full text-center">
              <div class="mb-6">
                <div
                  class="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
                  style="background: linear-gradient(135deg, #7c6af4 0%, #4f46e5 100%);"
                >
                  <svg class="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.611L5 14.5" />
                  </svg>
                </div>
                <h2 class="text-2xl font-semibold mb-2" style="color: #e6edf3;">What requirement would you like to analyze?</h2>
                <p class="text-sm" style="color: #8b949e;">
                  Paste your requirement, SRS, or PRD document. AI will extract FR/NFR, generate test cases, and validate coverage.
                </p>
              </div>

              <!-- Feature cards -->
              <div class="grid grid-cols-3 gap-3 mt-8 mb-8">
                <div class="p-4 rounded-xl text-left" style="background-color: #161b22; border: 1px solid #30363d;">
                  <div class="w-8 h-8 rounded-lg mb-3 flex items-center justify-center" style="background-color: #1f6feb20;">
                    <svg class="w-4 h-4" style="color: #58a6ff;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                    </svg>
                  </div>
                  <h3 class="text-sm font-medium mb-1" style="color: #e6edf3;">Extract Requirements</h3>
                  <p class="text-xs" style="color: #8b949e;">AI identifies FR and NFR from your document</p>
                </div>
                <div class="p-4 rounded-xl text-left" style="background-color: #161b22; border: 1px solid #30363d;">
                  <div class="w-8 h-8 rounded-lg mb-3 flex items-center justify-center" style="background-color: #3fb95020;">
                    <svg class="w-4 h-4" style="color: #3fb950;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15a2.25 2.25 0 012.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
                    </svg>
                  </div>
                  <h3 class="text-sm font-medium mb-1" style="color: #e6edf3;">Generate Test Cases</h3>
                  <p class="text-xs" style="color: #8b949e;">Comprehensive test cases with steps and priorities</p>
                </div>
                <div class="p-4 rounded-xl text-left" style="background-color: #161b22; border: 1px solid #30363d;">
                  <div class="w-8 h-8 rounded-lg mb-3 flex items-center justify-center" style="background-color: #a371f720;">
                    <svg class="w-4 h-4" style="color: #a371f7;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                    </svg>
                  </div>
                  <h3 class="text-sm font-medium mb-1" style="color: #e6edf3;">Validate Coverage</h3>
                  <p class="text-xs" style="color: #8b949e;">Ensure test cases cover all requirements</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Messages -->
          <div v-else class="max-w-4xl mx-auto px-4 py-6 space-y-6">
            <div
              v-for="msg in store.messages"
              :key="msg.id"
              class="animate-fade-in-up"
            >
              <!-- User Message -->
              <div v-if="msg.role === 'user'" class="flex gap-3 justify-end">
                <div
                  class="max-w-[80%] px-4 py-3 rounded-2xl rounded-br-sm text-sm whitespace-pre-wrap"
                  style="background-color: #1f6feb; color: #ffffff;"
                >
                  {{ msg.content }}
                </div>
                <div class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-bold" style="background-color: #1f6feb;">
                  U
                </div>
              </div>

              <!-- Assistant Message -->
              <div v-else class="flex gap-3">
                <div
                  class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
                  style="background: linear-gradient(135deg, #7c6af4 0%, #4f46e5 100%);"
                >
                  <svg class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082" />
                  </svg>
                </div>

                <div class="flex-1 min-w-0">
                  <!-- Loading / 에이전트 진행 상황 표시 -->
                  <!-- msg.steps가 있으면: 도구 호출 단계별로 표시 (SSE 스트리밍) -->
                  <!-- msg.steps가 없으면: 기존 로딩 메시지 + 타이핑 애니메이션 (폴링 fallback) -->
                  <div v-if="msg.type === 'loading'" class="space-y-2">
                    <!-- 에이전트 진행 단계 목록 (SSE로 실시간 수신된 단계들) -->
                    <div v-if="msg.steps && msg.steps.length > 0" class="space-y-1.5">
                      <div
                        v-for="(step, idx) in msg.steps"
                        :key="idx"
                        class="flex items-start gap-2 text-sm"
                      >
                        <!-- 완료된 단계: ✅ 아이콘 -->
                        <span v-if="step.done" class="shrink-0 mt-0.5" style="color: #3fb950;">✓</span>
                        <!-- 진행 중인 단계: 깜빡이는 점 -->
                        <span v-else class="shrink-0 mt-0.5 animate-pulse-subtle" style="color: #58a6ff;">●</span>
                        <span :style="{ color: step.done ? '#8b949e' : '#e6edf3' }">{{ step.message }}</span>
                      </div>
                    </div>
                    <!-- 현재 진행 중 표시 (마지막 단계가 미완료이거나 단계가 없을 때) -->
                    <div v-if="!msg.steps || msg.steps.length === 0 || !msg.steps[msg.steps.length - 1]?.done">
                      <p v-if="!msg.steps || msg.steps.length === 0" class="text-sm animate-pulse-subtle" style="color: #8b949e;">{{ msg.content }}</p>
                      <div class="flex gap-1 py-1">
                        <div class="typing-dot w-2 h-2 rounded-full" style="background-color: #8b949e;"></div>
                        <div class="typing-dot w-2 h-2 rounded-full" style="background-color: #8b949e;"></div>
                        <div class="typing-dot w-2 h-2 rounded-full" style="background-color: #8b949e;"></div>
                      </div>
                    </div>
                  </div>

                  <!-- Plain Text -->
                  <div v-else-if="msg.type === 'text'" class="text-sm" style="color: #e6edf3;">
                    <p class="whitespace-pre-wrap">{{ msg.content }}</p>
                  </div>

                  <!-- FR/NFR Results -->
                  <div v-else-if="msg.type === 'fr_nfr'" class="space-y-4">
                    <p class="text-sm mb-3" style="color: #e6edf3;">{{ msg.content }}</p>

                    <!-- Functional Requirements -->
                    <div v-if="msg.data?.fr?.length" class="space-y-2">
                      <div class="flex items-center gap-2 mb-2">
                        <div class="w-2 h-2 rounded-full" style="background-color: #58a6ff;"></div>
                        <span class="text-xs font-semibold uppercase tracking-wider" style="color: #58a6ff;">
                          Functional Requirements ({{ msg.data.fr.length }})
                        </span>
                      </div>
                      <div
                        v-for="item in msg.data.fr"
                        :key="item.id"
                        class="rounded-lg p-3"
                        style="background-color: #161b22; border: 1px solid #30363d;"
                      >
                        <div class="flex items-start justify-between gap-2 mb-1">
                          <div class="flex items-center gap-2 min-w-0">
                            <span class="text-xs font-mono shrink-0 px-1.5 py-0.5 rounded" style="background-color: #21262d; color: #8b949e;">{{ item.id }}</span>
                            <span class="text-sm font-medium truncate" style="color: #e6edf3;">{{ item.title }}</span>
                          </div>
                          <span class="text-xs px-2 py-0.5 rounded-full border shrink-0" :class="priorityBg(item.priority)">
                            {{ item.priority }}
                          </span>
                        </div>
                        <p class="text-xs mt-1" style="color: #8b949e;">{{ item.description }}</p>
                      </div>
                    </div>

                    <!-- Non-Functional Requirements -->
                    <div v-if="msg.data?.nfr?.length" class="space-y-2">
                      <div class="flex items-center gap-2 mb-2">
                        <div class="w-2 h-2 rounded-full" style="background-color: #a371f7;"></div>
                        <span class="text-xs font-semibold uppercase tracking-wider" style="color: #a371f7;">
                          Non-Functional Requirements ({{ msg.data.nfr.length }})
                        </span>
                      </div>
                      <div
                        v-for="item in msg.data.nfr"
                        :key="item.id"
                        class="rounded-lg p-3"
                        style="background-color: #161b22; border: 1px solid #30363d;"
                      >
                        <div class="flex items-start justify-between gap-2 mb-1">
                          <div class="flex items-center gap-2 min-w-0">
                            <span class="text-xs font-mono shrink-0 px-1.5 py-0.5 rounded" style="background-color: #21262d; color: #8b949e;">{{ item.id }}</span>
                            <span class="text-sm font-medium truncate" style="color: #e6edf3;">{{ item.title }}</span>
                          </div>
                          <span class="text-xs px-2 py-0.5 rounded-full border shrink-0" :class="priorityBg(item.priority)">
                            {{ item.priority }}
                          </span>
                        </div>
                        <p class="text-xs mt-1" style="color: #8b949e;">{{ item.description }}</p>
                      </div>
                    </div>

                    <!-- Generate Test Cases Button -->
                    <div v-if="msg.actionType === 'generate'" class="pt-2">
                      <button
                        @click="handleGenerate"
                        :disabled="store.loading || store.polling"
                        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
                        style="background-color: #238636; color: #ffffff;"
                      >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15a2.25 2.25 0 012.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
                        </svg>
                        Generate Test Cases
                      </button>
                    </div>
                  </div>

                  <!-- Test Cases Results -->
                  <div v-else-if="msg.type === 'testcases'" class="space-y-3">
                    <p class="text-sm mb-3" style="color: #e6edf3;">{{ msg.content }}</p>

                    <div
                      v-for="tc in (msg.data as TestCase[])"
                      :key="tc.id"
                      class="rounded-lg overflow-hidden"
                      style="background-color: #161b22; border: 1px solid #30363d;"
                    >
                      <!-- TC Header -->
                      <button
                        @click="toggleTestCase(tc.id)"
                        class="w-full text-left px-4 py-3 flex items-start justify-between gap-2 hover:bg-white/[0.02] transition-colors"
                      >
                        <div class="flex items-start gap-2 min-w-0 flex-1">
                          <svg
                            class="w-4 h-4 shrink-0 mt-0.5 transition-transform"
                            :class="{ 'rotate-90': expandedTestCases.has(tc.id) }"
                            style="color: #8b949e;"
                            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
                          >
                            <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                          </svg>
                          <div class="min-w-0">
                            <div class="flex items-center gap-2 flex-wrap">
                              <span class="text-xs font-mono px-1.5 py-0.5 rounded shrink-0" style="background-color: #21262d; color: #8b949e;">{{ tc.id }}</span>
                              <span class="text-sm font-medium" style="color: #e6edf3;">{{ tc.title }}</span>
                            </div>
                            <p v-if="!expandedTestCases.has(tc.id)" class="text-xs mt-1 truncate" style="color: #8b949e;">{{ tc.description }}</p>
                          </div>
                        </div>
                        <div class="flex items-center gap-1.5 shrink-0">
                          <span class="text-xs px-2 py-0.5 rounded-full" style="background-color: #1f6feb20; color: #58a6ff;">{{ tc.category }}</span>
                          <span class="text-xs px-2 py-0.5 rounded-full border" :class="priorityBg(tc.priority)">{{ tc.priority }}</span>
                        </div>
                      </button>

                      <!-- TC Expanded -->
                      <div v-if="expandedTestCases.has(tc.id)" class="px-4 pb-4 pt-0 ml-6 space-y-3" style="border-top: 1px solid #21262d;">
                        <div class="pt-3">
                          <span class="text-xs font-medium uppercase tracking-wider" style="color: #484f58;">Description</span>
                          <p class="text-sm mt-1" style="color: #c9d1d9;">{{ tc.description }}</p>
                        </div>
                        <div v-if="tc.preconditions">
                          <span class="text-xs font-medium uppercase tracking-wider" style="color: #484f58;">Preconditions</span>
                          <p class="text-sm mt-1" style="color: #c9d1d9;">{{ tc.preconditions }}</p>
                        </div>
                        <div>
                          <span class="text-xs font-medium uppercase tracking-wider" style="color: #484f58;">Steps</span>
                          <ol class="mt-1 space-y-1">
                            <li v-for="(step, idx) in tc.steps" :key="idx" class="text-sm flex gap-2" style="color: #c9d1d9;">
                              <span class="font-mono text-xs shrink-0" style="color: #484f58;">{{ idx + 1 }}.</span>
                              <span>{{ step }}</span>
                            </li>
                          </ol>
                        </div>
                        <div>
                          <span class="text-xs font-medium uppercase tracking-wider" style="color: #484f58;">Expected Result</span>
                          <p class="text-sm mt-1" style="color: #c9d1d9;">{{ tc.expected_result }}</p>
                        </div>
                        <div v-if="tc.fr_nfr_ref?.length">
                          <span class="text-xs font-medium uppercase tracking-wider" style="color: #484f58;">References</span>
                          <div class="flex gap-1 mt-1 flex-wrap">
                            <span
                              v-for="ref in tc.fr_nfr_ref"
                              :key="ref"
                              class="text-xs px-2 py-0.5 rounded-full"
                              style="background-color: #21262d; color: #8b949e; border: 1px solid #30363d;"
                            >{{ ref }}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- Validate Button -->
                    <div v-if="msg.actionType === 'validate'" class="pt-2">
                      <button
                        @click="handleValidate"
                        :disabled="store.loading || store.polling"
                        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
                        style="background-color: #8957e5; color: #ffffff;"
                      >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                        </svg>
                        Validate Coverage
                      </button>
                    </div>
                  </div>

                  <!-- Validation Results -->
                  <div v-else-if="msg.type === 'validation'" class="space-y-4">
                    <p class="text-sm mb-3" style="color: #e6edf3;">{{ msg.content }}</p>

                    <!-- Coverage Score Card -->
                    <div class="rounded-lg p-4" style="background-color: #161b22; border: 1px solid #30363d;">
                      <div class="flex items-center gap-6">
                        <!-- Circle Score -->
                        <div class="text-center shrink-0">
                          <div
                            class="w-20 h-20 rounded-full flex items-center justify-center border-[3px]"
                            :class="[coverageRingColor(coveragePercent(msg.data.coverage_score)), coverageColor(coveragePercent(msg.data.coverage_score))]"
                            style="background-color: #0d1117;"
                          >
                            <span class="text-2xl font-bold">{{ coveragePercent(msg.data.coverage_score) }}%</span>
                          </div>
                          <p class="text-xs mt-1.5" style="color: #8b949e;">Coverage</p>
                        </div>

                        <!-- Bar + Status -->
                        <div class="flex-1 min-w-0">
                          <div class="flex items-center gap-2 mb-2">
                            <span class="text-sm" style="color: #c9d1d9;">Test Coverage Sufficient:</span>
                            <span
                              class="text-xs px-2 py-0.5 rounded-full font-medium"
                              :class="msg.data.is_sufficient ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'"
                            >
                              {{ msg.data.is_sufficient ? 'Yes' : 'No' }}
                            </span>
                          </div>
                          <div class="w-full rounded-full h-2" style="background-color: #21262d;">
                            <div
                              class="h-2 rounded-full transition-all duration-700"
                              :class="coverageBarColor(coveragePercent(msg.data.coverage_score))"
                              :style="{ width: coveragePercent(msg.data.coverage_score) + '%' }"
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- Feedback -->
                    <div v-if="msg.data.feedback" class="rounded-lg p-4" style="background-color: #161b22; border: 1px solid #30363d;">
                      <div class="flex items-center gap-2 mb-2">
                        <svg class="w-4 h-4" style="color: #58a6ff;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
                        </svg>
                        <span class="text-xs font-semibold uppercase tracking-wider" style="color: #58a6ff;">AI Feedback</span>
                      </div>
                      <p class="text-sm whitespace-pre-wrap" style="color: #c9d1d9;">{{ msg.data.feedback }}</p>
                    </div>

                    <!-- Missing Areas -->
                    <div
                      v-if="msg.data.missing_areas?.length"
                      class="rounded-lg p-4"
                      style="background-color: #161b22; border: 1px solid #30363d;"
                    >
                      <div class="flex items-center gap-2 mb-3">
                        <svg class="w-4 h-4" style="color: #d29922;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                        </svg>
                        <span class="text-xs font-semibold uppercase tracking-wider" style="color: #d29922;">
                          Missing Coverage Areas ({{ msg.data.missing_areas.length }})
                        </span>
                      </div>
                      <ul class="space-y-2">
                        <li
                          v-for="(area, idx) in msg.data.missing_areas"
                          :key="idx"
                          class="flex items-start gap-2 text-sm"
                          style="color: #c9d1d9;"
                        >
                          <svg class="w-4 h-4 shrink-0 mt-0.5" style="color: #d29922;" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                          </svg>
                          <span>{{ area }}</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Bottom spacer for input bar -->
            <div class="h-4"></div>
          </div>
        </div>

        <!-- Input Bar (bottom) -->
        <div
          v-if="showInputBar"
          class="shrink-0 px-4 pb-4 pt-2"
          style="background: linear-gradient(to top, #0d1117 80%, transparent);"
        >
          <div class="max-w-4xl mx-auto">
            <!-- Document type pills -->
            <div class="flex items-center gap-1.5 mb-2 px-1">
              <span class="text-xs mr-1" style="color: #484f58;">Type:</span>
              <button
                v-for="rt in requirementTypes"
                :key="rt.value"
                @click="requirementType = rt.value"
                class="text-xs px-3 py-1 rounded-full transition-colors"
                :class="requirementType === rt.value
                  ? 'bg-[#1f6feb] text-white'
                  : 'hover:bg-white/5'"
                :style="requirementType !== rt.value ? 'background-color: #21262d; color: #8b949e; border: 1px solid #30363d;' : ''"
              >
                {{ rt.label }}
              </button>
            </div>

            <!-- Input container -->
            <div
              class="relative flex items-end rounded-2xl px-3 py-2"
              style="background-color: #161b22; border: 1px solid #30363d;"
            >
              <!-- File attachment -->
              <button
                @click="handleFileAttach"
                class="p-2 rounded-lg hover:bg-white/5 transition-colors shrink-0 self-end mb-0.5"
                style="color: #8b949e;"
                title="Attach file"
              >
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
                </svg>
              </button>
              <input ref="fileInputRef" type="file" accept=".txt,.md,.doc,.docx,.pdf" class="hidden" @change="handleFileChange" />

              <!-- Textarea -->
              <textarea
                ref="textareaRef"
                v-model="requirement"
                @keydown="handleKeydown"
                placeholder="Paste your requirement, SRS, or PRD document here..."
                rows="1"
                class="flex-1 bg-transparent border-none outline-none resize-none text-sm py-2 px-2 max-h-40 placeholder:text-[#484f58]"
                style="color: #e6edf3; field-sizing: content;"
              />

              <!-- Send button -->
              <button
                @click="handleSubmit"
                :disabled="!canSend"
                class="p-2 rounded-lg transition-all shrink-0 self-end mb-0.5"
                :class="canSend ? 'hover:brightness-110' : 'opacity-30 cursor-not-allowed'"
                :style="canSend ? 'background-color: #1f6feb; color: #ffffff;' : 'background-color: #30363d; color: #8b949e;'"
              >
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
                </svg>
              </button>
            </div>

            <p class="text-center text-xs mt-2" style="color: #30363d;">
              Press Enter to send, Shift+Enter for new line
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Toast -->
    <Transition
      enter-active-class="transition-all duration-300"
      enter-from-class="opacity-0 translate-y-4"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-300"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-4"
    >
      <div v-if="store.error" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
        <div
          class="flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl"
          style="background-color: #3d1f1f; border: 1px solid #6e3630; color: #f97583;"
        >
          <svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <span class="text-sm">{{ store.error }}</span>
          <button @click="store.error = null" class="p-1 hover:bg-white/10 rounded transition-colors">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>
