import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../views/Layout.vue'
import { readSession } from '../utils/session'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: Layout,
    children: [
      { path: '', name: 'home', component: () => import('../views/Home.vue'), meta: { title: '首页' } },
      { path: 'exams', name: 'exams', component: () => import('../views/Exams.vue'), meta: { title: '考试管理' } },
      { path: 'materials', name: 'materials', component: () => import('../views/Materials.vue'), meta: { title: '复习资料' } },
      { path: 'analysis', name: 'analysis', component: () => import('../views/Analysis.vue'), meta: { title: 'AI 复习分析' } },
      { path: 'admin', name: 'admin', component: () => import('../views/Admin.vue'), meta: { title: '管理端', admin: true } },
      { path: 'stats', name: 'stats', component: () => import('../views/Stats.vue'), meta: { title: '学习统计' } },
      { path: 'report', name: 'report', component: () => import('../views/WeeklyReport.vue'), meta: { title: '备考周报' } },
      { path: 'profile', name: 'profile', component: () => import('../views/Profile.vue'), meta: { title: '个人资料' } },
      { path: 'notifications', name: 'notifications', component: () => import('../views/Notifications.vue'), meta: { title: '通知中心' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  // 用构建基路径（本地为 '/'，GitHub Pages 构建为 '/fmzh/'），子路径部署下路由才正确
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    // Home scrolls after its asynchronous task list has mounted.
    if (to.hash === '#board') return false
    return { top: 0 }
  },
})

// 登录守卫：未登录一律去登录页，已登录访问登录页则回首页；管理端仅管理员可进
router.beforeEach((to) => {
  const { token, user } = readSession()
  if (to.path !== '/login' && !token) return '/login'
  if (to.path === '/login' && token) return '/'
  if (to.meta.admin) {
    if (!user?.is_admin) return '/'
  }
})

export default router
