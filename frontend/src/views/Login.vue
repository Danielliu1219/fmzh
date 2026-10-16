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
            <div class="forgot-row">
              <el-link type="info" :underline="false" @click="openForgot">忘记密码 / 账号被锁？</el-link>
            </div>
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
      <!-- 免登录预览：mock 模式进本地演示数据；联调模式用演示账号 demo 真实登录 -->
      <el-divider><span class="demo-tip">演示模式</span></el-divider>
      <el-button size="large" class="demo-btn" :loading="loading" @click="onDemoLogin">
        <el-icon><VideoPlay /></el-icon>&nbsp;{{ USE_MOCK ? '免登录预览（无后端）' : '演示账号一键登录（demo）' }}
      </el-button>

      <!-- 找回密码（1.4）：账号+学号验证身份 → 重置密码（并立即解锁） -->
      <el-dialog v-model="forgotVisible" title="找回密码" width="400px" append-to-body>
        <template v-if="forgotStep === 1">
          <p class="forgot-tip">输入账号与注册时填写的学号完成身份验证。</p>
          <el-form ref="forgotFormRef" :model="forgotForm" :rules="forgotRules" label-width="80px">
            <el-form-item label="账号" prop="username">
              <el-input v-model="forgotForm.username" placeholder="注册时的账号" />
            </el-form-item>
            <el-form-item label="学号" prop="student_no">
              <el-input v-model="forgotForm.student_no" placeholder="注册/资料里填写的学号" />
            </el-form-item>
          </el-form>
        </template>
        <template v-else>
          <el-alert
            :title="`身份验证通过（${forgotNickname}），请设置新密码，重置后账号将立即解锁。`"
            type="success"
            :closable="false"
            class="forgot-tip"
          />
          <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-width="80px">
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="resetForm.new_password" type="password" show-password placeholder="6-32 位" />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm">
              <el-input v-model="resetForm.confirm" type="password" show-password />
            </el-form-item>
          </el-form>
        </template>
        <template #footer>
          <el-button @click="forgotVisible = false">取消</el-button>
          <el-button v-if="forgotStep === 1" type="primary" :loading="loading" @click="onVerifyIdentity">
            验证身份
          </el-button>
          <el-button v-else type="primary" :loading="loading" @click="onResetPassword">重置密码</el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../api'
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

// mock 模式种本地会话跳过登录；联调模式用演示账号真实登录，数据与功能全部真实
const onDemoLogin = async () => {
  if (USE_MOCK) {
    localStorage.setItem('fmzh_token', 'demo-token')
    localStorage.setItem('fmzh_user', JSON.stringify({ username: 'demo', nickname: '演示同学' }))
    router.push('/')
    return
  }
  loading.value = true
  try {
    await userStore.login('demo', 'demo123456')
    ElMessage.success('已用演示账号 demo 登录（数据来自 seed_demo.py）')
    router.push('/')
  } finally {
    loading.value = false
  }
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

// ============ 找回密码（1.4）：账号+学号验证身份 → 重置密码并解锁 ============
const forgotVisible = ref(false)
const forgotStep = ref(1) // 1 验证身份 / 2 重置密码
const forgotNickname = ref('')
const forgotFormRef = ref()
const resetFormRef = ref()
let resetToken = ''

const forgotForm = reactive({ username: '', student_no: '' })
const forgotRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  student_no: [{ required: true, message: '请输入学号', trigger: 'blur' }],
}
const resetForm = reactive({ new_password: '', confirm: '' })
const resetRules = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 32, message: '密码长度 6-32 位', trigger: 'blur' },
  ],
  confirm: [
    {
      validator: (rule, value, callback) =>
        value === resetForm.new_password ? callback() : callback(new Error('两次输入的密码不一致')),
      trigger: 'blur',
    },
  ],
}

const openForgot = () => {
  forgotForm.username = loginForm.username
  forgotForm.student_no = ''
  resetForm.new_password = resetForm.confirm = ''
  forgotStep.value = 1
  forgotVisible.value = true
}

const onVerifyIdentity = async () => {
  await forgotFormRef.value.validate()
  loading.value = true
  try {
    const res = await authApi.resetVerify({
      username: forgotForm.username,
      student_no: forgotForm.student_no,
    })
    resetToken = res.reset_token
    forgotNickname.value = res.nickname || forgotForm.username
    forgotStep.value = 2
  } finally {
    loading.value = false
  }
}

const onResetPassword = async () => {
  await resetFormRef.value.validate()
  loading.value = true
  try {
    await authApi.resetConfirm({ reset_token: resetToken, new_password: resetForm.new_password })
    ElMessage.success('密码重置成功，账号已解锁，请用新密码登录')
    forgotVisible.value = false
    tab.value = 'login'
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
.forgot-row {
  margin-top: 12px;
  text-align: center;
}
.forgot-tip {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--text-low);
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
