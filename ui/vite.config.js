import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backend = 'http://127.0.0.1:' + (process.env.TAGWAVE_PORT || '8765')

export default defineConfig({
  plugins: [vue()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/media': { target: backend, changeOrigin: true },
    },
  },
})
