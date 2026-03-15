import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  modules: ['@pinia/nuxt'],
  devtools: { enabled: true },
  devServer: {
    port: 3482
  },
  runtimeConfig: {
    public: {
      apiBase: 'http://localhost:3480/api/v1'
    }
  },
  css: ['~/assets/css/main.css'],
  vite: {
    plugins: [
      tailwindcss()
    ]
  }
})
