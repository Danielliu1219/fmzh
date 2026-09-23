<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="brand" @click="$router.push('/')">
        <span class="logo"><el-icon :size="19"><Reading /></el-icon></span>
        <div class="brand-text">
          <span class="title">期末周别慌！</span>
          <span class="subtitle">AI 备考助手</span>
        </div>
      </div>
      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-link"
          :class="{ active: isActive(item.path) }"
        >
          {{ item.label }}
        </router-link>
      </nav>
      <div class="user-area">
        <el-avatar :size="32" class="avatar">{{ displayName.charAt(0) }}</el-avatar>
        <span class="name">{{ displayName }}</span>
        <el-divider direction="vertical" class="divider" />
        <el-button text class="logout" @click="onLogout">
          <el-icon><SwitchButton /></el-icon>
          <span>退出</span>
        </el-button>
      </div>
    </el-header>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const navItems = [
  { path: '/', label: '首页' },
  { path: '/exams', label: '课程管理' },
  { path: '/materials', label: '复习资料' },
  { path: '/analysis', label: 'AI 复习分析' },
]

const displayName = computed(() => userStore.displayName)
const isActive = (path) => (path === '/' ? route.path === '/' : route.path.startsWith(path))

const onLogout = () => {
  userStore.logout()
  ElMessage.success('已退出登录，考试顺利！')
  router.push('/login')
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
}
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 28px;
  background: var(--bg-page);
  border-bottom: 2px solid var(--ink-1);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.logo {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: var(--coral);
  color: #fff;
  display: grid;
  place-items: center;
  border: 1.5px solid var(--ink-1);
  box-shadow: var(--shadow-ink-xs);
}
.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.title {
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 900;
  color: var(--ink-1);
  letter-spacing: 0.06em;
}
.subtitle {
  font-size: 10px;
  letter-spacing: 2.5px;
  color: var(--ink-3);
  font-weight: 600;
}
.nav {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-link {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 14.5px;
  font-weight: 700;
  color: var(--ink-2);
  text-decoration: none;
  transition: all 0.15s;
  border: 1.5px solid transparent;
}
.nav-link:hover {
  color: var(--ink-1);
  background: var(--bg-soft);
}
.nav-link.active {
  color: #fff;
  background: var(--ink-1);
  border-color: var(--ink-1);
  box-shadow: var(--shadow-ink-xs);
}
.user-area {
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}
.avatar {
  background: var(--ink-1);
  color: var(--bg-page);
  font-weight: 700;
  border: 1.5px solid var(--ink-1);
}
.name {
  font-size: 14px;
  color: var(--ink-1);
  font-weight: 700;
}
.divider {
  height: 16px;
  margin: 0 2px;
  border-color: var(--line-strong);
}
.logout {
  color: var(--ink-3);
  font-weight: 700;
  padding: 6px 10px;
}
.logout:hover {
  color: var(--red);
}
.main {
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  padding: 28px 24px 56px;
}
</style>
