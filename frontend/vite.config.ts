import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The Vite dev server proxies /api to the FastAPI backend on :8000,
// so the frontend can call the same origin during development.
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
