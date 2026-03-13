import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:9003',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../hoshino/modules/webui/static',
    emptyOutDir: true
  }
})
