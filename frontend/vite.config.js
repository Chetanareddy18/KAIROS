import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 127.0.0.1, not localhost: avoids a ~2 s IPv6 fallback per request on Windows
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
