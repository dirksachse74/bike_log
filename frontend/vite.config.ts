import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The packaged backend serves dist/ at "/" on 127.0.0.1:<port>.
// In dev, /api is proxied to a locally running backend (BIKELOG_DEV_TOKEN=dev).
export default defineConfig({
  plugins: [react()],
  base: process.env.BIKELOG_BASE ?? '/',
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
})
