import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/process': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/analyze': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/previews': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: () => {},
      },
      '/progress': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: false,
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/video': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/check-duplicate': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
