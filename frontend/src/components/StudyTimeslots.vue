<template>
  <section class="panel timeslots" aria-labelledby="timeslots-title">
    <header>
      <div><p class="eyebrow">找到适合自己的节奏</p><h2 id="timeslots-title">学习时段推荐</h2></div>
      <div class="controls">
        <label for="timeslot-course">统计范围</label>
        <select id="timeslot-course" v-model="course" @change="load">
          <option value="">全部科目</option>
          <option v-for="exam in exams" :key="exam.id" :value="String(exam.id)">{{ exam.subject }}</option>
        </select>
        <button class="text-button" :disabled="busy" @click="load">{{ busy ? '读取中…' : '更新推荐' }}</button>
      </div>
    </header>
    <p v-if="busy" role="status">正在分析专注记录…</p>
    <div v-else-if="error" role="alert"><p>{{ error }}</p><button class="text-button" @click="load">重试推荐</button></div>
    <template v-else-if="data">
      <p class="summary"><b>{{ data.mode === 'history' ? '根据你的专注习惯' : '记录不足 · 通用参考' }}</b><span>近28天 · {{ data.session_count }}条专注 / {{ data.study_days }}天 / {{ data.history_minutes }}分钟 · {{ data.checkin_count }}次任务打卡</span></p>
      <ol>
        <li v-for="slot in data.slots" :key="slot.start">
          <span class="slot-name">{{ slot.name }}</span><strong>{{ slot.start }}–{{ slot.end }}</strong>
          <b>建议 {{ slot.minutes }} 分钟</b><small>{{ slot.reason }}</small>
        </li>
      </ol>
      <p class="explanation">{{ data.note }}</p>
      <p class="budget">全科每日预算 {{ data.daily_minutes }} 分钟 · 本次建议 {{ data.recommended_minutes }} 分钟<span v-if="data.scope === 'course'"> · 单科查看仍共享全科预算，请勿叠加</span> · 北京时间 {{ data.window_start }} 至 {{ data.window_end }}<span v-if="USE_MOCK"> · 示例记录，刷新恢复</span></p>
    </template>
  </section>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { featureApi } from '../api'
import { USE_MOCK, mockStudySession, getToday } from '../mock/dashboard'
import { recommendTimeslots } from '../utils/timeslots'

const props = defineProps({ exams: { type: Array, default: () => [] }, revision: { type: Number, default: 0 } })
const course = ref(''), data = ref(null), busy = ref(false), error = ref('')
let request = 0
async function load() {
  const current = ++request
  busy.value = true
  error.value = ''
  data.value = null
  try {
    const params = course.value ? { exam_id: Number(course.value) } : {}
    const result = USE_MOCK ? recommendTimeslots(mockStudySession.sessions, mockStudySession.tasks, mockStudySession.daily_minutes, `${getToday()}T23:59:59`, params.exam_id) : await featureApi.timeslots(params)
    if (current === request) data.value = result
  } catch (e) {
    if (current === request) error.value = e?.message || '学习时段暂时无法加载，请重试。'
  } finally { if (current === request) busy.value = false }
}
watch(() => [props.revision, props.exams.map(e => e.id).join(',')], () => {
  if (course.value && !props.exams.some(e => String(e.id) === course.value)) course.value = ''
  load()
}, { immediate: true })
onBeforeUnmount(() => { request++ })
</script>

<style scoped>
.timeslots { margin: 28px 0; }
header, .controls { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
header { justify-content:space-between; }
h2 { margin:4px 0 0; font-size:22px; }
.controls { font-size:12px; }
select { max-width:180px; padding:8px; color:inherit; font:inherit; background:var(--paper); border:1px solid var(--line); border-radius:6px; }
.text-button { border:0; padding:8px 0; background:transparent; color:var(--coral-deep); font:inherit; cursor:pointer; text-decoration:underline; text-underline-offset:4px; }
.text-button:disabled { opacity:.5; cursor:wait; }
select:focus-visible, .text-button:focus-visible { outline:2px solid var(--coral-deep); outline-offset:3px; }
.summary { display:flex; gap:12px; flex-wrap:wrap; margin:22px 0 16px; font-size:13px; }
.summary span, .explanation, .budget { color:var(--ink-3); line-height:1.8; }
ol { margin:0; padding:0; list-style:none; border-top:1px solid var(--line); }
li { display:grid; grid-template-columns:90px 180px 140px minmax(0,1fr); align-items:center; gap:12px; padding:18px 0; border-bottom:1px solid var(--line); }
.slot-name { font-size:11px; color:var(--ink-3); }
li strong { font-size:22px; font-variant-numeric:tabular-nums; }
li b { font-size:13px; font-weight:500; }
li small { font-size:12px; line-height:1.7; color:var(--ink-3); }
.explanation { font-size:13px; margin-bottom:8px; }
.budget { font-size:11px; margin-bottom:0; }
@media(max-width:900px) { li { grid-template-columns:80px 1fr; } li b, li small { grid-column:1 / -1; } }
@media(max-width:760px) { .timeslots { padding:20px; } .controls { gap:8px; } li { gap:8px; } li strong { font-size:20px; } }
</style>
