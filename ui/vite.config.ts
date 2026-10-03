/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import sirv from 'sirv'
import { defineConfig, loadEnv, type Plugin } from 'vite'

// Without VITE_API_URL the app runs on mocks (public/mock) and the dev server serves poc/store at /static,
// the same prefix the API uses. With VITE_API_URL, /soil, /static and /health are proxied to the API instead.
const STORE = path.resolve(import.meta.dirname, '../poc/store')

function serveStore(): Plugin {
  const handler = sirv(STORE, { dev: true, etag: true })
  const mount = (server: { middlewares: { use: (p: string, h: typeof handler) => unknown } }) => {
    server.middlewares.use('/static', handler)
  }
  return { name: 'serve-poc-store', configureServer: mount, configurePreviewServer: mount }
}

export default defineConfig(({ mode }) => {
  const apiUrl = loadEnv(mode, process.cwd(), 'VITE_').VITE_API_URL
  const proxy = apiUrl
    ? Object.fromEntries(['/soil', '/static', '/health'].map((p) => [p, { target: apiUrl, changeOrigin: true }]))
    : undefined
  return {
    plugins: [react(), tailwindcss(), ...(apiUrl ? [] : [serveStore()])],
    server: { proxy, fs: { allow: ['..'] } },
    test: { environment: 'node' },
  }
})
