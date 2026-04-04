import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.js"],
    exclude: ["**/node_modules/**", "**/dist/**", "tests/e2e/**"],
  },
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        errorHandler: (err, req, res) => {
          if (err.code === 'ECONNREFUSED') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({}));
          } else {
            throw err;
          }
        },
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
})
