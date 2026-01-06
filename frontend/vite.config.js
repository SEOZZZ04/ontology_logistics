import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static', // 상위 폴더의 static으로 빌드
    emptyOutDir: true
  }
})
