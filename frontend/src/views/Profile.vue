<template>
  <div>
    <div class="page-head">
      <h2>个人资料</h2>
      <span class="head-sub">维护头像、姓名与学籍信息，修改密码与注销账号也在这里</span>
    </div>

    <el-row :gutter="20">
      <!-- 编辑个人资料（1.6） -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header><b>编辑资料</b></template>
          <el-form :model="form" label-width="90px">
            <el-form-item label="头像">
              <div class="avatar-row">
                <el-avatar :size="52" :style="{ background: form.avatar || AVATAR_PALETTE[0] }" class="avatar-preview">
                  {{ (form.nickname || user?.username || '同').charAt(0) }}
                </el-avatar>
                <div class="swatches">
                  <button
                    v-for="c in AVATAR_PALETTE"
                    :key="c"
                    type="button"
                    class="swatch"
                    :class="{ active: form.avatar === c }"
                    :style="{ background: c }"
                    @click="form.avatar = c"
                  />
                </div>
              </div>
            </el-form-item>
            <el-form-item label="姓名">
              <el-input v-model="form.nickname" placeholder="姓名/昵称" maxlength="32" />
            </el-form-item>
            <el-form-item label="学号">
              <el-input v-model="form.student_no" placeholder="找回密码时用于身份验证" maxlength="32" />
            </el-form-item>
            <el-form-item label="专业">
              <el-input v-model="form.major" placeholder="如：计算机科学与技术" maxlength="32" />
            </el-form-item>
            <el-form-item label="年级">
              <el-input v-model="form.grade" placeholder="如：2024级" maxlength="16" />
            </el-form-item>
            <el-form-item label="班级">
              <el-input v-model="form.class_name" placeholder="如：计科2401班" maxlength="32" />
            </el-form-item>
            <el-form-item>
              <el-alert
                title="学号请如实填写：账号被锁定时，凭「账号 + 学号」才能完成身份验证找回密码。"
                type="info"
                :closable="false"
                class="tip"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="onSave">保存修改</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 账号安全（1.5 修改密码 / 1.7 注销账号） -->
      <el-col :span="10">
        <el-card shadow="never" class="sec-card">
          <template #header><b>账号安全</b></template>
          <div class="sec-item">
            <div>
              <b>修改密码</b>
              <p class="sec-desc">验证原密码后设置新密码（6-32 位）</p>
            </div>
            <el-button @click="pwdVisible = true">修改</el-button>
          </div>
          <el-divider />
          <div class="sec-item">
            <div>
              <b class="danger">注销账号</b>
              <p class="sec-desc">二次确认后清除全部个人数据（含上传资料），不可恢复</p>
            </div>
            <el-button type="danger" plain @click="onDeactivate">注销</el-button>
          </div>
        </el-card>
        <el-card shadow="never" class="info-card">
          <div class="info-row"><span>账号</span><b>{{ user?.username || '-' }}</b></div>
          <div class="info-row"><span>注册时间</span><b>{{ formatDate(user?.created_at) }}</b></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 修改密码（1.5） -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="400px" :before-close="passwordDraft.beforeClose" @closed="clearPassword">
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="6-32 位" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="pwdSaving" @click="passwordDraft.close">取消</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="onChangePassword">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useDialogDraft, usePendingWork, useActionLock, confirmAction } from '../composables/usePendingWork'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { authApi } from '../api'
import { useUserStore } from '../stores/user'
import { AVATAR_PALETTE } from '../utils/subjectColor'
import { USE_MOCK } from '../mock/dashboard'

const router = useRouter()
const userStore = useUserStore()

const user = ref(userStore.user)
const saving = ref(false)
const pwdVisible = ref(false)
const pwdSaving = ref(false)
const pwdFormRef = ref()

const form = reactive({ nickname: '', student_no: '', major: '', grade: '', class_name: '', avatar: '' })
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const passwordDraft = useDialogDraft(pwdForm,pwdVisible,pwdSaving,'密码表单')
const profileAction = useActionLock('账号安全操作')
const savedForm = ref('')
const clearPassword = () => {pwdForm.old_password=pwdForm.new_password=pwdForm.confirm=''}
usePendingWork(() => ({busy:saving.value ? '个人资料保存' : '', warning:savedForm.value && JSON.stringify(form)!==savedForm.value ? '个人资料有未保存修改，离开会丢弃。' : ''}))
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 32, message: '密码长度 6-32 位', trigger: 'blur' },
  ],
  confirm: [
    {
      validator: (rule, value, callback) =>
        value === pwdForm.new_password ? callback() : callback(new Error('两次输入的新密码不一致')),
      trigger: 'blur',
    },
  ],
}

const fillForm = (u) => {
  form.nickname = u?.nickname || ''
  form.student_no = u?.student_no || ''
  form.major = u?.major || ''
  form.grade = u?.grade || ''
  form.class_name = u?.class_name || ''
  form.avatar = u?.avatar || ''
  savedForm.value = JSON.stringify(form)
}

const load = async () => {
  if (USE_MOCK) {
    // 演示模式：使用本地演示会话，不调接口
    user.value = userStore.user || { username: 'demo', nickname: '演示同学' }
    fillForm(user.value)
    return
  }
  user.value = await authApi.me()
  fillForm(user.value)
}

const onSave = async () => {
  if(saving.value) return
  if (!form.nickname.trim()) {
    ElMessage.warning('姓名不能为空')
    return
  }
  if (USE_MOCK) {
    userStore.applyUser({...userStore.user,...form})
    savedForm.value=JSON.stringify(form)
    ElMessage.success('演示模式：资料仅保存在本地预览，不会提交后端')
    return
  }
  saving.value = true
  try {
    const updated = await authApi.updateMe({ ...form })
    userStore.applyUser(updated)
    user.value = updated
    savedForm.value=JSON.stringify(form)
    ElMessage.success('资料已更新')
  } finally {
    saving.value = false
  }
}

const onChangePassword = async () => {
  return profileAction.run(async () => {
  if(pwdSaving.value) return
  await pwdFormRef.value.validate()
  if(!await confirmAction('修改密码后，已有登录会话将失效，需要重新登录；当前浏览器的自测草稿会清除。个人资料的未保存修改不会保存。确认修改？','修改密码',{confirmButtonText:'确认修改密码',cancelButtonText:'继续编辑'})) return
  pwdSaving.value = true
  try {
    if (USE_MOCK) {
      ElMessage.success('演示模式：修改密码需联调真实后端')
      pwdVisible.value = false
      return
    }
    await authApi.changePassword({
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    userStore.logout()
    ElMessage.success('密码修改成功，旧会话已退出，请使用新密码登录')
    router.replace('/login')
    pwdVisible.value = false
    pwdForm.old_password = pwdForm.new_password = pwdForm.confirm = ''
  } finally {
    pwdSaving.value = false
  }
  })
}

// 1.7 注销账号：二次确认后调用后端清理全部数据并退出登录
const onDeactivate = async () => {
  return profileAction.run(async () => {
  if (USE_MOCK) {
    ElMessage.info('演示模式：注销操作需联调真实后端')
    return
  }
  const name = userStore.user?.username || ''
  await ElMessageBox.confirm(
    `注销后将删除你的全部数据：考试、任务、资料、分析记录与上传文件，且不可恢复。确认注销账号「${name}」吗？`,
    '注销账号',
    { type: 'error', confirmButtonText: '确认注销', cancelButtonText: '再想想', confirmButtonClass: 'el-button--danger' },
  )
  await authApi.deactivate()
  userStore.logout()
  ElMessage.success('账号已注销，个人数据已清理')
  router.push('/login')
  })
}

const formatDate = (v) => (v ? String(v).slice(0, 10) : '-')

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.page-head h2 {
  color: var(--text-hi);
}
.head-sub {
  flex: 1;
  font-size: 13px;
  color: var(--text-low);
}
.avatar-row {
  display: flex;
  align-items: center;
  gap: 16px;
}
.avatar-preview {
  border: 2px solid var(--ink-1);
  box-shadow: var(--shadow-ink-xs);
  font-weight: 700;
  font-size: 20px;
}
.swatches {
  display: flex;
  gap: 8px;
}
.swatch {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--ink-1);
  cursor: pointer;
  padding: 0;
  transition: transform 0.12s;
}
.swatch:hover {
  transform: scale(1.12);
}
.swatch.active {
  box-shadow: 2px 2px 0 var(--ink-1);
  outline: 2px solid var(--bg-card);
  outline-offset: -5px;
}
.tip {
  width: 100%;
}
.sec-card,
.info-card {
  margin-bottom: 16px;
}
.sec-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.sec-desc {
  font-size: 12.5px;
  color: var(--text-low);
  margin: 4px 0 0;
}
.danger {
  color: var(--red);
}
.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13.5px;
  color: var(--text-mid);
  padding: 4px 0;
}
</style>
