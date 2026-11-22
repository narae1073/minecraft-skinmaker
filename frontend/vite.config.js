import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Second agent/worktree: VITE_API_TARGET=http://localhost:8002 npm run dev
const apiTarget = globalThis.process?.env?.VITE_API_TARGET || 'http://localhost:8001'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
  },
  build: {
    rollupOptions: {
      output: {
        // three.js is only needed once a result card/editor opens; keep it out of
        // the entry chunk so the first paint stays small.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('three') || id.includes('@react-three')) return 'three'
          if (id.includes('react') || id.includes('scheduler')) return 'react'
          return undefined
        },
      },
    },
  },
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
