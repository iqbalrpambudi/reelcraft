import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Built straight into the Python package so `reelcraft serve` and the wheel ship it
  build: { outDir: '../src/reelcraft/api/static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
})
