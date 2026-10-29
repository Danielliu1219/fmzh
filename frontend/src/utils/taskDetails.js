export const difficultyLabels = { easy: '简单', medium: '适中', hard: '较难' }
export const repeatLabels = { none: '单次', daily: '每天', weekdays: '工作日', weekly: '每周' }
const dayNumber = day => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day || '')) throw new Error('请选择有效日期')
  const value = Date.parse(day + 'T00:00:00Z')
  if (!Number.isFinite(value) || new Date(value).toISOString().slice(0, 10) !== day) throw new Error('日期无效')
  return Math.floor(value / 86400000)
}
const dayString = day => new Date(day * 86400000).toISOString().slice(0, 10)

export function timeDuration(start, end) {
  const missing = value => value === null || value === undefined || value === ''
  if (missing(start) && missing(end)) return null
  if (missing(start) || missing(end)) throw new Error('开始时间和结束时间需一起填写，或一起清空')
  const minutes = value => {
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) throw new Error('任务时间请使用 HH:mm，按北京时间填写')
    return Number(value.slice(0, 2)) * 60 + Number(value.slice(3))
  }
  const result = minutes(end) - minutes(start)
  if (result <= 0) throw new Error('结束时间需晚于开始时间；跨午夜任务请拆成两天')
  return result
}

export function occurrenceDates(start, rule = 'none', until = null) {
  const first = dayNumber(start)
  if (!Object.hasOwn(repeatLabels, rule)) throw new Error('不支持的重复规则')
  if (rule === 'none') {
    if (until) throw new Error('单次任务不需要重复截止日')
    return [start]
  }
  if (!until || dayNumber(until) < first) throw new Error('重复截止日需填写，且不能早于开始日期')
  const last = dayNumber(until)
  if (last - first > 365) throw new Error('重复任务的日期范围最多一年')
  const dates = []
  for (let day = first; day <= last; day++) {
    const weekday = new Date(day * 86400000).getUTCDay()
    if (rule === 'daily' || (rule === 'weekdays' && weekday >= 1 && weekday <= 5) || (rule === 'weekly' && (day - first) % 7 === 0)) dates.push(dayString(day))
    if (dates.length > 180) throw new Error('一次最多创建180项重复任务，请缩短截止日期')
  }
  if (!dates.length) throw new Error('该日期范围内没有符合重复规则的日期')
  return dates
}

export function normalizeTask(payload) {
  const item = { ...payload, title: String(payload.title || '').trim(), location: String(payload.location || '').trim(), detail: String(payload.detail || '').trim(),
    start_time: payload.start_time || null, end_time: payload.end_time || null, difficulty: payload.difficulty || 'medium', repeat_rule: payload.repeat_rule || 'none', repeat_until: payload.repeat_until || null }
  if (!item.title || item.title.length > 256) throw new Error('任务名称需为1～256字')
  if (item.location.length > 120 || item.detail.length > 2000) throw new Error('地点最多120字，说明最多2000字')
  if (!Object.hasOwn(difficultyLabels, item.difficulty)) throw new Error('不支持的任务难度')
  const duration = timeDuration(item.start_time, item.end_time)
  item.estimated_minutes = duration ?? Number(item.estimated_minutes)
  if (!Number.isInteger(item.estimated_minutes) || item.estimated_minutes < 1 || item.estimated_minutes > 1440) throw new Error('预计时长需为1～1440分钟')
  if (![1, 2, 3].includes(item.priority)) throw new Error('优先级无效')
  return item
}

export function buildTaskPreview(payload, tasks, exams, budget, excludeId = null) {
  const item = normalizeTask(payload)
  const exam = exams.find(e => e.id === item.exam_id)
  if (!exam) throw new Error('请选择有效科目')
  const dates = occurrenceDates(item.plan_date, item.repeat_rule, item.repeat_until)
  if ((item.repeat_until || item.plan_date) > exam.exam_date) throw new Error('任务日期和重复截止日不能晚于考试日期')
  const items = dates.map(plan_date => ({ ...item, plan_date }))
  const warnings = dates.flatMap(day => {
    const existing = tasks.filter(t => t.id !== excludeId && t.plan_date === day).reduce((sum, t) => sum + t.estimated_minutes, 0)
    return existing + item.estimated_minutes > budget ? [{ date: day, existing_minutes: existing, planned_minutes: existing + item.estimated_minutes, limit_minutes: budget, reason: '全科当日总时长超过预算，请确认取舍' }] : []
  })
  return { count: items.length, total_minutes: items.length * item.estimated_minutes, items, warnings,
    note: '预览不保存；每个重复日期会生成一项任务，可单独打卡和编辑。请核对日期、时段及预算。' }
}

export function mockTaskInstances(preview, existingTasks, groupId) {
  const firstId = Math.max(0, ...existingTasks.map(t => t.id)) + 1
  return preview.items.map((item, i) => ({ ...item, id: firstId + i, is_done: false, done_at: null, source: 'manual', sort_order: i, repeat_group_id: item.repeat_rule === 'none' ? null : groupId }))
}

export const taskTimeLabel = task => task.start_time && task.end_time ? `${task.start_time.slice(0, 5)}–${task.end_time.slice(0, 5)}` : '时间待安排'
export const taskRepeatLabel = task => !task.repeat_group_id || task.repeat_rule === 'none' ? '单次' : `${repeatLabels[task.repeat_rule] || '重复'}${task.repeat_until ? '至' + task.repeat_until : ''}`
