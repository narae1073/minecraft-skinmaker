import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Second agent/worktree: VITE_API_TARGET=http://localhost:8002 npm run dev
const apiTarget = globalThis.process?.env?.VITE_API_TARGET || 'http://localhost:8001'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/static': {
        target: apiTarget,
        changeOrigin: true,
      }
    }
  }
})