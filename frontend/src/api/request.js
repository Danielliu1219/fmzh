import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

const request = axios.create({
  baseURL: '/api',
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
  (error) => {
    let msg = error.response?.data?.detail
    if (Array.isArray(msg)) msg = msg[0]?.msg // FastAPI 参数校验错误
    msg = msg || error.message || '请求失败'
    if (error.response?.status === 401) {
      localStorage.removeItem('fmzh_token')
      localStorage.removeItem('fmzh_user')
      if (router.currentRoute.value.path !== '/login') router.push('/login')
    }
    ElMessage.error(msg)
    return Promise.reject(error)
  },
)

export default request
