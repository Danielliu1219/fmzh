<template>
  <div class="notification-page">
    <header class="notice-head">
      <div>
        <p class="eyebrow">把重要的事，放在心上</p>
        <h1>
          通知中心 <span>{{ store.unread }} 条未读</span>
        </h1>
        <p>打开页面时检查到期提醒，也可以在这里手动刷新。</p>
      </div>
      <el-button :loading="loading" @click="load(true)"
        ><el-icon><Refresh /></el-icon>&nbsp;检查提醒</el-button
      >
    </header>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
      class="notice-error"
    />
    <div class="notice-columns">
      <section class="history-panel" aria-label="通知历史" v-loading="loading">
        <div class="history-tools">
          <el-radio-group
            v-model="unreadOnly"
            @change="changeFilter"
            aria-label="通知范围"
          >
            <el-radio-button :value="false">全部通知</el-radio-button
            ><el-radio-button :value="true">仅未读</el-radio-button>
          </el-radio-group>
          <el-button text :disabled="!store.unread || busy" @click="readAll"
            >全部已读</el-button
          >
        </div>
        <ul v-if="items.length" class="notice-list">
          <li
            v-for="item in items"
            :key="item.id"
            :class="{ unread: !item.is_read }"
          >
            <div class="notice-meta">
              <span>{{
                item.target_type === 'exam' ? '考试提醒' : '任务提醒'
              }}</span
              ><span
                >{{ item.is_read ? '已读' : '未读' }} ·
                {{ notificationTime(item.created_at) }}</span
              >
            </div>
            <h2>{{ item.title }}</h2>
            <p>{{ item.content }}</p>
            <small
              >设置的提醒时间 {{ notificationTime(item.due_at) }} ·
              北京时间</small
            >
            <div class="notice-actions">
              <el-button
                v-if="item.target_available"
                link
                type="primary"
                :disabled="busy"
                @click="openTarget(item)"
                >查看安排 ↗</el-button
              >
              <span v-else class="source-gone">原事项已删除，保留通知历史</span>
              <el-button text :disabled="busy" @click="mark(item)">{{
                item.is_read ? '标为未读' : '标为已读'
              }}</el-button>
              <el-button
                text
                type="danger"
                :disabled="busy"
                @click="remove(item)"
                >删除</el-button
              >
            </div>
          </li>
        </ul>
        <el-empty
          v-else
          :description="
            unreadOnly
              ? '没有未读提醒，可以安心复习'
              : '还没有通知，先为考试或任务设置提醒'
          "
          :image-size="70"
        />
        <el-pagination
          v-if="total > 20"
          v-model:current-page="page"
          :page-size="20"
          :total="total"
          layout="prev, pager, next"
          @current-change="load(false)"
        />
      </section>
      <aside class="notice-settings" aria-label="提醒设置">
        <h2>按你的节奏提醒</h2>
        <div class="pref-row">
          <span>站内提醒总开关</span
          ><el-switch
            id="notice-enabled"
            aria-label="站内提醒总开关"
            v-model="prefs.enabled"
            :disabled="!ready || savingPrefs"
            @change="savePrefs"
          />
        </div>
        <div class="pref-row">
          <span>考试提醒</span
          ><el-switch
            id="exam-enabled"
            aria-label="考试提醒"
            v-model="prefs.exam_enabled"
            :disabled="!ready || savingPrefs || !prefs.enabled"
            @change="savePrefs"
          />
        </div>
        <div class="pref-row">
          <span>任务提醒</span
          ><el-switch
            id="task-enabled"
            aria-label="任务提醒"
            v-model="prefs.task_enabled"
            :disabled="!ready || savingPrefs || !prefs.enabled"
            @change="savePrefs"
          />
        </div>
        <p>
          {{
            prefs.enabled
              ? '开启后，按各事项的设置检查提醒。'
              : '已暂停生成新提醒，已有通知仍可查看。'
          }}
        </p>
        <div class="configure-item">
          <h3>为一件事设置提醒</h3>
          <el-radio-group v-model="kind" size="small" @change="targetId = null"
            ><el-radio-button value="exam">考试</el-radio-button
            ><el-radio-button value="task"
              >复习任务</el-radio-button
            ></el-radio-group
          >
          <el-select
            v-model="targetId"
            filterable
            placeholder="选择考试或任务"
            aria-label="选择提醒事项"
          >
            <el-option
              v-for="item in targets"
              :key="item.id"
              :value="item.id"
              :label="`${item.subject || item.title} · ${item.exam_date || item.plan_date}`"
            />
          </el-select>
          <el-button :disabled="!targetId" @click="dialogVisible = true"
            >设置提醒时间</el-button
          >
          <p>
            也可在课程管理的考试或任务旁点击“提醒”。已完成任务不再生成新提醒。
          </p>
        </div>
        <p class="delivery-note">
          仅站内提醒。网页关闭期间不会主动推送；下次打开时检查仍有效的事项。默认不会为新事项自动开启提醒。
        </p>
      </aside>
    </div>
    <ReminderDialog
      v-model="dialogVisible"
      :kind="kind"
      :target-id="targetId"
      @saved="load(false)"
    />
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ReminderDialog from '../components/ReminderDialog.vue'
import { notifications, notificationTime } from '../services/notifications'
import { useNotificationStore } from '../stores/notifications'
import { examApi, taskApi } from '../api'
import { USE_MOCK, mockStudySession } from '../mock/dashboard'
const store = useNotificationStore(),
  router = useRouter()
const items = ref([]),
  total = ref(0),
  page = ref(1),
  unreadOnly = ref(false)
const loading = ref(false),
  busy = ref(false),
  error = ref(''),
  ready = ref(false),
  savingPrefs = ref(false)
const prefs = reactive({
  enabled: true,
  exam_enabled: true,
  task_enabled: true,
})
const exams = ref([]),
  tasks = ref([]),
  kind = ref('exam'),
  targetId = ref(null),
  dialogVisible = ref(false)
const targets = computed(() =>
  kind.value === 'exam'
    ? exams.value
    : tasks.value.filter(
        (t) => !t.is_done && exams.value.some((e) => e.id === t.exam_id),
      ),
)
async function load(check = false) {
  loading.value = true
  error.value = ''
  try {
    await store.refresh(check)
    if (store.error) throw new Error(store.error)
    const result = await notifications.list({
      page: page.value,
      unread_only: unreadOnly.value,
    })
    if (!result.items.length && page.value > 1) {
      page.value--
      return await load(false)
    }
    items.value = result.items
    total.value = result.total
  } catch (e) {
    error.value = e.message || '通知加载失败，请重试'
  } finally {
    loading.value = false
  }
}
function changeFilter() {
  page.value = 1
  load(false)
}
async function mutate(action) {
  busy.value = true
  try {
    await action()
    await load(false)
  } catch {
    ElMessage.error('操作失败，请重试')
  } finally {
    busy.value = false
  }
}
const mark = (item) => mutate(() => notifications.mark(item.id, !item.is_read))
const readAll = () => mutate(() => notifications.readAll())
async function remove(item) {
  try {
    await ElMessageBox.confirm(
      '删除后不再显示这条通知，同一提醒不会因刷新重新出现。',
      '删除通知',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await mutate(() => notifications.remove(item.id))
}
async function openTarget(item) {
  try {
    await notifications.mark(item.id, true)
    await store.refresh(false)
  } catch {
    return
  }
  router.push({
    path: '/exams',
    query: { [item.target_type === 'exam' ? 'exam' : 'task']: item.target_id },
  })
}
async function savePrefs() {
  savingPrefs.value = true
  try {
    Object.assign(prefs, await notifications.savePreferences({ ...prefs }))
    await load(true)
  } catch {
    ready.value = false
    error.value = '开关保存失败，请刷新页面重新读取设置'
    ElMessage.error('开关保存失败')
  } finally {
    savingPrefs.value = false
  }
}
onMounted(async () => {
  await load(true)
  try {
    const result = await Promise.all([
      notifications.preferences(),
      USE_MOCK ? structuredClone(mockStudySession.exams) : examApi.list(),
      USE_MOCK ? structuredClone(mockStudySession.tasks) : taskApi.list(),
    ])
    Object.assign(prefs, result[0])
    exams.value = result[1]
    tasks.value = result[2]
    ready.value = true
  } catch {
    error.value = '提醒设置加载失败，请刷新重试'
  }
})
</script>
<style scoped>
.notice-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin-bottom: 28px;
}
.eyebrow {
  color: var(--coral-deep);
  font-size: 11px;
  letter-spacing: 2px;
  margin-bottom: 10px;
}
h1 {
  font-family: var(--font-serif);
  font-size: 30px;
}
h1 span {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--ink-2);
  margin-left: 12px;
}
.notice-head p:last-child {
  color: var(--ink-2);
  font-size: 12px;
  margin-top: 12px;
}
.notice-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 290px;
  gap: 28px;
  align-items: start;
}
.history-panel {
  border: 1px solid var(--line-strong);
  background: var(--bg-card);
  border-radius: 10px;
  overflow: hidden;
}
.history-tools {
  padding: 16px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.notice-list {
  list-style: none;
}
.notice-list li {
  padding: 22px;
  border-bottom: 1px solid var(--line);
  border-left: 3px solid transparent;
}
.notice-list li.unread {
  border-left-color: var(--coral);
  background: var(--bg-soft);
}
.notice-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--ink-2);
  font-size: 11px;
  margin-bottom: 12px;
}
.notice-meta span:first-child {
  color: var(--coral-deep);
  font-weight: 700;
}
.notice-list h2 {
  font-size: 16px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.notice-list p {
  margin: 10px 0;
  font-size: 13px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.notice-list small,
.source-gone {
  color: var(--ink-2);
  font-size: 11px;
}
.notice-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 16px;
}
.notice-actions .el-button {
  margin-left: 0;
}
.notice-settings {
  padding: 22px;
  border-top: 3px solid var(--ink-1);
  background: var(--bg-soft);
}
.notice-settings h2 {
  font-family: var(--font-serif);
  font-size: 20px;
  margin-bottom: 18px;
}
.pref-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  margin: 14px 0;
}
.notice-settings p {
  font-size: 12px;
  line-height: 1.8;
  color: var(--ink-2);
}
.configure-item {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--line-strong);
  display: grid;
  gap: 14px;
}
.configure-item h3 {
  font-size: 14px;
}
.delivery-note {
  margin-top: 24px;
}
.notice-error {
  margin-bottom: 20px;
}
.el-pagination {
  padding: 20px;
  justify-content: center;
}
@media (max-width: 760px) {
  .notice-columns {
    grid-template-columns: 1fr;
  }
  .notice-head {
    align-items: start;
  }
  h1 {
    font-size: 25px;
  }
  .notice-list li {
    padding: 16px;
  }
  .notice-meta {
    flex-wrap: wrap;
  }
}
</style>
