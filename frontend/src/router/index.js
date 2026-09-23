import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../views/Layout.vue'

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
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 登录守卫：未登录一律去登录页，已登录访问登录页则回首页
router.beforeEach((to) => {
  const token = localStorage.getItem('fmzh_token')
  if (to.path !== '/login' && !token) return '/login'
  if (to.path === '/login' && token) return '/'
})

export default router
