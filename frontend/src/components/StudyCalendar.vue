<template>
  <section class="study-calendar" aria-labelledby="calendar-heading" :aria-busy="busy || loading" v-loading="loading">
    <header class="calendar-toolbar">
      <div><p class="calendar-kicker">把复习放进时间里</p><h3 id="calendar-heading">{{ periodTitle }}</h3></div>
      <div class="calendar-controls">
        <el-radio-group v-model="mode" aria-label="日历视图"><el-radio-button value="day">日</el-radio-button><el-radio-button value="week">周</el-radio-button><el-radio-button value="month">月</el-radio-button></el-radio-group>
        <el-select v-model="examFilter" aria-label="日历科目" class="course-filter"><el-option :value="0" label="全部科目" /><el-option v-for="exam in exams" :key="exam.id" :value="exam.id" :label="exam.subject" /></el-select>
        <el-button :disabled="busy || !exams.length" @click="$emit('create', anchor, examFilter)">添加任务</el-button>
      </div>
    </header>
    <div class="calendar-navigation">
      <el-button :aria-label="previousLabel" @click="navigate(-1)">上一{{ unit }}</el-button><el-button @click="anchor = today">今天</el-button><el-button :aria-label="nextLabel" @click="navigate(1)">下一{{ unit }}</el-button>
      <label class="date-jump">定位日期 <input type="date" :value="anchor" aria-label="日历定位日期" @change="changeAnchor($event.target.value)" /></label>
      <span class="calendar-hint">北京时间 · 拖动以 15 分钟定位，时长保持不变</span>
    </div>
    <p v-if="feedback.message" class="move-feedback" :class="feedback.status" role="status" aria-live="polite">{{ feedback.message }}</p>

    <el-calendar v-if="mode === 'month'" v-model="monthDate">
      <template #date-cell="{ data }">
        <div class="month-cell" @dragover.prevent="allowDrop" @drop.prevent="dropOnDate($event, data.day)">
          <span class="month-number">{{ Number(data.day.slice(8)) }}</span>
          <button v-for="exam in examsFor(data.day)" :key="`exam-${exam.id}`" class="month-exam" @click="$emit('edit-exam', exam)">考试 · {{ exam.subject }}</button>
          <button v-for="task in tasksFor(data.day).slice(0, 3)" :key="task.id" class="calendar-task month-task" :style="taskColor(task)" :draggable="!task.is_done && !busy" :disabled="busy" :aria-label="taskLabel(task)" @dragstart="beginDrag($event, task)" @dragend="endDrag" @click="openTask(task)">{{ task.start_time || '待安排' }} · {{ task.title }}</button>
          <button v-if="tasksFor(data.day).length > 3" class="more-tasks" @click="anchor = data.day; mode = 'day'">查看当日全部 {{ tasksFor(data.day).length }} 项</button>
        </div>
      </template>
    </el-calendar>

    <template v-else>
      <div class="date-only-panel">
        <div class="section-label">考试与待安排任务 <span>考试未指定时刻；未定时任务可拖进下方时间轴</span></div>
        <div class="day-shelves" :class="{ week: mode === 'week' }">
          <section v-for="day in days" :key="day" class="day-shelf" :aria-label="`${day} 时间待安排`" @dragover.prevent="allowDrop" @drop.prevent="dropOnDate($event, day, true)">
            <strong>{{ weekday(day) }} · {{ dayHeading(day) }}</strong>
            <button v-for="exam in examsFor(day)" :key="`exam-${exam.id}`" class="month-exam" @click="$emit('edit-exam', exam)">考试 · {{ exam.subject }}</button>
            <button v-for="task in tasksFor(day).filter(t => !t.start_time)" :key="task.id" class="calendar-task shelf-task" :style="taskColor(task)" :draggable="!task.is_done && !busy" :disabled="busy" :aria-label="taskLabel(task)" @dragstart="beginDrag($event, task)" @dragend="endDrag" @click="openTask(task)">{{ task.title }} · {{ task.estimated_minutes }} 分</button>
            <span v-if="!examsFor(day).length && !tasksFor(day).some(t => !t.start_time)" class="shelf-empty">时间待安排区</span>
          </section>
        </div>
      </div>
      <p v-if="!visibleTasks.length && !visibleExams.length" class="calendar-empty">这{{ mode === 'day' ? '天' : '周' }}还没有考试或任务，可以从“添加任务”开始安排。</p>
      <div ref="scrollArea" class="timeline-scroll" tabindex="0" aria-label="24小时时间轴，可滚动；周视图可左右滚动">
        <div class="timeline" :class="{ week: mode === 'week' }" :style="{ '--day-count': days.length }">
          <div class="axis-head">时刻</div>
          <div v-for="day in days" :key="`head-${day}`" class="day-heading" :class="{ today: day === today }"><span>{{ weekday(day) }}</span><strong>{{ dayHeading(day) }}</strong></div>
          <div class="time-axis"><span v-for="hour in 24" :key="hour" :style="{ top: `${(hour - 1) * 48}px` }">{{ minuteLabel((hour - 1) * 60) }}</span></div>
          <section v-for="day in days" :key="day" class="time-column" :data-calendar-day="day" :aria-label="`${day} 固定时段`" @dragover.prevent="hoverTime($event, day)" @dragleave="hover = null" @drop.prevent="dropOnTime($event, day)">
            <div v-if="hover?.day === day" class="drop-indicator" :style="{ top: `${hover.minute * 0.8}px` }">{{ minuteLabel(hover.minute) }}</div>
            <button v-for="item in layoutTimedTasks(tasksFor(day))" :key="item.task.id" class="calendar-task timed-task" :class="{ done: item.task.is_done, compact: item.end - item.start < 75 }" :data-task-id="item.task.id" :style="{ ...taskColor(item.task), top: `${item.start * 0.8}px`, height: `${Math.max(12, (item.end - item.start) * 0.8)}px`, left: `calc(${item.lane / item.columns * 100}% + 2px)`, width: `calc(${100 / item.columns}% - 4px)` }" :draggable="!item.task.is_done && !busy" :disabled="busy" :aria-label="taskLabel(item.task)" :title="taskLabel(item.task)" @dragstart="beginDrag($event, item.task)" @dragend="endDrag" @click="openTask(item.task)"><time>{{ item.task.start_time }}–{{ item.task.end_time }}</time><b>{{ item.task.title }}</b><span>{{ subject(item.task) }}<template v-if="item.task.location"> · {{ item.task.location }}</template></span></button>
          </section>
        </div>
      </div>
      <p class="calendar-footnote">点击任务可精确调整日期或时间，也适用于触屏与键盘。已完成任务保留历史安排，不可拖动。移到“时间待安排区”可清除固定时段。</p>
    </template>

    <el-dialog v-model="adjustVisible" title="移动任务时间" width="min(460px, 94vw)" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :before-close="adjustDraft.beforeClose">
      <template v-if="adjustTask">
        <p class="adjust-title">{{ subject(adjustTask) }} · {{ adjustTask.title }}</p><p class="calendar-footnote">保留 {{ adjustTask.estimated_minutes }} 分钟，只调整本次任务。</p>
        <el-form label-width="88px" @submit.prevent="submitAdjustment">
          <el-form-item label="移动到日期"><el-input v-model="adjust.date" type="date" aria-label="移动到日期" /></el-form-item>
          <el-form-item label="固定时段"><el-switch v-model="adjust.timed" aria-label="移动后固定时段" /></el-form-item>
          <el-form-item v-if="adjust.timed" label="开始时间"><el-input v-model="adjust.time" type="time" step="60" aria-label="移动后开始时间" /></el-form-item>
        </el-form>
        <p v-if="feedback.status === 'error'" class="move-feedback error" role="alert">{{ feedback.message }}</p>
      </template>
      <template #footer><el-button :disabled="busy" @click="adjustDraft.close">取消</el-button><el-button type="primary" :loading="busy" @click="submitAdjustment">确认移动</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useDialogDraft } from '../composables/usePendingWork'
import { addDays, calendarDays, dayHeading, weekday, minuteLabel, dropMinute, moveProposal, layoutTimedTasks } from '../utils/calendar.js'
import { examColor } from '../utils/subjectColor.js'

const props = defineProps({ tasks: { type: Array, required: true }, exams: { type: Array, required: true }, today: { type: String, required: true }, busy: Boolean, loading: Boolean, feedback: { type: Object, default: () => ({}) } })
const emit = defineEmits(['move', 'edit', 'edit-exam', 'create', 'clear-feedback'])
const mode = ref('week'), anchor = ref(props.today), examFilter = ref(0), scrollArea = ref(null), hover = ref(null), dragging = ref(null)
const days = computed(() => calendarDays(anchor.value, mode.value))
const visibleTasks = computed(() => props.tasks.filter(t => days.value.includes(t.plan_date) && (!examFilter.value || t.exam_id === examFilter.value)))
const visibleExams = computed(() => props.exams.filter(e => days.value.includes(e.exam_date) && (!examFilter.value || e.id === examFilter.value)))
const unit = computed(() => ({ day: '日', week: '周', month: '月' }[mode.value]))
const previousLabel = computed(() => `上一${unit.value}`), nextLabel = computed(() => `下一${unit.value}`)
const periodTitle = computed(() => mode.value === 'month' ? `${anchor.value.slice(0, 4)}年${Number(anchor.value.slice(5, 7))}月` : mode.value === 'day' ? `${anchor.value.slice(0, 4)}年${dayHeading(anchor.value)}` : `${days.value[0].slice(0, 4)}年${dayHeading(days.value[0])} — ${dayHeading(days.value[6])}`)
const monthDate = computed({ get: () => new Date(anchor.value + 'T12:00:00'), set: date => { anchor.value = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}` } })
const tasksFor = day => props.tasks.filter(t => t.plan_date === day && (!examFilter.value || t.exam_id === examFilter.value))
const examsFor = day => props.exams.filter(e => e.exam_date === day && (!examFilter.value || e.id === examFilter.value))
const subject = task => props.exams.find(e => e.id === task.exam_id)?.subject || '科目待确认'
const taskColor = task => { const color = examColor(props.exams.find(e => e.id === task.exam_id)); return { '--course-color': color.color, '--course-soft': color.soft } }
const taskLabel = task => `${task.is_done ? '已完成，查看' : '移动或编辑'} ${subject(task)} · ${task.title} · ${task.plan_date} ${task.start_time ? `${task.start_time}至${task.end_time}` : '时间待安排'} · ${task.estimated_minutes}分钟`
const changeAnchor = day => { if (day) anchor.value = day }
function navigate(direction) {
  if (mode.value !== 'month') anchor.value = addDays(anchor.value, direction * (mode.value === 'week' ? 7 : 1))
  else { const date = new Date(anchor.value + 'T12:00:00'); date.setDate(1); date.setMonth(date.getMonth() + direction); monthDate.value = date }
}
let lastDrag = 0, dragOffset = 0, dragOriginY = 0, dragClock = null
function beginDrag(event, task) {
  if (props.busy || task.is_done) { event.preventDefault(); return }
  dragOriginY = event.clientY; dragClock = task.start_time || null
  dragOffset = task.start_time ? event.clientY - event.currentTarget.getBoundingClientRect().top : 0
  dragging.value = moveProposal(task, task.plan_date)
  event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(task.id))
}
function endDrag() { hover.value = null; dragging.value = null; lastDrag = Date.now() }
function proposalFor(day, start) {
  const original = dragging.value
  if (!original || props.busy) return null
  const proposal = { ...original, plan_date: day }
  if (start !== undefined) proposal.start_time = start
  return proposal
}
function dropOnDate(event, day, clearTime = false) { const proposal = proposalFor(day, clearTime ? null : undefined); if (proposal) emit('move', proposal); endDrag() }
function allowDrop(event) { if (dragging.value && !props.busy) event.dataTransfer.dropEffect = 'move' }
function hoverTime(event, day) { allowDrop(event); if (dragging.value && !props.busy) hover.value = { day, minute: dropMinute(event.clientY-event.currentTarget.getBoundingClientRect().top, event.currentTarget.clientHeight, dragClock, dragOffset, event.clientY-dragOriginY) } }
function dropOnTime(event, day) { hoverTime(event, day); const proposal = proposalFor(day, hover.value ? minuteLabel(hover.value.minute) : undefined); if (proposal) emit('move', proposal); endDrag() }
const adjustVisible = ref(false), adjustTask = ref(null), adjust = reactive({ date: '', time: '', timed: false, fingerprint: '' })
const adjustDraft = useDialogDraft(adjust,adjustVisible,computed(() => props.busy),'任务移动')
function openTask(task) {
  if (Date.now() - lastDrag < 250) return
  emit('clear-feedback')
  if (task.is_done) { emit('edit', task); return }
  adjustTask.value = task; Object.assign(adjust, { date: task.plan_date, time: task.start_time || '09:00', timed: !!task.start_time, fingerprint: moveProposal(task, task.plan_date).fingerprint }); adjustVisible.value = true
}
function submitAdjustment() {
  if (!adjustTask.value || props.busy) return
  emit('move', { task_id: adjustTask.value.id, plan_date: adjust.date, fingerprint: adjust.fingerprint, start_time: adjust.timed ? adjust.time : null })
}
watch(() => props.feedback, feedback => { if (feedback.status === 'success' && feedback.task_id === adjustTask.value?.id) adjustVisible.value = false })
async function scrollToDaytime() { await nextTick(); if (scrollArea.value) scrollArea.value.scrollTop = 8*48 }
watch(mode, scrollToDaytime); onMounted(scrollToDaytime)
</script>

<style scoped>
.study-calendar { background: var(--bg-card); border: 1px solid var(--ink-1); border-radius: 14px; overflow: hidden; }
.calendar-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; padding: 22px 22px 14px; }
.calendar-kicker { color: var(--text-low); font-size: 12px; margin: 0 0 5px; }.calendar-toolbar h3 { margin: 0; font-size: 20px; font-variant-numeric: tabular-nums; }
.calendar-controls, .calendar-navigation { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }.course-filter { width: 150px; }
.calendar-navigation { padding: 0 22px 16px; }.calendar-navigation :deep(.el-button + .el-button) { margin-left: 0; }
.date-jump { display: flex; align-items: center; gap: 8px; color: var(--text-mid); font-size: 12px; }.date-jump input { padding: 6px 8px; border: 1px solid var(--line); background: var(--bg-page); color: var(--text-hi); border-radius: 5px; font: inherit; }
.calendar-hint, .calendar-footnote { color: var(--text-low); font-size: 12px; line-height: 1.7; }.calendar-hint { margin-left: auto; }.calendar-footnote { padding: 0 18px; margin: 12px 0; }
.date-only-panel { border-top: 1px solid var(--line); }.section-label { padding: 11px 18px; font-size: 12px; font-weight: 600; }.section-label span { font-weight: 400; color: var(--text-low); margin-left: 10px; }
.day-shelves { display: grid; grid-template-columns: 1fr; max-height: 220px; overflow: auto; }.day-shelves.week { grid-template-columns: repeat(7, minmax(116px, 1fr)); }.date-only-panel { overflow-x: auto; }.day-shelf { padding: 8px; min-height: 60px; border-right: 1px solid var(--line); }.day-shelf > strong { font-size: 11px; color: var(--text-mid); }.shelf-empty { display: block; margin-top: 8px; color: var(--text-low); font-size: 11px; }
.calendar-task, .month-exam { font: inherit; text-align: left; border-radius: 4px; cursor: pointer; }.calendar-task { background: var(--course-soft); border: 1px solid transparent; border-left: 3px solid var(--course-color); color: var(--ink-1); overflow: hidden; }.calendar-task:hover { border-color: var(--course-color); }.calendar-task:focus-visible, .month-exam:focus-visible, .more-tasks:focus-visible { outline: 2px solid var(--coral); outline-offset: 2px; }.calendar-task[draggable=true] { cursor: grab; user-select: none; } .calendar-task > * { pointer-events: none; }.calendar-task:active[draggable=true] { cursor: grabbing; }.calendar-task:disabled { opacity: .6; cursor: wait; }
.shelf-task { display: block; width: 100%; margin-top: 5px; padding: 5px; font-size: 11px; line-height: 1.5; }.month-exam { display: block; background: var(--bg-page); border: 1px solid var(--ink-1); padding: 3px 5px; margin-top: 5px; font-size: 11px; width: 100%; color: var(--text-hi); }
.timeline-scroll { height: min(620px, 68vh); min-height: 320px; overflow: auto; border-top: 1px solid var(--line); overscroll-behavior: contain; }.timeline { display: grid; grid-template-columns: 52px repeat(var(--day-count), minmax(0, 1fr)); min-width: 330px; }.timeline.week { min-width: 865px; }
.axis-head, .day-heading { position: sticky; top: 0; z-index: 3; padding: 10px 6px; background: var(--bg-card); border-bottom: 1px solid var(--ink-1); font-size: 11px; }.axis-head { left: 0; z-index: 4; color: var(--text-low); }.day-heading { display: flex; gap: 5px; flex-wrap: wrap; justify-content: center; }.day-heading strong { font-variant-numeric: tabular-nums; }.day-heading.today { color: var(--coral); }
.time-axis, .time-column { position: relative; height: 1152px; }.time-axis { position: sticky; left: 0; background: var(--bg-card); z-index: 2; font-size: 10px; font-variant-numeric: tabular-nums; color: var(--text-low); }.time-axis span { position: absolute; right: 7px; }.time-column { border-right: 1px solid var(--line); background: repeating-linear-gradient(to bottom, transparent 0, transparent 23px, var(--line) 24px, transparent 25px, transparent 47px, var(--line) 48px); }
.timed-task { position: absolute; z-index: 1; padding: 3px 4px; font-size: 11px; line-height: 1.35; display: flex; flex-direction: column; gap: 2px; }.timed-task time { font-size: 10px; font-variant-numeric: tabular-nums; white-space: nowrap; }.timed-task b { overflow: hidden; text-overflow: ellipsis; }.timed-task > span { font-size: 10px; }.timed-task.compact { flex-direction: row; flex-wrap: nowrap; gap: 4px; } .timed-task.compact time { flex-shrink: 0; } .timed-task.compact b { min-width: 0; white-space: nowrap; text-overflow: ellipsis; }.timed-task.compact > span { display: none; }.timed-task:hover, .timed-task:focus-visible { z-index: 5; min-height: 48px; }.timed-task.done { opacity: .65; }.timed-task.done b { text-decoration: line-through; }.drop-indicator { position: absolute; left: 0; right: 0; border-top: 2px solid var(--coral); color: var(--coral); background: var(--bg-card); z-index: 6; pointer-events: none; font-size: 11px; }
.study-calendar :deep(.el-calendar__header) { display: none; } .study-calendar :deep(.el-calendar-day) { height: auto; min-height: 124px; } .month-cell { min-height: 108px; }.month-number { font-size: 12px; font-weight: 600; }.month-task { display: block; padding: 2px 4px; width: 100%; margin-top: 3px; font-size: 11px; white-space: nowrap; text-overflow: ellipsis; }.more-tasks { font: inherit; border: 0; background: none; padding: 5px 0; color: var(--text-mid); cursor: pointer; font-size: 11px; }.calendar-empty { padding: 8px 18px; color: var(--text-low); font-size: 13px; }.move-feedback { margin: 0; padding: 12px 20px; background: var(--bg-page); border-top: 1px solid var(--line); font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }.move-feedback.error { color: var(--danger, #b63a2e); }.move-feedback.success { color: var(--text-hi); }.adjust-title { font-weight: 600; line-height: 1.6; }
@media (max-width: 680px) { .calendar-toolbar { padding: 16px 12px 10px; }.calendar-toolbar h3 { font-size: 17px; }.calendar-controls { width: 100%; }.calendar-navigation { padding: 0 12px 12px; }.calendar-hint { width: 100%; margin-left: 0; }.section-label span { display: block; margin: 4px 0 0; }.course-filter { width: 130px; }.study-calendar :deep(.el-calendar__body) { overflow-x: auto; padding: 10px; }.study-calendar :deep(.el-calendar-table) { min-width: 700px; } }
</style>
