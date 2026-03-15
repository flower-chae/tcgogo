# 프론트엔드 디자인 지시 가이드

## 이번 프로젝트에서 디자인이 잘 나온 이유

### 1. "레퍼런스"를 명시했다
> "ChatGPT / Gemini / Claude 의 채팅화면에서 진행하게 해줘"

이 한 문장이 결정적이었다. 추상적인 "모던하게"가 아니라, **누구나 아는 서비스를 레퍼런스로 지정**하니 방향이 즉시 확정되었다.

### 2. UI 컴포넌트 라이브러리에 의존하지 않았다
Nuxt UI 컴포넌트(UCard, UButton 등)를 사용했을 때 스타일이 깨졌다. 결국 **Tailwind CSS + inline style로 직접 구현**하니 의도한 대로 나왔다.

이유: UI 라이브러리는 버전 호환성, 테마 충돌, SSR 이슈 등 변수가 많다. 특히 빠른 프로토타입에서는 직접 스타일링이 더 안정적이다.

### 3. 색상 시스템을 구체적으로 지정했다
GitHub Dark 테마의 색상 코드를 직접 사용했다:
```
배경:       #0d1117
사이드바:    #161b22
테두리:      #30363d
본문 텍스트: #e6edf3
보조 텍스트: #8b949e
비활성:      #484f58
파란색 강조: #1f6feb
보라색 강조: #7c6af4
```

모호한 "다크 테마"가 아니라 **구체적인 색상 팔레트**가 있었기에 일관된 디자인이 나왔다.

---

## 앞으로 프론트엔드를 지시할 때 사용할 템플릿

### 필수 포함 항목

```markdown
## 1. 레퍼런스 (가장 중요)
- "XXX 서비스의 YYY 화면처럼 만들어줘"
- 예: "Notion의 사이드바 + ChatGPT의 채팅 영역"
- 예: "Linear의 이슈 목록 UI처럼"
- 예: "Vercel 대시보드 스타일로"
- 스크린샷이 있으면 더 좋다

## 2. 테마/색상
- 다크/라이트 선택
- 구체적 색상이 있으면 명시 (예: "GitHub Dark 색상", "Tailwind Slate 계열")
- 없으면: "GitHub Dark 스타일" 또는 "Vercel 스타일" 같이 레퍼런스로 대체 가능

## 3. 레이아웃 구조
- 사이드바 유무, 위치, 너비
- 상단바 유무
- 메인 콘텐츠 영역 구성
- 예: "왼쪽 사이드바(280px) + 메인 영역 + 하단 고정 입력바"

## 4. 핵심 인터랙션
- 데이터 흐름 (사용자가 무엇을 입력 → 어떤 결과가 나오는지)
- 로딩/에러 상태 처리 방법
- 예: "입력 → AI 처리 중 타이핑 애니메이션 → 결과 카드로 표시"

## 5. 기술 제약
- 사용할 프레임워크 (Nuxt, Next, React 등)
- CSS 방식: "Tailwind 직접 사용, UI 라이브러리 쓰지 말 것" ← 권장
- 반응형 필요 여부
```

### 실제 지시 예시 (좋은 예)

```
채팅 기반 UI를 만들어줘.

레퍼런스: ChatGPT의 채팅 화면
- 왼쪽 사이드바: 대화 이력, 날짜별 그룹핑, New Chat 버튼
- 메인: 채팅 메시지 (유저 오른쪽 파란 말풍선, AI 왼쪽 아바타+텍스트)
- 하단: 고정 입력바 (파일 첨부 버튼 + textarea + 전송 버튼)
- 다크 테마, GitHub Dark 색상 (#0d1117 배경)
- Tailwind CSS 직접 사용, UI 라이브러리 컴포넌트 쓰지 말 것
- Enter로 전송, Shift+Enter로 줄바꿈
```

### 피해야 할 지시 (나쁜 예)

```
❌ "모던하게 만들어줘" → 너무 모호함
❌ "이쁘게 해줘" → 기준이 없음
❌ "대시보드 만들어줘" → 어떤 종류의 대시보드?
❌ "Nuxt UI 컴포넌트 활용해서" → 호환성 문제 위험
```

---

## 기술적 팁

### Tailwind CSS 직접 사용이 안정적인 이유
- UI 라이브러리(Nuxt UI, Vuetify 등)는 버전 업데이트 시 스타일 깨짐 위험
- SSR 환경에서 스타일 미적용 문제 빈번
- Tailwind + inline style 조합이 가장 예측 가능

### inline style을 섞어 쓰는 이유
```html
<!-- Tailwind: 레이아웃/간격 -->
<!-- inline style: 색상/테두리 등 구체적 값 -->
<div class="flex items-center gap-2 px-3 py-2 rounded-lg"
     style="background-color: #161b22; border: 1px solid #30363d;">
```
- Tailwind 클래스: `flex`, `gap-2`, `px-3` 등 레이아웃 담당
- inline style: `#161b22` 같은 커스텀 색상 담당
- 이렇게 하면 Tailwind 빌드 문제와 무관하게 색상이 항상 적용됨

### SVG 아이콘 직접 사용
- 아이콘 라이브러리 의존성 줄이기 위해 SVG를 직접 inline으로 삽입
- heroicons.com 에서 SVG 복사해서 사용하면 편리
- 단, 아이콘이 많아지면 아이콘 라이브러리(@iconify-json/lucide 등) 사용도 OK

### 애니메이션으로 완성도 높이기
```css
/* 메시지 등장 애니메이션 */
@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 타이핑 인디케이터 */
@keyframes typing-dot {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-4px); }
}
```
- 작은 애니메이션 몇 개만으로도 "모던함"이 크게 향상됨
- fade-in, typing dots, hover transition 정도면 충분

---

## UI 효과 용어 사전

Claude Code에 작업을 지시할 때 사용할 수 있는 효과 이름과 의미.

### 효과 종류

| 용어 | 의미 | 사용 예시 |
|------|------|----------|
| **text shimmer** | 텍스트 위로 빛이 천천히 흘러가는 효과. 회색 텍스트에 밝은 빛이 왼쪽→오른쪽으로 지나감. Claude Code의 "Inferring..." 느낌. | "로딩 텍스트에 text shimmer 적용해줘" |
| **skeleton shimmer** | 회색 박스(뼈대) 위로 빛이 지나가는 효과. 콘텐츠 로딩 전 자리 표시. | "데이터 로딩 전에 skeleton shimmer 보여줘" |
| **pulse** | 요소 전체가 부드럽게 깜빡이는 효과. 투명도(opacity)가 반복 변화. | "로딩 중에 pulse 효과 넣어줘" |
| **fade-in** | 투명→불투명으로 서서히 나타나는 효과. | "메시지가 fade-in으로 나타나게 해줘" |
| **fade-in-up** | 아래에서 위로 올라오며 나타나는 효과. | "카드가 fade-in-up으로 등장하게 해줘" |
| **typing dots** | ●●● 점 3개가 순서대로 튀어오르는 효과. AI가 응답 중일 때 사용. | "AI 응답 대기 시 typing dots 보여줘" |
| **gradient wave** | 여러 색상이 물결처럼 텍스트를 흐르는 효과. 화려한 버전. | "제목에 gradient wave 효과 넣어줘" |
| **hover transition** | 마우스를 올리면 부드럽게 색이 변하는 효과. | "버튼에 hover transition 넣어줘" |

### 이 프로젝트에서 사용 중인 효과

```
1. text shimmer — 에이전트 처리 중 상태 메시지
   "요구사항을 분석하고 있습니다..." ← 빛이 왼→오로 흐름
   지시법: "shimmer 효과로 해줘" 또는 "text shimmer 적용해줘"

2. typing dots — text shimmer 아래에 ●●● 점 3개 애니메이션
   지시법: "typing dots 추가해줘"

3. fade-in-up — 새 채팅 메시지가 아래에서 올라오며 등장
   지시법: "fade-in-up으로 나타나게 해줘"

4. pulse — 처리 중 텍스트가 부드럽게 깜빡임 (shimmer 적용 전 사용했던 효과)
   지시법: "pulse 효과 넣어줘"
```

### Claude Code에 효과 지시하는 방법

```markdown
# 좋은 예 (구체적)

"로딩 메시지에 text shimmer 효과 적용해줘.
 회색 톤(#6e7681 → #e6edf3)으로, 왼→오 방향, 3.5초 주기"

"버튼 hover 시 brightness-110으로 transition 넣어줘"

"새 메시지 등장 시 fade-in-up 0.3초로 해줘"

# 나쁜 예 (모호함)

"이쁘게 움직이게 해줘"          → 어떤 효과?
"반짝거리게"                   → shimmer? pulse? 다른 거?
"뭔가 효과 넣어줘"              → 기준이 없음
```

### text shimmer 구현 원리 (참고용)

```css
/* 핵심 원리: 텍스트를 클리핑 마스크로 사용하여 배경 그라데이션을 보여준다 */

@keyframes shimmer-glow {
  0% { background-position: 200% center; }    /* 빛이 오른쪽에서 시작 */
  100% { background-position: 0% center; }    /* 왼쪽으로 이동 완료 */
}

/* 적용 방법 (인라인 style 권장 — Tailwind가 덮어쓰는 문제 방지) */
style="
  background: linear-gradient(90deg,
    #6e7681 0%,      /* 기본 회색 */
    #6e7681 35%,     /* 회색 유지 */
    #e6edf3 50%,     /* 밝은 빛 포인트 */
    #6e7681 65%,     /* 회색 복귀 */
    #6e7681 100%     /* 회색 끝 */
  );
  background-size: 200% auto;
  -webkit-background-clip: text;         /* 텍스트 모양으로 배경 자르기 */
  background-clip: text;
  -webkit-text-fill-color: transparent;  /* 기본 텍스트 색 숨기기 */
  animation: shimmer-glow 3.5s linear infinite;
"
```

**주의: CSS 클래스 대신 인라인 style로 적용해야 한다.**
Tailwind 4 + Vite 환경에서 `background-clip: text`가 클래스로 적용 시
Tailwind에 의해 덮어씌워질 수 있다. 인라인 style은 항상 최우선 적용.
