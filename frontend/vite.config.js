import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'node:fs'

const showcaseFile = new URL('../项目介绍/期末周别慌_开放平台.html', import.meta.url)
const showcase = () => ({
  name: 'fmzh-showcase',
  generateBundle() {
    this.emitFile({ type: 'asset', fileName: 'showcase/index.html', source: readFileSync(showcaseFile, 'utf8') })
  },
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      if (!['/showcase', '/showcase/', '/showcase/index.html'].includes(req.url?.split('?')[0])) return next()
      res.setHeader('Content-Type', 'text/html; charset=utf-8')
      res.end(readFileSync(showcaseFile, 'utf8'))
    })
  },
})

// 开发服务器把 /api 请求代理到后端，前端代码里直接写相对路径即可。
// base：仅构建时指向 GitHub Pages 项目站（https://danielliu1219.github.io/fmzh/），
// 本地 npm run dev 保持 '/'，两条路径互不影响。
export default defineConfig(({ command, mode }) => ({
  base: command === 'build' && mode !== 'app' ? '/fmzh/' : '/',
  define: mode === 'app' ? {
    'import.meta.env.VITE_USE_MOCK': JSON.stringify('false'),
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api'),
  } : {},
  plugins: [vue(), showcase(), ...(mode === 'app' ? [{name:'fmzh-app-build',generateBundle(){
    this.emitFile({type:'asset',fileName:'app-build.json',source:JSON.stringify({schema:1,mode:'backend-api',base:'/'})})
  }}] : [])],
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
