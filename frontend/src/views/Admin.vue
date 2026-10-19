<template>
  <div class="admin">
    <header class="admin-head">
      <div>
        <h1>管理端</h1>
        <p class="admin-sub">课程/科目基础数据维护 · 异常账号与违规内容治理 · 操作日志</p>
      </div>
      <el-tag v-if="USE_MOCK" type="warning" effect="plain">预览态（不落库）</el-tag>
    </header>

    <el-tabs v-model="tab" class="admin-tabs">
      <!-- ===== 8.1 课程/科目维护 ===== -->
      <el-tab-pane label="课程 / 科目维护" name="courses">
        <div class="bar">
          <span class="bar-count">共 {{ courses.length }} 门</span>
          <el-button type="primary" round @click="openCreate">新增课程</el-button>
        </div>
        <el-table :data="courses" stripe v-loading="loading">
          <el-table-column prop="name" label="课程/科目" min-width="140" />
          <el-table-column prop="code" label="课程代码" width="120" />
          <el-table-column prop="teacher" label="任课教师" width="110" />
          <el-table-column prop="credit" label="学分" width="80" />
          <el-table-column prop="term" label="学期" width="100" />
          <el-table-column prop="note" label="备注" min-width="100" />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="removeCourse(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ===== 8.2 异常账号与内容治理 ===== -->
      <el-tab-pane label="异常账号与内容治理" name="governance">
        <h3 class="sec-title">账号列表</h3>
        <el-table :data="users" stripe v-loading="loading">
          <el-table-column prop="username" label="账号" width="130" />
          <el-table-column prop="nickname" label="昵称" width="120" />
          <el-table-column prop="student_no" label="学号" width="120" />
          <el-table-column prop="exam_count" label="考试数" width="90" />
          <el-table-column prop="material_count" label="资料数" width="90" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.is_admin" type="info" effect="plain">管理员</el-tag>
              <el-tag v-else-if="row.is_banned" type="danger">已封禁</el-tag>
              <el-tag v-else type="success" effect="plain">正常</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!row.is_admin && !row.is_banned" link type="danger" @click="ban(row)">封禁</el-button>
              <el-button v-if="!row.is_admin && row.is_banned" link type="primary" @click="unban(row)">解封</el-button>
              <span v-if="row.is_admin" class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>

        <h3 class="sec-title">全站资料（内容治理）</h3>
        <el-table :data="materials" stripe v-loading="loading">
          <el-table-column prop="username" label="上传者" width="130" />
          <el-table-column prop="title" label="资料标题" min-width="180" />
          <el-table-column prop="source_type" label="来源类型" width="110" />
          <el-table-column prop="file_type" label="格式" width="80" />
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeMaterial(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ===== 9.4 操作日志 ===== -->
      <el-tab-pane label="操作日志" name="logs">
        <div class="bar">
          <div class="filters">
            <el-input
              v-model="logFilter.username"
              placeholder="账号"
              clearable
              style="width: 130px"
              @keyup.enter="loadLogs"
            />
            <el-input
              v-model="logFilter.action"
              placeholder="操作类型"
              clearable
              style="width: 130px"
              @keyup.enter="loadLogs"
            />
            <el-input
              v-model="logFilter.keyword"
              placeholder="关键词（账号 / 操作 / 详情）"
              clearable
              style="width: 220px"
              @keyup.enter="loadLogs"
            />
            <el-button type="primary" plain @click="loadLogs">查询</el-button>
          </div>
          <span class="bar-count">最近 {{ logs.length }} 条</span>
        </div>
        <el-table :data="logs" stripe v-loading="logLoading">
          <el-table-column label="时间" width="160">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="username" label="操作账号" width="120" />
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ row.action }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="对象" width="150">
            <template #default="{ row }">
              <span v-if="row.target_type">
                {{ row.target_type }}<span v-if="row.target_id">#{{ row.target_id }}</span>
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ===== 新增 / 编辑课程弹窗 ===== -->
    <el-dialog v-model="courseDialog" :title="editing ? '编辑课程/科目' : '新增课程/科目'" width="460px" align-center>
      <el-form :model="courseForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="courseForm.name" placeholder="如：高等数学" />
        </el-form-item>
        <el-form-item label="代码">
          <el-input v-model="courseForm.code" placeholder="如：MATH101" />
        </el-form-item>
        <el-form-item label="任课教师">
          <el-input v-model="courseForm.teacher" />
        </el-form-item>
        <el-form-item label="学分">
          <el-input-number v-model="courseForm.credit" :min="0" :max="20" :step="0.5" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="courseForm.term" placeholder="如：2024秋" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="courseForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="courseDialog = false">取消</el-button>
        <el-button type="primary" @click="saveCourse">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '../api'
import {
  USE_MOCK,
  mockAdminCourses,
  mockAdminLogs,
  mockAdminMaterials,
  mockAdminUsers,
} from '../mock/dashboard'

const tab = ref('courses')
const loading = ref(false)
const courses = ref([])
const users = ref([])
const materials = ref([])

const logs = ref([])
const logLoading = ref(false)
const logFilter = reactive({ username: '', action: '', keyword: '' })

const courseDialog = ref(false)
const editing = ref(false)
const courseForm = reactive({
  id: null,
  name: '',
  code: '',
  teacher: '',
  credit: 0,
  term: '',
  note: '',
})

const loadAll = async () => {
  loading.value = true
  try {
    if (USE_MOCK) {
      courses.value = structuredClone(mockAdminCourses)
      users.value = structuredClone(mockAdminUsers)
      materials.value = structuredClone(mockAdminMaterials)
    } else {
      const [c, u, m] = await Promise.all([
        adminApi.courses(),
        adminApi.users(),
        adminApi.materials(),
      ])
      courses.value = c
      users.value = u
      materials.value = m
    }
  } catch (e) {
    // request.js 已统一提示错误
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = false
  Object.assign(courseForm, { id: null, name: '', code: '', teacher: '', credit: 0, term: '', note: '' })
  courseDialog.value = true
}

const openEdit = (row) => {
  editing.value = true
  Object.assign(courseForm, row)
  courseDialog.value = true
}

const saveCourse = async () => {
  if (!courseForm.name.trim()) {
    ElMessage.warning('请填写课程/科目名称')
    return
  }
  const payload = {
    name: courseForm.name.trim(),
    code: courseForm.code,
    teacher: courseForm.teacher,
    credit: Number(courseForm.credit) || 0,
    term: courseForm.term,
    note: courseForm.note,
  }
  if (USE_MOCK) {
    if (editing.value) {
      const i = courses.value.findIndex((c) => c.id === courseForm.id)
      courses.value[i] = { ...courses.value[i], ...payload }
    } else {
      courses.value.push({ id: Date.now(), created_at: new Date().toISOString(), ...payload })
    }
    courseDialog.value = false
    ElMessage.success('已保存（预览态不落库）')
    return
  }
  try {
    if (editing.value) await adminApi.updateCourse(courseForm.id, payload)
    else await adminApi.createCourse(payload)
    ElMessage.success('已保存')
    courseDialog.value = false
    await loadAll()
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const removeCourse = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除课程「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  if (USE_MOCK) {
    courses.value = courses.value.filter((c) => c.id !== row.id)
    ElMessage.success('已删除（预览态不落库）')
    return
  }
  try {
    await adminApi.removeCourse(row.id)
    ElMessage.success('已删除')
    await loadAll()
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const ban = async (row) => {
  try {
    await ElMessageBox.confirm(`确定封禁账号「${row.username}」？该账号将无法登录。`, '封禁确认', { type: 'warning' })
  } catch {
    return
  }
  if (USE_MOCK) {
    row.is_banned = true
    ElMessage.success('已封禁（预览态不落库）')
    return
  }
  try {
    await adminApi.banUser(row.id)
    ElMessage.success('已封禁')
    await loadAll()
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const unban = async (row) => {
  if (USE_MOCK) {
    row.is_banned = false
    ElMessage.success('已解封（预览态不落库）')
    return
  }
  try {
    await adminApi.unbanUser(row.id)
    ElMessage.success('已解封')
    await loadAll()
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const removeMaterial = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除资料「${row.title}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  if (USE_MOCK) {
    materials.value = materials.value.filter((m) => m.id !== row.id)
    ElMessage.success('已删除（预览态不落库）')
    return
  }
  try {
    await adminApi.removeMaterial(row.id)
    ElMessage.success('已删除')
    await loadAll()
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const formatTime = (value) => (value || '').replace('T', ' ').slice(0, 16)

const loadLogs = async () => {
  logLoading.value = true
  try {
    if (USE_MOCK) {
      const { username, action, keyword } = logFilter
      logs.value = mockAdminLogs.filter(
        (l) =>
          (!username || l.username.includes(username.trim())) &&
          (!action || l.action.includes(action.trim())) &&
          (!keyword ||
            `${l.username}${l.action}${l.detail}${l.target_type}`.includes(keyword.trim())),
      )
    } else {
      logs.value = await adminApi.logs({ ...logFilter })
    }
  } catch (e) {
    // request.js 已统一提示错误
  } finally {
    logLoading.value = false
  }
}

onMounted(() => {
  loadAll()
  loadLogs()
})
</script>

<style scoped>
.admin {
  max-width: 1100px;
  margin: 0 auto;
}
.admin-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}
.admin-head h1 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 900;
  letter-spacing: 0.06em;
  color: var(--ink-1);
}
.admin-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--ink-3);
}
.admin-tabs {
  margin-top: 10px;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.bar-count {
  font-size: 13px;
  color: var(--ink-3);
}
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sec-title {
  margin: 22px 0 10px;
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 900;
  color: var(--ink-1);
  border-left: 4px solid var(--coral);
  padding-left: 10px;
}
.muted {
  color: var(--ink-3);
}
</style>
