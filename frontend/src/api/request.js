import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 120000, // AI 分析耗时较长
})

// 请求拦截：自动带上 token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('fmzh_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：统一错误提示；401 时清除登录状态并跳转登录页
request.interceptors.response.use(
  (resp) => resp.data,
  async (error) => {
    let msg = error.response?.data?.detail
    if (Array.isArray(msg)) msg = msg[0]?.msg // FastAPI 参数校验错误
    msg = msg || error.message || '请求失败'
    if (error.response?.status === 401) {
      localStorage.removeItem('fmzh_token')
      localStorage.removeItem('fmzh_user')
      // 延迟加载路由，避免 Layout → store → request → router 的循环依赖破坏热更新。
      const { default: router } = await import('../router')
      if (router.currentRoute.value.path !== '/login') router.push('/login')
    }
    // No saved analysis is an expected empty state when first selecting a subject.
    if (!(error.config?.quietNotFound && error.response?.status === 404)) ElMessage.error(msg)
    return Promise.reject(error)
  },
)

export default request
