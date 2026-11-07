import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the UI runs on :5173 and forwards /api to the backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
