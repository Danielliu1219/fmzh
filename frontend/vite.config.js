import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发服务器把 /api 请求代理到后端，前端代码里直接写相对路径即可。
// base：仅构建时指向 GitHub Pages 项目站（https://danielliu1219.github.io/fmzh/），
// 本地 npm run dev 保持 '/'，两条路径互不影响。
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/fmzh/' : '/',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))
