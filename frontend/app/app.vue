<!--
  app.vue: Nuxt 앱의 최상위 컴포넌트 (루트 레이아웃)
  =============================================
  모든 페이지가 이 컴포넌트 안에서 렌더링된다.

  <NuxtPage />는 pages/ 폴더의 .vue 파일을 URL에 따라 자동으로 렌더링한다.
  예: pages/index.vue → http://localhost:3482/
      pages/about.vue → http://localhost:3482/about (있다면)

  현재는 단일 페이지(SPA 스타일)이므로 pages/index.vue만 사용한다.

  여기에 공통 레이아웃(헤더, 푸터 등)을 추가하면 모든 페이지에 적용된다.
  예:
    <template>
      <header>공통 헤더</header>
      <NuxtPage />
      <footer>공통 푸터</footer>
    </template>
-->
<template>
  <NuxtPage />
</template>
