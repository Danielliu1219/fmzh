import { buildTaskPreview } from './taskDetails.js'

const dayNumber = day => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day || '')) throw new Error('请选择有效日期')
  const value = Date.parse(day + 'T00:00:00Z')
  if (!Number.isFinite(value) || new Date(value).toISOString().slice(0, 10) !== day) throw new Error('日期无效')
  return Math.floor(value / 86400000)
}
const dayString = number => new Date(number * 86400000).toISOString().slice(0, 10)
export const addDays = (day, amount) => dayString(dayNumber(day) + amount)
export function calendarDays(day, mode) {
  const number = dayNumber(day)
  if (mode === 'day') return [day]
  const offset = (new Date(number * 86400000).getUTCDay() + 6) % 7
  return Array.from({ length: 7 }, (_, index) => dayString(number - offset + index))
}
export const dayHeading = day => `${Number(day.slice(5, 7))}月${Number(day.slice(8))}日`
export const weekday = day => ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(dayNumber(day) * 86400000).getUTCDay()]
export const minuteOf = value => {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value || '')) throw new Error('请输入同日 HH:mm 时间')
  return Number(value.slice(0, 2)) * 60 + Number(value.slice(3))
}
export const minuteLabel = value => `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
export const snapMinute = (offset, height) => Math.min(1425, Math.max(0, Math.round(offset / height * 1440 / 15) * 15))
export function dropMinute(offset, height, startTime, grabOffset, deltaY) {
  if (startTime && Math.abs(deltaY) < 4) return minuteOf(startTime)
  return snapMinute(offset - grabOffset, height)
}

const snapshotFields = ['id', 'exam_id', 'title', 'plan_date', 'estimated_minutes', 'priority', 'source', 'is_done', 'start_time', 'end_time', 'location', 'difficulty', 'detail', 'repeat_rule', 'repeat_until', 'repeat_group_id', 'created_at', 'done_at']
export const calendarFingerprint = task => task.move_fingerprint || JSON.stringify(snapshotFields.map(key => task[key] ?? null))
export function moveProposal(task, day, startTime = undefined) {
  dayNumber(day)
  const proposal = { task_id: task.id, plan_date: day, fingerprint: calendarFingerprint(task) }
  if (startTime !== undefined) proposal.start_time = startTime
  return proposal
}
export function moveCandidate(task, proposal) {
  if (calendarFingerprint(task) !== proposal.fingerprint) throw new Error('任务已在其他页面修改，请刷新后重新移动')
  if (task.is_done) throw new Error('已完成任务保留历史安排，不能拖动')
  dayNumber(proposal.plan_date)
  const candidate = { ...task, plan_date: proposal.plan_date }
  if (Object.hasOwn(proposal, 'start_time')) {
    if (proposal.start_time === null) candidate.start_time = candidate.end_time = null
    else {
      const start = minuteOf(proposal.start_time), end = start + task.estimated_minutes
      if (!Number.isInteger(task.estimated_minutes) || task.estimated_minutes < 1 || end > 1439) throw new Error('该时段会跨越午夜，请选择更早的时间或先拆分任务')
      candidate.start_time = proposal.start_time; candidate.end_time = minuteLabel(end)
    }
  }
  return candidate
}
export function previewCalendarMove(task, proposal, tasks, exams, budget) {
  const candidate = moveCandidate(task, proposal)
  const preview = buildTaskPreview({ ...candidate, repeat_rule: 'none', repeat_until: null }, tasks, exams, budget, task.id)
  const existing = tasks.filter(t => t.id !== task.id && t.plan_date === proposal.plan_date).reduce((sum, t) => sum + t.estimated_minutes, 0)
  return { candidate, overlaps: preview.overlaps, can_save: preview.can_save,
    changed: ['plan_date', 'start_time', 'end_time'].some(key => (task[key] || null) !== (candidate[key] || null)),
    budget_exceeded: existing + task.estimated_minutes > budget, existing_minutes: existing, planned_minutes: existing + task.estimated_minutes, limit_minutes: budget }
}
export function applyMockCalendarMove(task, proposal, tasks, exams, budget, allowOverBudget = false) {
  const preview = previewCalendarMove(task, proposal, tasks, exams, budget)
  if (!preview.can_save) throw new Error('任务时段重叠，请调整后重试')
  if (preview.changed && preview.budget_exceeded && !allowOverBudget) throw new Error('目标日期超过全科日预算，请先确认取舍')
  return { ...preview.candidate, ...(task.plan_date !== proposal.plan_date ? { repeat_group_id: null, repeat_rule: 'none', repeat_until: null } : {}) }
}

// 仅展示存量交叠任务的分栏，不更改实际时间；同组的列宽按最大同时占用计算。
export function layoutTimedTasks(tasks) {
  const rows = tasks.filter(t => t.start_time && t.end_time).map(task => ({ task, start: minuteOf(task.start_time), end: minuteOf(task.end_time) }))
    .sort((a, b) => a.start - b.start || a.end - b.end || a.task.id - b.task.id)
  const result = []; let group = [], groupEnd = -1
  const flush = () => {
    const lanes = []
    for (const row of group) {
      let lane = lanes.findIndex(end => end <= row.start)
      if (lane < 0) lane = lanes.length
      lanes[lane] = row.end; row.lane = lane
    }
    result.push(...group.map(row => ({ ...row, columns: lanes.length })))
    group = []
  }
  for (const row of rows) {
    if (group.length && row.start >= groupEnd) { flush(); groupEnd = -1 }
    group.push(row); groupEnd = Math.max(groupEnd, row.end)
  }
  if (group.length) flush()
  return result
}
