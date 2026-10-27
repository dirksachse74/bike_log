import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The git commit the screens were built from. Settings compares it with the running backend's commit,
// so a stale frontend/dist (forgot `npm run build`) or an old app still running is visible.
function gitCommit(): string {
  try {
    return execSync('git rev-parse --short=7 HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() || 'unknown'
  } catch {
    return 'unknown'
  }
}
const COMMIT = gitCommit()
// The version number lives in one place: backend/bikelog/__init__.py (see scripts/release.py).
const VERSION = /__version__ = "([^"]+)"/.exec(readFileSync(new URL('../backend/bikelog/__init__.py', import.meta.url), 'utf8'))?.[1] ?? 'unknown'

// The packaged backend serves dist/ at "/" on 127.0.0.1:<port>.
// In dev, /api is proxied to a locally running backend (BIKELOG_DEV_TOKEN=dev).
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'bikelog-build-info',
      generateBundle() {
        this.emitFile({ type: 'asset', fileName: 'build-info.json', source: JSON.stringify({ commit: COMMIT, version: VERSION, built_at: new Date().toISOString() }) })
      },
    },
  ],
  define: { __BUILD_COMMIT__: JSON.stringify(COMMIT), __APP_VERSION__: JSON.stringify(VERSION) },
  base: '/',
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
})
