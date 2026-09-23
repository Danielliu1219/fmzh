<template>
  <div class="login-page">
    <span class="watermark num">FINAL</span>
    <div class="card">
      <div class="head">
        <div class="logo"><el-icon :size="22"><Reading /></el-icon></div>
        <h1>期末周别慌<span class="coral-mark">！</span></h1>
        <p class="slogan">资料给你 · 计划给你 · 高分也给你</p>
      </div>
      <el-tabs v-model="tab" stretch class="tabs">
        <el-tab-pane label="登录" name="login">
          <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" @keyup.enter="onLogin">
            <el-form-item prop="username">
              <el-input v-model="loginForm.username" placeholder="账号" size="large">
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item prop="password">
              <el-input v-model="loginForm.password" type="password" placeholder="密码" size="large" show-password>
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-button type="primary" size="large" class="submit" :loading="loading" @click="onLogin">
              开始冲刺 →
            </el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules" @keyup.enter="onRegister">
            <el-form-item prop="username">
              <el-input v-model="registerForm.username" placeholder="账号（3-20位字母数字下划线）" size="large" />
            </el-form-item>
            <el-form-item prop="password">
              <el-input v-model="registerForm.password" type="password" placeholder="密码（6-32位）" size="large" show-password />
            </el-form-item>
            <el-form-item prop="confirmPassword">
              <el-input v-model="registerForm.confirmPassword" type="password" placeholder="确认密码" size="large" show-password />
            </el-form-item>
            <el-form-item prop="nickname">
              <el-input v-model="registerForm.nickname" placeholder="姓名/昵称" size="large" />
            </el-form-item>
            <el-form-item prop="studentNo">
              <el-input v-model="registerForm.studentNo" placeholder="学号（选填）" size="large" />
            </el-form-item>
            <el-form-item prop="major">
              <el-input v-model="registerForm.major" placeholder="专业（选填）" size="large" />
            </el-form-item>
            <el-button type="primary" size="large" class="submit" :loading="loading" @click="onRegister">
              加入冲刺 →
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <!-- 仅 mock 模式出现：不启动后端也能进首页看效果（USE_MOCK=false 时自动消失） -->
      <template v-if="USE_MOCK">
        <el-divider><span class="demo-tip">演示模式</span></el-divider>
        <el-button size="large" class="demo-btn" @click="onDemoLogin">
          <el-icon><VideoPlay /></el-icon>&nbsp;免登录预览（无后端）
        </el-button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'
import { USE_MOCK } from '../mock/dashboard'

const router = useRouter()
const userStore = useUserStore()

const tab = ref('login')
const loading = ref(false)
const loginFormRef = ref()
const registerFormRef = ref()

const loginForm = reactive({ username: '', password: '' })
const loginRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  nickname: '',
  studentNo: '',
  major: '',
})
const registerRules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]{3,20}$/, message: '3-20位字母、数字或下划线', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 32, message: '密码长度 6-32 位', trigger: 'blur' },
  ],
  confirmPassword: [
    {
      validator: (rule, value, callback) =>
        value === registerForm.password ? callback() : callback(new Error('两次输入的密码不一致')),
      trigger: 'blur',
    },
  ],
}

const onLogin = async () => {
  await loginFormRef.value.validate()
  loading.value = true
  try {
    await userStore.login(loginForm.username, loginForm.password)
    ElMessage.success(`欢迎回来，${userStore.displayName}`)
    router.push('/')
  } finally {
    loading.value = false
  }
}

// mock 模式下直接种一份本地会话，跳过真实登录
const onDemoLogin = () => {
  localStorage.setItem('fmzh_token', 'demo-token')
  localStorage.setItem('fmzh_user', JSON.stringify({ username: 'demo', nickname: '演示同学' }))
  router.push('/')
}

const onRegister = async () => {
  await registerFormRef.value.validate()
  loading.value = true
  try {
    await userStore.register({
      username: registerForm.username,
      password: registerForm.password,
      nickname: registerForm.nickname,
      student_no: registerForm.studentNo,
      major: registerForm.major,
    })
    ElMessage.success('注册成功，已自动登录')
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--bg-page);
}
/* 巨型水印字（编辑风装饰） */
.watermark {
  position: absolute;
  right: -0.5%;
  bottom: -9%;
  font-size: 380px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.02em;
  color: rgba(12, 22, 20, 0.05);
  pointer-events: none;
  user-select: none;
}
.card {
  position: relative;
  z-index: 1;
  width: 440px;
  background: var(--bg-card);
  border: 2px solid var(--ink-1);
  border-radius: var(--radius-lg);
  border-top: 6px solid var(--coral);
  padding: 38px 40px 28px;
  box-shadow: var(--shadow-ink);
}
.head {
  text-align: center;
  margin-bottom: 14px;
}
.logo {
  width: 54px;
  height: 54px;
  margin: 0 auto;
  border-radius: 10px;
  background: var(--coral);
  color: #fff;
  display: grid;
  place-items: center;
  border: 1.5px solid var(--ink-1);
  box-shadow: var(--shadow-ink-xs);
}
.head h1 {
  font-family: var(--font-serif);
  font-size: 30px;
  font-weight: 900;
  letter-spacing: 0.08em;
  margin-top: 16px;
  color: var(--ink-1);
}
.coral-mark {
  color: var(--coral);
}
.slogan {
  color: var(--text-low);
  font-size: 12.5px;
  letter-spacing: 2px;
  font-weight: 600;
  margin-top: 10px;
}
.tabs :deep(.el-tabs__item) {
  color: var(--text-mid);
  font-weight: 700;
}
.tabs :deep(.el-tabs__item.is-active) {
  color: var(--ink-1);
}
.tabs :deep(.el-tabs__active-bar) {
  background: var(--coral);
  height: 3px;
}
.submit {
  width: 100%;
  letter-spacing: 0.3em;
  font-size: 15px;
}
.demo-tip {
  font-size: 12px;
  color: var(--ink-3);
  letter-spacing: 3px;
  font-weight: 600;
}
.demo-btn {
  width: 100%;
  letter-spacing: 0.2em;
}
</style>
