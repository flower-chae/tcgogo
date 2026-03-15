/**
 * Nuxt 4 설정 파일
 * =================
 * Nuxt 앱의 전체 동작을 설정하는 핵심 파일이다.
 * 여기서 설정한 내용이 빌드, 개발 서버, 런타임 전체에 영향을 준다.
 *
 * Nuxt의 역할: Vue.js 위에 구축된 프레임워크로,
 * - 페이지 라우팅 (pages/ 폴더 기반 자동 라우팅)
 * - SSR (Server-Side Rendering) 지원
 * - 자동 import (ref, computed 등을 import 없이 사용 가능)
 * - 모듈 시스템 (Pinia, UI 라이브러리 등 플러그인 관리)
 * 을 자동으로 처리해준다.
 */

// Tailwind CSS를 Vite 플러그인으로 가져온다
// Vite: Nuxt가 내부적으로 사용하는 빌드 도구 (번들링, HMR 등)
// Tailwind: 유틸리티 기반 CSS 프레임워크 (class="flex gap-2 p-4" 같은 방식)
import tailwindcss from '@tailwindcss/vite'

// defineNuxtConfig(): Nuxt가 자동으로 제공하는 함수 (import 불필요)
// 이 함수로 감싸야 타입 지원과 자동완성이 동작한다
export default defineNuxtConfig({
  // Nuxt 4 호환성 날짜: 이 날짜 이후의 breaking change를 적용하겠다는 의미
  // Nuxt가 버전 업데이트 시 하위 호환성을 유지하기 위해 사용하는 메커니즘
  compatibilityDate: '2025-01-01',

  // -----------------------------------------------------------------------
  // 모듈 등록
  // -----------------------------------------------------------------------
  // Nuxt 모듈: 앱에 기능을 추가하는 플러그인 시스템
  // '@pinia/nuxt': Pinia(상태 관리 라이브러리)를 Nuxt에 통합
  //   → stores/ 폴더의 스토어를 자동으로 인식
  //   → 페이지에서 useTestcaseStore() 같은 함수를 바로 사용 가능
  modules: ['@pinia/nuxt'],

  // Vue DevTools 활성화 (브라우저에서 컴포넌트 구조, 상태를 실시간 확인 가능)
  devtools: { enabled: true },

  // -----------------------------------------------------------------------
  // 개발 서버 설정
  // -----------------------------------------------------------------------
  devServer: {
    port: 3482  // npm run dev 시 http://localhost:3482 에서 접근
  },

  // -----------------------------------------------------------------------
  // 런타임 설정 (runtimeConfig)
  // -----------------------------------------------------------------------
  // 런타임에 접근 가능한 설정값. 환경변수로 오버라이드 가능.
  //
  // public: 클라이언트(브라우저)와 서버 양쪽에서 접근 가능
  // (public이 아닌 값은 서버에서만 접근 가능 → API 키 등에 사용)
  //
  // 사용법: const config = useRuntimeConfig()
  //         config.public.apiBase → 'http://localhost:3480/api/v1'
  //
  // 환경변수 오버라이드: NUXT_PUBLIC_API_BASE=https://prod.com/api/v1
  //   → Nuxt가 자동으로 runtimeConfig.public.apiBase를 오버라이드
  runtimeConfig: {
    public: {
      apiBase: 'http://localhost:3480/api/v1'  // 백엔드 API 기본 주소
    }
  },

  // -----------------------------------------------------------------------
  // 글로벌 CSS
  // -----------------------------------------------------------------------
  // 모든 페이지에 적용되는 CSS 파일
  // ~/는 프로젝트 루트(frontend/app/)를 가리킨다
  // main.css에는 다크 테마 기본 스타일과 애니메이션이 정의되어 있다
  css: ['~/assets/css/main.css'],

  // -----------------------------------------------------------------------
  // Vite 설정
  // -----------------------------------------------------------------------
  // Vite: Nuxt가 사용하는 빌드 도구
  // 여기서 Vite 플러그인을 추가할 수 있다
  vite: {
    plugins: [
      // Tailwind CSS를 Vite 플러그인으로 등록
      // 이렇게 하면 .vue 파일에서 Tailwind 클래스를 바로 사용 가능
      // 예: class="flex items-center gap-2 bg-gray-800 rounded-lg p-4"
      tailwindcss()
    ]
  }
})
