import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            const normalized = id.replaceAll(String.fromCharCode(92), '/')
            if (normalized.includes('/node_modules/.pnpm/echarts@')) return 'report-charts'
            if (normalized.includes('/node_modules/.pnpm/zrender@')) return 'report-charts'
            return undefined
          },
        },
      },
    },
    server: {
      // OIDC 回调使用 127.0.0.1，显式监听 IPv4，避免 Windows 下仅绑定 ::1。
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': {
          target: backendTarget,
          ws: true,
        },
        '/auth': backendTarget,
      },
    },
  }
})
