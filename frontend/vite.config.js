import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/calendar/',
  build: {
    outDir: '../we-mp-rss/static/calendar',
    emptyOutDir: true,
  },
})
