<template>
  <el-container class="layout">
    <a class="skip-link" href="#main-content">跳转到主要内容</a>
    <el-header class="header">
      <router-link class="brand" to="/" aria-label="期末周别慌，返回首页">
        <span class="logo"
          ><el-icon :size="19"><Reading /></el-icon
        ></span>
        <div class="brand-text">
          <span class="title">期末周别慌！</span>
          <span class="subtitle">AI 备考助手</span>
        </div>
      </router-link>
      <nav class="nav" aria-label="主导航">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          :data-tour="item.path.slice(1) || 'home'"
          class="nav-link"
          :class="{ active: isActive(item.path) }"
        >
          {{ item.label }}
        </router-link>
      </nav>
      <div class="user-area">
        <router-link class="notification-bell" data-tour="notifications" to="/notifications" :aria-label="`通知中心，${notices.unread} 条未读`">
          <el-icon :size="18"><Bell /></el-icon><span v-if="notices.unread" class="notification-count">{{ notices.unread > 99 ? '99+' : notices.unread }}</span>
        </router-link>
        <el-avatar
          :size="32"
          class="avatar"
          :style="
            userStore.user?.avatar ? { background: userStore.user.avatar } : {}
          "
        >
          {{ displayName.charAt(0) }}
        </el-avatar>
        <span class="name" @click="$router.push('/profile')" title="个人资料">{{
          displayName
        }}</span>
        <el-divider direction="vertical" class="divider" />
        <el-button text class="logout" aria-label="退出登录" :loading="loggingOut" @click="onLogout">
          <el-icon><SwitchButton /></el-icon>
          <span>退出</span>
        </el-button>
      </div>
    </el-header>
    <el-main id="main-content" class="main" tabindex="-1">
      <router-view />
      <footer class="site-footer">
        <span>期末周别慌！</span><span>把复习拆小，把每一步走好。</span>
      </footer>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { pendingWork, createLogoutFlow } from '../utils/pendingWork'
import { confirmAction, protectBrowserClose } from '../composables/usePendingWork'
import { authApi } from '../api'
import { USE_MOCK } from '../mock/dashboard'
import { useUserStore } from '../stores/user'
import { useNotificationStore } from '../stores/notifications'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const notices = useNotificationStore()
watch(() => route.fullPath, () => notices.refresh(), { immediate: true })
onBeforeUnmount(() => notices.reset())
onMounted(() => window.addEventListener('beforeunload',protectBrowserClose))
onBeforeUnmount(() => window.removeEventListener('beforeunload',protectBrowserClose))

const navItems = computed(() => {
  const items = [
    { path: '/', label: '首页' },
    { path: '/exams', label: '课程管理' },
    { path: '/materials', label: '复习资料' },
    { path: '/analysis', label: 'AI 复习分析' },
    { path: '/stats', label: '学习统计' },
    { path: '/report', label: '备考周报' },
  ]
  if (userStore.isAdmin) items.push({ path: '/admin', label: '管理端' })
  return items
})

const displayName = computed(() => userStore.displayName)
const isActive = (path) =>
  path === '/' ? route.path === '/' : route.path.startsWith(path)

const loggingOut = ref(false)
const logoutFlow = createLogoutFlow({work:pendingWork, token:() => localStorage.getItem('fmzh_token') || '',
  confirm:message => confirmAction(message,'退出登录',{confirmButtonText:'退出登录',cancelButtonText:'继续学习'}),
  revoke:token => USE_MOCK ? Promise.resolve() : authApi.logout(token),
  notify:message => ElMessage.warning(message),
  clear:async () => {userStore.logout();ElMessage.success('已退出登录');await router.replace('/login')},
})
const onLogout = async () => {
  if(loggingOut.value) return
  if(userStore.token !== (localStorage.getItem('fmzh_token') || '')) {ElMessage.warning('账号已在其他页面变化，请刷新后再操作');return}
  loggingOut.value = true
  try {await logoutFlow()} finally {loggingOut.value = false}
}
</script>

<style scoped>
.layout {
  min-height: 100dvh;
}
.header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 24px;
  height: auto;
  min-height: 76px;
  padding: 14px max(24px, calc((100% - 1152px) / 2));
  background: var(--bg-page);
  border-bottom: 1px solid var(--line);
}
.brand {
  text-decoration: none;
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
  padding: 8px 12px;
  white-space: nowrap;
  border-radius: 6px;
  font-size: 12px;
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
.notification-bell { position:relative; display:grid; place-items:center; padding:8px; color:var(--ink-1); text-decoration:none; border-radius:6px; }
.notification-bell:hover { background:var(--bg-soft); }
.notification-count { position:absolute; top:-3px; right:-4px; min-width:16px; padding:1px 4px; background:var(--coral-deep); color:white; border-radius:10px; font-size:10px; line-height:14px; }
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
  cursor: pointer;
}
.name:hover {
  color: var(--coral-deep);
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
.site-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 40px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--ink-2);
  font-size: 10px;
}
.site-footer > span:first-child {
  font-family: var(--font-serif);
  font-weight: 700;
}
@media (max-width: 1100px) {
  .header {
    flex-wrap: wrap;
    gap: 14px 20px;
    padding: 14px 24px 10px;
  }
  .user-area {
    margin-left: auto;
  }
  .nav {
    order: 3;
    flex-basis: 100%;
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .nav-link {
    flex-shrink: 0;
  }
}
@media (max-width: 560px) {
  .header {
    padding: 12px 18px 8px;
    gap: 12px;
  }
  .logo {
    width: 32px;
    height: 32px;
  }
  .brand {
    gap: 8px;
  }
  .title {
    font-size: 16px;
  }
  .subtitle {
    font-size: 8px;
    letter-spacing: 2px;
  }
  .nav {
    gap: 4px;
    margin-inline: -3px;
  }
  .nav-link {
    padding: 7px 10px;
    font-size: 11px;
  }
  .user-area {
    gap: 8px;
  }
  .user-area .name {
    max-width: 64px;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 11px;
  }
  .avatar {
    width: 26px;
    height: 26px;
  }
  .divider,
  .logout span {
    display: none;
  }
  .logout {
    padding: 5px;
  }
  .main {
    padding: 22px 18px 32px;
  }
  .site-footer {
    font-size: 9px;
  }
}
</style>
