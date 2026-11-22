import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend runs on port 8000 (see README). /api and /ws are forwarded to it.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
