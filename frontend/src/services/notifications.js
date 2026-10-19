import { notificationApi } from '../api'
import { USE_MOCK, getToday, mockStudySession } from '../mock/dashboard'
import { reminderDate } from '../utils/reminders'
export { reminderDate, notificationTime } from '../utils/reminders'

let scenario, prefs, rules, records, nextId
function resetDemo() {
  scenario = mockStudySession.scenario
  prefs = { enabled: true, exam_enabled: true, task_enabled: true }
  rules = new Map()
  records = []
  nextId = 1
  if (mockStudySession.exams.some((e) => e.id === 1))
    rules.set('exam:1', {
      enabled: true,
      event_time: '09:00',
      advance_minutes: 10080,
    })
  if (mockStudySession.tasks.some((t) => t.id === 1))
    rules.set('task:1', {
      enabled: true,
      event_time: '09:00',
      advance_minutes: 15,
    })
}
function ensureDemo() {
  if (!rules || scenario !== mockStudySession.scenario) resetDemo()
}
function source(kind, id) {
  const row = (
    kind === 'exam' ? mockStudySession.exams : mockStudySession.tasks
  ).find((r) => r.id === id)
  if (
    !row ||
    (kind === 'task' &&
      !mockStudySession.exams.some((e) => e.id === row.exam_id))
  )
    throw new Error('考试或任务已不存在')
  return row
}
function ruleData(kind, id) {
  const row = source(kind, id)
  const rule = rules.get(`${kind}:${id}`) || {
    enabled: false,
    event_time: '09:00',
    advance_minutes: kind === 'exam' ? 1440 : 15,
  }
  const day = kind === 'exam' ? row.exam_date : row.plan_date
  return {
    ...rule,
    target_type: kind,
    target_id: id,
    title: row.subject || row.title,
    event_date: day,
    due_at: reminderDate(day, rule.event_time, rule.advance_minutes),
    timezone: 'Asia/Shanghai',
  }
}
const demo = {
  async check() {
    ensureDemo()
    let created = 0
    if (!prefs.enabled) return { created }
    const now = `${getToday()}T12:00:00+08:00`
    for (const [key, rule] of rules) {
      const [kind, id] = key.split(':')
      if (!rule.enabled || !prefs[`${kind}_enabled`]) continue
      let row
      try {
        row = source(kind, Number(id))
      } catch {
        continue
      }
      if (
        (kind === 'task' && row.is_done) ||
        (kind === 'exam' && row.exam_date < getToday())
      )
        continue
      const data = ruleData(kind, Number(id))
      const occurrence = `${key}:${data.due_at}`
      if (
        Date.parse(data.due_at) > Date.parse(now) ||
        records.some((n) => n.occurrence === occurrence)
      )
        continue
      const label = kind === 'exam' ? '考试' : '复习任务'
      records.unshift({
        id: nextId++,
        occurrence,
        target_type: kind,
        target_id: Number(id),
        title: `${label}提醒 · ${data.title}`.slice(0, 50),
        content: `${data.title}：${data.event_date} ${data.event_time}。已到你设置的提醒时间，请查看安排。`,
        due_at: data.due_at,
        created_at: new Date(now).toISOString(),
        is_read: false,
        deleted: false,
      })
      created++
    }
    return { created }
  },
  async list({ page = 1, page_size = 20, unread_only = false } = {}) {
    ensureDemo()
    const visible = records.filter((n) => !n.deleted)
    const filtered = visible.filter((n) => !unread_only || !n.is_read)
    return {
      unread_count: visible.filter((n) => !n.is_read).length,
      total: filtered.length,
      page,
      page_size,
      items: filtered
        .slice((page - 1) * page_size, page * page_size)
        .map((n) => {
          let available = true
          try {
            source(n.target_type, n.target_id)
          } catch {
            available = false
          }
          return { ...n, target_available: available }
        }),
    }
  },
  async preferences() {
    ensureDemo()
    return { ...prefs }
  },
  async savePreferences(data) {
    ensureDemo()
    prefs = { ...data }
    return { ...prefs }
  },
  async reminder(kind, id) {
    ensureDemo()
    return ruleData(kind, id)
  },
  async saveReminder(kind, id, data) {
    ensureDemo()
    source(kind, id)
    rules.set(`${kind}:${id}`, { ...data })
    return ruleData(kind, id)
  },
  async mark(id, is_read) {
    const n = records.find((n) => n.id === id && !n.deleted)
    if (n) n.is_read = is_read
  },
  async readAll() {
    records.forEach((n) => {
      n.is_read = true
    })
  },
  async remove(id) {
    const n = records.find((n) => n.id === id)
    if (n) n.deleted = true
  },
}
export const notifications = USE_MOCK ? demo : notificationApi
