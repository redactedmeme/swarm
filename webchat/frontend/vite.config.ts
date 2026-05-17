import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/login': 'http://localhost:8080',
      '/chat': 'http://localhost:8080',
      '/hermes': 'http://localhost:8080',
      '/upload': 'http://localhost:8080',
      '/chan': 'http://localhost:8080',
      '/api': 'http://localhost:8080',
      '/proxy-config': 'http://localhost:8080',
      '/proxy-logs': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
      '/ws': { target: 'ws://localhost:8080', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
