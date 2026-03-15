# Frontend 코드 스터디 가이드

> Nuxt 4 + Pinia + Tailwind 프론트엔드를 이해하기 위한 학습 문서

---

## 1. 파일 구조 (읽는 순서)

```
frontend/
├── nuxt.config.ts              ① 설정 파일 (모든 것의 시작점)
├── package.json                   패키지 의존성 목록
├── app/
│   ├── app.vue                 ② 최상위 컴포넌트 (루트 레이아웃)
│   ├── assets/
│   │   └── css/main.css        ③ 글로벌 CSS (다크 테마, 애니메이션)
│   ├── stores/
│   │   └── testcase.ts         ④ Pinia 스토어 (데이터 + API 호출)
│   └── pages/
│       └── index.vue           ⑤ 메인 페이지 (UI 전체)
```

**읽는 순서: ① → ② → ③ → ④ → ⑤**

---

## 2. Vue 3 기초 개념 (이것만 알면 코드가 읽힌다)

### .vue 파일 구조

```vue
<!-- 모든 .vue 파일은 3개 블록으로 구성된다 -->

<script setup lang="ts">
// JavaScript/TypeScript 로직 (데이터, 함수, 이벤트 처리)
// "setup"이 붙으면 Vue 3의 Composition API를 사용한다는 의미
</script>

<template>
<!-- HTML 템플릿 (화면에 보이는 부분) -->
<!-- Vue 디렉티브 (v-if, v-for, @click 등)를 사용하여 동적 렌더링 -->
</template>

<style>
/* CSS 스타일 (이 프로젝트에서는 Tailwind 클래스를 사용하므로 거의 비어있음) */
</style>
```

### 반응형 데이터 (ref, computed)

```typescript
// ref(): 변경을 감지하는 데이터. 값이 바뀌면 화면이 자동 업데이트됨.
const count = ref(0)       // count.value = 0
count.value++              // count.value = 1 → 화면에 1이 표시됨

// computed(): 다른 데이터에서 파생된 값. 의존하는 데이터가 바뀌면 자동 재계산.
const doubled = computed(() => count.value * 2)  // count가 바뀌면 자동 갱신

// ref vs reactive:
// ref: 단일 값 (문자열, 숫자, 배열 등)
// reactive: 객체 전체를 반응형으로 만듦 (Pinia의 state가 이 방식)
```

### 템플릿 디렉티브 (v-if, v-for, @click 등)

```vue
<template>
  <!-- v-if: 조건부 렌더링 (조건이 false면 DOM에서 아예 제거됨) -->
  <div v-if="isLoggedIn">환영합니다</div>
  <div v-else>로그인해주세요</div>

  <!-- v-for: 반복 렌더링 (배열의 각 요소를 반복) -->
  <!-- :key는 필수: Vue가 각 요소를 구분하기 위한 고유 식별자 -->
  <div v-for="item in items" :key="item.id">
    {{ item.name }}
  </div>

  <!-- @click: 이벤트 핸들러 (@는 v-on:의 축약형) -->
  <button @click="handleClick">클릭</button>
  <button @click="count++">카운터: {{ count }}</button>

  <!-- :class: 동적 클래스 바인딩 (:는 v-bind:의 축약형) -->
  <div :class="isActive ? 'bg-blue-500' : 'bg-gray-500'">동적 색상</div>
  <div :class="{ 'text-bold': isBold, 'text-red': isError }">조건부 클래스</div>

  <!-- :style: 동적 인라인 스타일 -->
  <div :style="{ width: percentage + '%' }">프로그레스 바</div>

  <!-- {{ }}: 데이터 바인딩 (JavaScript 값을 텍스트로 표시) -->
  <p>{{ message }}</p>
  <p>{{ items.length }}개의 항목</p>

  <!-- v-model: 양방향 데이터 바인딩 (입력값 ↔ 변수 자동 동기화) -->
  <input v-model="searchText" />
  <!-- searchText가 바뀌면 input이 업데이트되고, input을 수정하면 searchText가 업데이트됨 -->
</template>
```

### 라이프사이클 (onMounted, watch)

```typescript
// onMounted(): 컴포넌트가 화면에 처음 나타날 때 1회 실행
// → API 초기 데이터 로드에 사용
onMounted(() => {
  store.fetchSessions()  // 페이지 로드 시 세션 목록 가져오기
})

// watch(): 특정 값이 변경될 때마다 실행
// → 데이터 변경에 따른 부수 효과(side effect) 처리
watch(() => store.messages.length, () => {
  scrollToBottom()  // 메시지가 추가되면 자동 스크롤
})
```

---

## 3. 이 프로젝트의 데이터 흐름

```
┌──────────────────────────────────────────────────────┐
│                    pages/index.vue                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   사이드바    │  │   채팅 영역   │  │   입력 바    │ │
│  │  (세션 목록)  │  │  (메시지들)   │  │  (textarea)  │ │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                │                  │         │
│         ▼                ▼                  ▼         │
│  ┌────────────────────────────────────────────────┐   │
│  │         stores/testcase.ts (Pinia 스토어)        │   │
│  │                                                  │   │
│  │  state:                                          │   │
│  │    sessions[]        ← fetchSessions()           │   │
│  │    currentSession    ← fetchSession(id)          │   │
│  │    messages[]        ← addUserMessage()          │   │
│  │    loading           ← API 호출 중 true          │   │
│  │    polling            ← 2초마다 상태 확인         │   │
│  │                                                  │   │
│  │  actions (API 호출):                              │   │
│  │    extractFrNfr()    → POST /extract-fr-nfr      │   │
│  │    generateFromSession() → POST /{id}/generate   │   │
│  │    validateSession()  → POST /{id}/validate      │   │
│  └──────────────────────┬────────────────────────┘   │
│                          │                            │
└──────────────────────────┼────────────────────────────┘
                           ▼
                 Backend API (localhost:3480)
```

---

## 4. index.vue 구조 맵 (765줄을 영역별로 나눠서 읽기)

### script 영역 (line 1~208)

```
line   1-14   : import + 기본 변수 선언 (ref)
line  16-20   : 요구사항 타입 선택지 (Requirement/SRS/PRD)
line  23-48   : groupSessionsByDate() — 사이드바 날짜별 그룹핑
line  50      : sessionGroups (computed) — 정렬된 세션을 날짜 그룹으로 변환
line  53-97   : 유틸리티 함수들 (truncate, priorityColor, coveragePercent 등)
line  99-106  : toggleTestCase() — TC 카드 펼치기/접기
line 108-124  : scrollToBottom() + watch — 새 메시지 시 자동 스크롤
line 126-145  : handleSubmit(), handleKeydown() — 입력 처리
line 147-165  : handleGenerate(), handleValidate(), selectSession() — 액션 버튼
line 167-207  : startNewChat(), 파일 첨부, canSend, onMounted — 기타 기능
```

### template 영역 (line 210~765) — 화면 레이아웃

```
전체 구조:
┌─────────────────────────────────────────┐
│ ┌───────────┐ ┌───────────────────────┐ │
│ │           │ │ Top Bar (상태 뱃지)    │ │
│ │  Sidebar  │ ├───────────────────────┤ │
│ │ (세션목록) │ │                       │ │
│ │           │ │  Chat Area            │ │
│ │ line      │ │  (메시지 또는 웰컴)    │ │
│ │ 213-265   │ │                       │ │
│ │           │ │  line 306-661         │ │
│ │           │ ├───────────────────────┤ │
│ │           │ │ Input Bar (입력창)     │ │
│ │           │ │ line 663-734          │ │
│ └───────────┘ └───────────────────────┘ │
│                                         │
│ Error Toast (하단 중앙) line 739-763    │
└─────────────────────────────────────────┘
```

### 메시지 타입별 렌더링 분기 (line 362~656)

```vue
<!-- msg.type에 따라 다른 UI를 렌더링한다 -->

v-if="msg.role === 'user'"          → 사용자 메시지 (오른쪽, 파란 배경)
v-else                              → AI 메시지 (왼쪽, 아이콘)
  ├─ msg.type === 'loading'         → 타이핑 인디케이터 (●●●)
  ├─ msg.type === 'text'            → 일반 텍스트
  ├─ msg.type === 'fr_nfr'          → FR/NFR 카드 목록 + "Generate" 버튼
  ├─ msg.type === 'testcases'       → TC 카드 목록 (펼치기/접기) + "Validate" 버튼
  └─ msg.type === 'validation'      → 커버리지 원형 점수 + 피드백 + 누락 영역
```

---

## 5. 핵심 패턴 상세

### 패턴 1: 비동기 작업 + 폴링

```
사용자가 "분석" 클릭
    │
    ▼
handleSubmit()                         ← index.vue
    │
    ▼
store.extractFrNfr(text, type)         ← testcase.ts
    │
    ├─ addUserMessage(text)            ← 채팅에 사용자 메시지 추가
    ├─ _addLoadingMsg("Analyzing...")  ← 채팅에 로딩(●●●) 추가
    ├─ $fetch(POST /extract-fr-nfr)    ← 백엔드 API 호출 → 202 즉시 응답
    ├─ currentSession = {...}          ← 임시 세션 설정
    └─ startPolling(id, 'extracted')   ← 폴링 시작
         │
         └─ 2초마다 반복:
              fetchSession(id) → status 확인
              ├─ 'extracted'  → _replaceLoadingMsg(FR/NFR 결과)  ← ●●● → 카드 교체
              ├─ 'failed'     → _replaceLoadingMsg(에러 메시지)
              └─ 그 외        → 계속 폴링
```

### 패턴 2: 메시지 교체 (Loading → Result)

```typescript
// 1. API 호출 직후: 로딩 메시지 추가
this._addLoadingMsg('Analyzing your document...')
// messages: [..., {type: 'loading', content: 'Analyzing...'}]
// 화면: 사용자 메시지 → ●●● Analyzing...

// 2. 폴링으로 완료 감지: 로딩 메시지를 결과로 교체
this._replaceLoadingMsg({
  type: 'fr_nfr',
  content: 'Here are the extracted FR/NFR:',
  data: session.fr_nfr,
  actionType: 'generate'
})
// messages: [..., {type: 'fr_nfr', data: {...}, actionType: 'generate'}]
// 화면: 사용자 메시지 → FR/NFR 카드들 → [Generate Test Cases] 버튼
```

### 패턴 3: 조건부 액션 버튼

```vue
<!-- FR/NFR 메시지 하단에 "Generate" 버튼 표시 조건 -->
<div v-if="msg.actionType === 'generate'">
  <button @click="handleGenerate">Generate Test Cases</button>
</div>

<!-- TC 메시지 하단에 "Validate" 버튼 표시 조건 -->
<div v-if="msg.actionType === 'validate'">
  <button @click="handleValidate">Validate Coverage</button>
</div>
```

```
actionType 설정 로직:
- FR/NFR 메시지: TC가 아직 없으면 'generate', 있으면 undefined (버튼 숨김)
- TC 메시지: validation이 아직 없으면 'validate', 있으면 undefined
→ 이미 다음 단계를 완료했으면 버튼을 숨긴다
```

### 패턴 4: 동적 스타일링 (Tailwind + 인라인)

```vue
<!-- 이 프로젝트의 스타일링 전략 -->

<!-- 1. 레이아웃/간격: Tailwind 클래스 -->
<div class="flex items-center gap-2 px-4 py-3 rounded-lg">

<!-- 2. 색상/테두리: 인라인 style (GitHub Dark 팔레트) -->
<div style="background-color: #161b22; border: 1px solid #30363d; color: #e6edf3;">

<!-- 3. 동적 조건: :class 바인딩 -->
<span :class="{
  'bg-green-500/10 text-green-400': status === 'completed',
  'bg-red-500/10 text-red-400': status === 'failed'
}">

<!-- 왜 이렇게 나눠서 쓰는가?
     - Tailwind: 레이아웃은 클래스가 직관적 (flex, gap, padding)
     - 인라인: 정확한 hex 색상은 Tailwind 기본 팔레트에 없으므로
     - :class: 상태에 따라 바뀌는 스타일은 동적 바인딩으로 -->
```

---

## 6. Tailwind CSS 자주 쓰이는 클래스 사전

### 레이아웃

```
flex              → display: flex (가로 배치)
flex-col          → flex-direction: column (세로 배치)
flex-1            → flex: 1 (남은 공간 차지)
items-center      → align-items: center (세로 중앙 정렬)
justify-between   → justify-content: space-between (양쪽 끝 정렬)
justify-end       → justify-content: flex-end (오른쪽 정렬)
gap-2             → gap: 0.5rem (8px 간격)
grid grid-cols-3  → 3열 그리드
```

### 크기/여백

```
w-8 h-8           → width: 2rem, height: 2rem (32px)
w-full            → width: 100%
max-w-4xl         → max-width: 56rem (896px)
p-4               → padding: 1rem (16px, 상하좌우 전체)
px-4              → padding-left + padding-right (좌우만)
py-2              → padding-top + padding-bottom (상하만)
mt-4              → margin-top: 1rem
mb-2              → margin-bottom: 0.5rem
```

### 텍스트

```
text-sm           → font-size: 0.875rem (14px)
text-xs           → font-size: 0.75rem (12px)
text-2xl          → font-size: 1.5rem (24px)
font-medium       → font-weight: 500
font-bold         → font-weight: 700
font-mono         → monospace 글꼴 (코드용)
truncate          → 텍스트 넘치면 ... 으로 자름
whitespace-pre-wrap → 줄바꿈 유지
```

### 모양

```
rounded-lg        → border-radius: 0.5rem (8px)
rounded-full      → border-radius: 9999px (완전한 원)
rounded-2xl       → border-radius: 1rem (16px)
border            → border: 1px solid
shadow-2xl        → 큰 그림자
overflow-hidden   → 넘치는 내용 숨기기
```

### 상태

```
hover:bg-white/5  → 마우스 올리면 흰색 5% 투명도 배경
disabled:opacity-50  → 비활성화 시 50% 투명
transition-colors → 색상 변경 시 부드러운 전환 (0.15s)
transition-all    → 모든 속성 변경 시 부드러운 전환
```

### 색상 패턴

```
bg-blue-500/10    → 파란색 배경 10% 투명도 (반투명 뱃지)
text-green-400    → 초록색 텍스트
border-red-500/20 → 빨간색 테두리 20% 투명도
bg-white/5        → 흰색 5% (거의 투명, 호버 효과용)
```

---

## 7. 수정하고 싶을 때 참고

### 새 메시지 타입 추가하고 싶을 때

```
1. stores/testcase.ts
   - ChatMessage 인터페이스의 type에 새 타입 추가
   - 폴링 로직에 새 상태 처리 추가

2. pages/index.vue
   - template의 메시지 렌더링 분기에 v-else-if 추가
   - 새 타입에 맞는 UI 카드 구현
```

### 색상 테마 변경하고 싶을 때

```
1. assets/css/main.css
   - html, body의 background-color, color 변경

2. pages/index.vue
   - style="..." 부분의 hex 색상 변경
   - 주요 색상:
     #0d1117 (메인 배경) → 바꾸면 전체 분위기 변경
     #161b22 (카드 배경) → 사이드바, 카드 색상
     #30363d (테두리)    → 구분선 색상
     #1f6feb (파란 액센트) → 버튼, 링크 색상
```

### 새 API 연결하고 싶을 때

```
1. stores/testcase.ts
   - actions에 새 함수 추가
   - $fetch로 API 호출
   - state 업데이트

2. pages/index.vue
   - 버튼에 @click으로 새 함수 연결
```

---

## 8. 개발 도구 활용

### Vue DevTools (브라우저 확장)

```
Chrome에서 F12 → Vue 탭

확인 가능한 것:
- 컴포넌트 트리 (어떤 컴포넌트가 어떤 데이터를 가지고 있는지)
- Pinia 스토어 상태 (sessions, messages, loading 등 실시간 확인)
- 이벤트 흐름 (어떤 이벤트가 발생했는지)
```

### 브라우저 DevTools

```
F12 → Network 탭:
  - API 호출 확인 (어떤 URL로, 어떤 응답이 왔는지)
  - 폴링 요청 확인 (2초마다 GET 요청이 반복되는지)

F12 → Console 탭:
  - JavaScript 에러 확인
  - console.log() 출력 확인

F12 → Elements 탭:
  - HTML 구조 확인
  - Tailwind 클래스가 어떤 CSS로 변환되었는지 확인
  - 인라인 style 값 수정하여 실시간 미리보기
```
