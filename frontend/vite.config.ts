import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      usePolling: true,
    },
    host: true,
    strictPort: true,
    port: 5173,
    proxy: {
      // Forward share links directly to the backend — only match /s/{slug}, NOT /src/
      '^/s/': { target: 'http://api:8000', changeOrigin: true },
      '/uploads/download': { target: 'http://api:8000', changeOrigin: true },
    },
  },
})
