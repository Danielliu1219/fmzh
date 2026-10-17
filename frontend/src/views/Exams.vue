<template>
  <div>
    <div class="page-head">
      <h2>课程管理</h2>
      <span class="head-sub">录入课程与考试时间，安排复习任务，考表和倒计时从这里生成</span>
      <el-radio-group v-model="viewMode" class="view-switch">
        <el-radio-button value="list">科目列表</el-radio-button>
        <el-radio-button value="calendar">备考日历</el-radio-button>
      </el-radio-group>
      <el-button @click="onExportIcs" :loading="exporting" title="导出为日历文件，可导入手机/电脑日历">
        <el-icon><Download /></el-icon>&nbsp;导出 ICS
      </el-button>
      <el-button type="primary" @click="openDialog()">
        <el-icon><Plus /></el-icon>&nbsp;添加课程
      </el-button>
    </div>

    <!-- ==================== 科目列表视图 ==================== -->
    <template v-if="viewMode === 'list'">
      <!-- 2.4 筛选查看：科目 / 考试日期区间 -->
      <el-card shadow="never" class="filter-card">
        <div class="filter-bar">
          <el-input
            v-model="filter.subject"
            placeholder="按科目筛选，如：数学"
            clearable
            style="width: 200px"
            @keyup.enter="load"
            @clear="load"
          />
          <el-date-picker
            v-model="filter.range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="考试日期从"
            end-placeholder="到"
            style="width: 260px"
            @change="load"
          />
          <el-button @click="load">
            <el-icon><Search /></el-icon>&nbsp;筛选
          </el-button>
          <el-button link type="info" @click="resetFilter">重置</el-button>
        </div>
      </el-card>

      <el-card shadow="never">
        <el-table :data="exams" v-loading="loading" empty-text="还没有课程，点右上角添加">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="task-panel">
                <div class="task-panel-head">
                  <b>{{ row.subject }} · 学习任务</b>
                  <el-button size="small" type="primary" plain @click="openTaskDialog(null, row)">
                    <el-icon><Plus /></el-icon>&nbsp;添加任务
                  </el-button>
                </div>
                <el-table
                  :data="tasksOf(row.id)"
                  size="small"
                  :empty-text="'该科目还没有任务，可手动添加，或在 AI 分析后自动生成'"
                >
                  <el-table-column prop="plan_date" label="日期" width="110" />
                  <el-table-column prop="title" label="任务" min-width="220" />
                  <el-table-column label="时长" width="80">
                    <template #default="{ row: t }">{{ t.estimated_minutes }} 分</template>
                  </el-table-column>
                  <el-table-column label="优先级" width="80">
                    <template #default="{ row: t }">
                      <el-tag size="small" :type="['', 'danger', 'warning', 'info'][t.priority] || 'info'">
                        {{ { 1: '高', 2: '中', 3: '低' }[t.priority] || '中' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="80">
                    <template #default="{ row: t }">
                      <el-tag size="small" :type="t.is_done ? 'success' : 'info'">
                        {{ t.is_done ? '已完成' : '待完成' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="190">
                    <template #default="{ row: t }">
                      <el-button v-if="!t.is_done" link type="success" size="small" @click="onCheckin(t)">打卡</el-button>
                      <el-button v-else link size="small" @click="onUncheckin(t)">撤销</el-button>
                      <el-button link type="primary" size="small" @click="openTaskDialog(t, row)">编辑</el-button>
                      <el-button link type="danger" size="small" @click="onDeleteTask(t)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="subject" label="科目" min-width="150">
            <template #default="{ row }">
              <span class="subject-dot" :style="{ background: examColor(row).color }" />
              <b>{{ row.subject }}</b>
            </template>
          </el-table-column>
          <el-table-column prop="exam_date" label="考试日期" width="120" />
          <el-table-column prop="location" label="地点" min-width="110">
            <template #default="{ row }">{{ row.location || '-' }}</template>
          </el-table-column>
          <el-table-column prop="duration_minutes" label="时长" width="90">
            <template #default="{ row }">{{ row.duration_minutes }} 分钟</template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="120">
            <template #default="{ row }">{{ row.note || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="250" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openPlanDialog(row)" title="按考试日期倒推生成复习计划">倒推计划</el-button>
              <el-button link type="primary" @click="onPickIcs(row)" title="把课表/日历 ICS 导入为本科目任务">导入 ICS</el-button>
              <el-button link @click="openDialog(row)">编辑</el-button>
              <el-button link type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- ==================== 备考日历视图（2.9）：拖拽任务卡片改期 ==================== -->
    <el-card v-else shadow="never">
      <el-calendar v-model="calDate">
        <template #date-cell="{ data }">
          <div
            class="cal-cell"
            :class="{ today: data.isSelected }"
            @dragover.prevent
            @drop="onDropToDate($event, data.day)"
          >
            <div class="cal-date-num">{{ Number(data.day.split('-')[2]) }}</div>
            <div v-if="examsOn(data.day).length" class="cal-exams">
              <div v-for="e in examsOn(data.day)" :key="e.id" class="cal-exam" :style="{ background: examColor(e).soft, borderColor: examColor(e).color }">
                📝 {{ e.subject }}
              </div>
            </div>
            <div
              v-for="t in tasksOn(data.day).slice(0, 3)"
              :key="t.id"
              class="cal-task"
              :class="{ done: t.is_done }"
              :style="{ borderLeftColor: examColorById(t.exam_id).color }"
              draggable="true"
              :title="`${t.title}（${t.estimated_minutes} 分钟）— 拖拽到其他日期可改期`"
              @dragstart="onDragTaskStart($event, t)"
              @click="openTaskDialog(t)"
            >
              {{ t.title }}
            </div>
            <div v-if="tasksOn(data.day).length > 3" class="cal-more">等 {{ tasksOn(data.day).length }} 项任务…</div>
          </div>
        </template>
      </el-calendar>
      <div class="cal-legend">
        <span><i class="legend-dot" style="background: var(--coral)" /> 考试日</span>
        <span>拖拽任务卡片到其他日期即可改期（改期时自动做冲突检测）</span>
      </div>
    </el-card>

    <!-- 课程编辑对话框（含科目颜色 2.11） -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑课程' : '添加课程'" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="科目" prop="subject">
          <el-input v-model="form.subject" placeholder="如：高等数学" />
        </el-form-item>
        <el-form-item label="考试日期" prop="exam_date">
          <el-date-picker v-model="form.exam_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" placeholder="选择日期" />
        </el-form-item>
        <el-form-item label="地点" prop="location">
          <el-input v-model="form.location" placeholder="如：教三 101（选填）" />
        </el-form-item>
        <el-form-item label="时长" prop="duration_minutes">
          <el-input-number v-model="form.duration_minutes" :min="10" :max="480" :step="10" />
          <span class="unit">分钟</span>
        </el-form-item>
        <el-form-item label="科目颜色" prop="color">
          <div class="color-row">
            <button
              v-for="c in SUBJECT_PALETTE"
              :key="c.color"
              type="button"
              class="color-swatch"
              :class="{ active: form.color === c.color }"
              :style="{ background: c.color }"
              :title="c.color"
              @click="form.color = form.color === c.color ? '' : c.color"
            />
            <span class="color-hint">默认按科目名自动配色，选择后全站固定</span>
          </div>
        </el-form-item>
        <el-form-item label="备注" prop="note">
          <el-input v-model="form.note" placeholder="开卷/闭卷等（选填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 学习任务编辑对话框（2.6 编辑 / 2.5 添加复用，保存前 2.8 冲突检测） -->
    <el-dialog v-model="taskDialogVisible" :title="taskForm.id ? '编辑任务' : '添加任务'" width="440px">
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="90px">
        <el-form-item label="所属科目" prop="exam_id">
          <el-select v-model="taskForm.exam_id" style="width: 100%" placeholder="选择科目">
            <el-option v-for="e in exams" :key="e.id" :value="e.id" :label="e.subject" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务内容" prop="title">
          <el-input v-model="taskForm.title" placeholder="如：刷 2018 年真题一套" maxlength="100" />
        </el-form-item>
        <el-form-item label="计划日期" prop="plan_date">
          <el-date-picker v-model="taskForm.plan_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="预计时长" prop="estimated_minutes">
          <el-input-number v-model="taskForm.estimated_minutes" :min="15" :max="720" :step="15" />
          <span class="unit">分钟</span>
        </el-form-item>
        <el-form-item label="优先级" prop="priority">
          <el-radio-group v-model="taskForm.priority">
            <el-radio-button :value="1">高</el-radio-button>
            <el-radio-button :value="2">中</el-radio-button>
            <el-radio-button :value="3">低</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="taskSaving" @click="onSaveTask">保存</el-button>
      </template>
    </el-dialog>

    <!-- 倒推生成备考时间表（2.7） -->
    <el-dialog v-model="planDialogVisible" title="倒推生成备考时间表" width="420px">
      <p class="plan-tip">
        依据「<b>{{ planExam?.subject }}</b>」的考试日期（{{ planExam?.exam_date }}），从现在倒推到考试前一天，
        每天安排不超过设定时长的复习任务，越临近考试优先级越高。
      </p>
      <el-form label-width="110px">
        <el-form-item label="每天复习时长">
          <el-input-number v-model="planDailyMinutes" :min="30" :max="480" :step="30" />
          <span class="unit">分钟</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="planDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="planLoading" @click="onGeneratePlan">生成计划</el-button>
      </template>
    </el-dialog>

    <input ref="icsInputRef" type="file" accept=".ics,text/calendar" style="display: none" @change="onImportIcs" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { examApi, taskApi } from '../api'
import { USE_MOCK, getToday, mockStudySession } from '../mock/dashboard'
import { examColor, SUBJECT_PALETTE } from '../utils/subjectColor'

// 2.11 全站统一科目配色：任务/日历只有 exam_id 时先找考试再取色
const examColorById = (examId) => examColor(exams.value.find((e) => e.id === examId))

const viewMode = ref('list')
const exams = ref([])
const tasks = ref([])
const loading = ref(false)
const exporting = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref()

// 2.4 筛选条件
const filter = reactive({ subject: '', range: null })

const emptyForm = () => ({
  id: null,
  subject: '',
  exam_date: '',
  location: '',
  duration_minutes: 120,
  note: '',
  color: '',
})
const form = reactive(emptyForm())
const rules = {
  subject: [{ required: true, message: '请输入科目', trigger: 'blur' }],
  exam_date: [{ required: true, message: '请选择考试日期', trigger: 'change' }],
}

const load = async () => {
  loading.value = true
  try {
    // mock 模式下展示本地演示数据；真实模式下走接口（含筛选参数）
    if (USE_MOCK) {
      exams.value = structuredClone(mockStudySession.exams)
    } else {
      const params = {}
      if (filter.subject) params.subject = filter.subject
      if (filter.range?.length === 2) {
        params.date_from = filter.range[0]
        params.date_to = filter.range[1]
      }
      exams.value = await examApi.list(params)
    }
    await loadTasks()
  } finally {
    loading.value = false
  }
}

const loadTasks = async () => {
  if (USE_MOCK) {
    tasks.value = structuredClone(mockStudySession.tasks)
    return
  }
  tasks.value = await taskApi.list()
}

const resetFilter = () => {
  filter.subject = ''
  filter.range = null
  load()
}

const openDialog = (row) => {
  Object.assign(form, emptyForm(), row ? { ...row } : {})
  dialogVisible.value = true
}

const onSave = async () => {
  await formRef.value.validate()
  saving.value = true
  try {
    if (USE_MOCK) {
      // mock 模式下仅改本地列表
      if (form.id) {
        const i = exams.value.findIndex((e) => e.id === form.id)
        if (i >= 0) exams.value[i] = { ...exams.value[i], ...form }
        ElMessage.success('修改成功')
      } else {
        exams.value.unshift({ ...form, id: Date.now(), days_left: null, progress: 0 })
        ElMessage.success('添加成功')
      }
      dialogVisible.value = false
      return
    }
    if (form.id) {
      await examApi.update(form.id, form)
      ElMessage.success('修改成功')
    } else {
      await examApi.create(form)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

const onDelete = async (row) => {
  await ElMessageBox.confirm(
    `确定删除「${row.subject}」吗？该考试下的资料、分析和任务也会随之失效。`,
    '删除确认',
    { type: 'warning' },
  )
  if (USE_MOCK) {
    const i = exams.value.findIndex((e) => e.id === row.id)
    if (i >= 0) exams.value.splice(i, 1)
    ElMessage.success('已删除')
    return
  }
  await examApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

// ==================== 学习任务：添加（2.5 复用）/ 编辑（2.6）/ 冲突检测（2.8） ====================
const taskDialogVisible = ref(false)
const taskSaving = ref(false)
const taskFormRef = ref()
const taskForm = reactive({ id: null, exam_id: null, title: '', plan_date: '', estimated_minutes: 60, priority: 2 })
const taskRules = {
  exam_id: [{ required: true, message: '请选择科目', trigger: 'change' }],
  title: [{ required: true, message: '请输入任务内容', trigger: 'blur' }],
  plan_date: [{ required: true, message: '请选择计划日期', trigger: 'change' }],
}

const tasksOf = (examId) => tasks.value.filter((t) => t.exam_id === examId)

const openTaskDialog = (task, exam) => {
  Object.assign(taskForm, {
    id: task?.id || null,
    exam_id: task?.exam_id || exam?.id || exams.value[0]?.id || null,
    title: task?.title || '',
    plan_date: task?.plan_date || '',
    estimated_minutes: task?.estimated_minutes || 60,
    priority: task?.priority || 2,
  })
  taskDialogVisible.value = true
}

// 2.8 冲突检测：保存前预检，当天总时长超上限时提醒（可选择仍要保存）
const confirmNoConflict = async (payload, excludeId) => {
  if (USE_MOCK) return
  const res = await taskApi.checkConflict({
    plan_date: payload.plan_date,
    estimated_minutes: payload.estimated_minutes,
    exclude_task_id: excludeId || undefined,
  })
  if (res.conflict) {
    await ElMessageBox.confirm(
      `「${payload.plan_date}」当天已安排 ${res.existing_minutes} 分钟，加上本任务共 ${res.planned_minutes} 分钟，超过每日上限 ${res.limit_minutes} 分钟。仍要保存吗？`,
      '日程冲突提醒',
      { type: 'warning', confirmButtonText: '仍要保存', cancelButtonText: '返回调整' },
    )
  }
}

const onSaveTask = async () => {
  await taskFormRef.value.validate()
  taskSaving.value = true
  try {
    const payload = { ...taskForm }
    delete payload.id
    await confirmNoConflict(payload, taskForm.id)
    if (USE_MOCK) {
      if (taskForm.id) {
        const i = tasks.value.findIndex((t) => t.id === taskForm.id)
        if (i >= 0) tasks.value[i] = { ...tasks.value[i], ...taskForm }
        ElMessage.success('修改成功')
      } else {
        tasks.value.unshift({ ...taskForm, id: Date.now(), is_done: false, source: 'manual' })
        ElMessage.success('添加成功')
      }
      taskDialogVisible.value = false
      return
    }
    if (taskForm.id) {
      await taskApi.update(taskForm.id, payload)
      ElMessage.success('任务已更新')
    } else {
      await taskApi.create(payload)
      ElMessage.success('任务已添加')
    }
    taskDialogVisible.value = false
    loadTasks()
  } finally {
    taskSaving.value = false
  }
}

const onCheckin = async (t) => {
  if (!USE_MOCK) await taskApi.checkin(t.id)
  t.is_done = true
  if (USE_MOCK) t.done_at = `${getToday()}T12:00:00`
  ElMessage.success('已完成，继续保持！')
}

const onUncheckin = async (t) => {
  if (!USE_MOCK) await taskApi.uncheckin(t.id)
  t.is_done = false
  if (USE_MOCK) t.done_at = null
}

const onDeleteTask = async (t) => {
  await ElMessageBox.confirm(`确定删除任务「${t.title}」吗？`, '删除确认', { type: 'warning' })
  if (!USE_MOCK) await taskApi.remove(t.id)
  tasks.value = tasks.value.filter((x) => x.id !== t.id)
  ElMessage.success('已删除')
}

// ==================== 倒推生成备考时间表（2.7） ====================
const planDialogVisible = ref(false)
const planLoading = ref(false)
const planExam = ref(null)
const planDailyMinutes = ref(120)

const openPlanDialog = (row) => {
  planExam.value = row
  planDailyMinutes.value = 120
  planDialogVisible.value = true
}

const onGeneratePlan = async () => {
  if (USE_MOCK) {
    ElMessage.info('演示模式：倒推计划需联调真实后端（LLM_MOCK=true 即可演示）')
    planDialogVisible.value = false
    return
  }
  planLoading.value = true
  try {
    const res = await examApi.generateSchedule(planExam.value.id, { daily_minutes: planDailyMinutes.value })
    planDialogVisible.value = false
    if (res.conflicts?.length) {
      const lines = res.conflicts
        .slice(0, 5)
        .map((c) => `${c.date}：已有 ${c.existing_minutes} 分钟 + 新排 ${c.planned_minutes - c.existing_minutes} 分钟`)
        .join('\n')
      await ElMessageBox.alert(
        `已生成 ${res.created} 天复习计划（共约 ${Math.round(res.total_minutes / 60)} 小时）。以下日期与现有日程冲突，请到列表中手动调整：\n${lines}`,
        '生成完成，部分日期有冲突',
        { type: 'warning', customStyle: { whiteSpace: 'pre-line' } },
      )
    } else {
      ElMessage.success(`已生成 ${res.created} 天复习计划（共约 ${Math.round(res.total_minutes / 60)} 小时），展开科目行查看`)
    }
    loadTasks()
  } finally {
    planLoading.value = false
  }
}

// ==================== ICS 导入（2.12）/ 导出（2.13） ====================
const icsInputRef = ref()
let icsExamId = null

const onPickIcs = (row) => {
  icsExamId = row.id
  icsInputRef.value.value = ''
  icsInputRef.value.click()
}

const onImportIcs = async (ev) => {
  const file = ev.target.files?.[0]
  if (!file) return
  if (USE_MOCK) {
    ElMessage.info('演示模式：ICS 导入需联调真实后端')
    return
  }
  const fd = new FormData()
  fd.append('file', file)
  fd.append('exam_id', String(icsExamId))
  loading.value = true
  try {
    const res = await examApi.importIcs(fd)
    if (res.conflicts?.length) {
      const lines = res.conflicts.map((c) => `${c.date}：共 ${c.planned_minutes} 分钟（上限 ${c.limit_minutes}）`).join('\n')
      await ElMessageBox.alert(
        `导入 ${res.imported} 项任务${res.skipped ? `，跳过 ${res.skipped} 项无效事件` : ''}。以下日期合并后超上限，建议手动调整：\n${lines}`,
        '导入完成，部分日期有冲突',
        { type: 'warning', customStyle: { whiteSpace: 'pre-line' } },
      )
    } else {
      ElMessage.success(`导入成功：${res.imported} 项任务${res.skipped ? `，跳过 ${res.skipped} 项` : ''}`)
    }
    loadTasks()
  } finally {
    loading.value = false
  }
}

const onExportIcs = async () => {
  if (USE_MOCK) {
    ElMessage.info('演示模式：ICS 导出需联调真实后端')
    return
  }
  exporting.value = true
  try {
    const blob = await examApi.exportIcs()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'fmzh_备考日历.ics'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出备考日历（考试 + 任务），可导入手机/电脑日历')
  } finally {
    exporting.value = false
  }
}

// ==================== 备考日历（2.9） ====================
const calDate = ref(new Date(`${getToday()}T12:00:00`))
const dragTask = ref(null)

const tasksOn = (day) => tasks.value.filter((t) => t.plan_date === day)
const examsOn = (day) => exams.value.filter((e) => e.exam_date === day)

const onDragTaskStart = (ev, t) => {
  dragTask.value = t
  ev.dataTransfer.effectAllowed = 'move'
}

const onDropToDate = async (ev, day) => {
  const t = dragTask.value
  dragTask.value = null
  if (!t || t.plan_date === day) return
  if (USE_MOCK) {
    t.plan_date = day
    ElMessage.success(`演示：任务已改期到 ${day}`)
    return
  }
  try {
    await confirmNoConflict({ plan_date: day, estimated_minutes: t.estimated_minutes }, t.id)
  } catch {
    return // 用户选择「返回调整」
  }
  await taskApi.update(t.id, { plan_date: day })
  t.plan_date = day
  ElMessage.success(`「${t.title.slice(0, 12)}…」已改期到 ${day}`)
}

watch(tasks, value=>{if(USE_MOCK)mockStudySession.tasks=JSON.parse(JSON.stringify(value))},{deep:true,flush:'sync'})
watch(exams, value=>{if(USE_MOCK)mockStudySession.exams=JSON.parse(JSON.stringify(value))},{deep:true,flush:'sync'})

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
.view-switch {
  margin-right: 4px;
}
.filter-card {
  margin-bottom: 14px;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.subject-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 8px;
  border: 1.5px solid var(--ink-1);
  vertical-align: middle;
}
.task-panel {
  padding: 4px 12px 8px;
}
.task-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.unit {
  margin-left: 8px;
  color: var(--text-low);
  font-size: 13px;
}
.color-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.color-swatch {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1.5px solid var(--ink-1);
  cursor: pointer;
  padding: 0;
  transition: transform 0.12s;
}
.color-swatch:hover {
  transform: scale(1.12);
}
.color-swatch.active {
  box-shadow: 2px 2px 0 var(--ink-1);
  outline: 2px solid var(--bg-card);
  outline-offset: -5px;
}
.color-hint {
  font-size: 12px;
  color: var(--text-low);
}
.plan-tip {
  font-size: 13px;
  color: var(--text-mid);
  margin: 0 0 14px;
  line-height: 1.7;
}

/* 备考日历 */
.cal-cell {
  min-height: 78px;
  cursor: default;
}
.cal-date-num {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-mid);
}
.cal-exam {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-1);
  border: 1px solid;
  border-radius: 4px;
  padding: 0 4px;
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cal-task {
  font-size: 11px;
  color: var(--text-hi);
  background: var(--bg-page);
  border-left: 3px solid var(--coral);
  border-radius: 3px;
  padding: 1px 4px;
  margin-top: 3px;
  cursor: grab;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cal-task.done {
  text-decoration: line-through;
  color: var(--text-low);
  opacity: 0.6;
}
.cal-more {
  font-size: 11px;
  color: var(--text-low);
  margin-top: 2px;
}
.cal-legend {
  display: flex;
  gap: 18px;
  font-size: 12.5px;
  color: var(--text-low);
  margin-top: 10px;
  align-items: center;
}
.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 4px;
}
</style>
