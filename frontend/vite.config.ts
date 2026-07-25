import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Config de Vite para Argos (frontend).
// - plugin de React (JSX / Fast Refresh)
// - plugin de Tailwind v4 (utilidades + tokens)
// - alias "@" -> src, para imports limpios
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
})
