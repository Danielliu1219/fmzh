import { buildStudyPlan } from './studyPlan.js'

// 静态演示也使用同一全科容量规则，保持已有工作量和账号内课程边界。
export function feedbackReplan(result, examId, tasks, exams, dailyMinutes, today, mistakes = []) {
  const exam = exams.find(e => e.id === examId)
  if (!exam || exam.exam_date < today) throw new Error('该考试已经结束，不能再安排备考任务')
  const own = tasks.filter(t => t.exam_id === examId && t.source === 'ai')
  const done = own.filter(t => t.is_done).length
  const counts = {}
  mistakes.forEach(item => {
    if (item.subject === result.course && !item.correct && item.knowledge_point) {
      counts[item.knowledge_point] = (counts[item.knowledge_point] || 0) + 1
    }
  })
  const base = result.replan_base_weights || Object.fromEntries(result.knowledge_points.map(k => [k.name, k.weight]))
  const daysLeft = Math.round((Date.parse(exam.exam_date + 'T00:00:00Z') - Date.parse(today + 'T00:00:00Z')) / 86400000)
  const weights = result.knowledge_points.map(k => {
    const errors = counts[k.name] || 0
    let weight = base[k.name] + Math.min(0.3, errors * 0.08)
    if (own.length && done / own.length < 0.5 && base[k.name] >= 0.6) weight += 0.03
    if (daysLeft <= 3 && base[k.name] < 0.6 && !errors) weight -= 0.08
    return { name: k.name, old_weight: k.weight, new_weight: Math.max(0.05, Math.min(1, Math.round(weight * 100) / 100)), reason: errors ? `当前科目自测错题 ${errors} 道，优先巩固` : '结合完成进度与剩余天数调整' }
  }).sort((a, b) => b.new_weight - a.new_weight)
  const priorities = {}
  const candidate = tasks.map(task => {
    if (task.exam_id !== examId || task.source !== 'ai' || task.is_done) return { ...task }
    const matches = weights.filter(w => task.title.includes(w.name) || w.name.includes(task.title))
    const weight = Math.max(...matches.map(w => w.new_weight))
    const priority = matches.length ? (weight >= 0.7 ? 1 : weight >= 0.45 ? 2 : 3) : task.priority
    priorities[task.id] = priority
    return { ...task, priority }
  })
  const feedbackKey = JSON.stringify(mistakes)
  let nextId = Math.max(0, ...tasks.map(t => t.id)) + 1
  if (mistakes.length && feedbackKey !== result.replan_feedback_key) {
    weights.forEach(weight => {
      const title = `专项练习：${weight.name}`
      if (counts[weight.name] && !own.some(t => t.title === title && !t.is_done)) {
        candidate.push({ id: nextId++, exam_id: examId, title, plan_date: today, estimated_minutes: 30, priority: 1, source: 'ai', is_done: false, exam: result.course })
      }
    })
  }
  const scheduling = buildStudyPlan(candidate, exams, dailyMinutes, today)
  const fingerprint = JSON.stringify([result, tasks, exams, dailyMinutes, today, mistakes])
  const plan = scheduling.assignments.filter(a => a.exam_id === examId).map(a => ({
    day: Math.round((Date.parse(a.date + 'T00:00:00Z') - Date.parse(today + 'T00:00:00Z')) / 86400000) + 1,
    date: a.date, title: a.title, estimated_minutes: a.minutes,
    priority: candidate.find(t => t.id === a.task_id)?.priority || 2,
    detail: '依据当前学习反馈在全科共享预算内调整',
  }))
  plan.push(...own.filter(t => !t.is_done && t.start_time).map(t => ({
    day: Math.round((Date.parse(t.plan_date+'T00:00:00Z')-Date.parse(today+'T00:00:00Z'))/86400000)+1,
    date: t.plan_date, title: t.title, estimated_minutes: t.estimated_minutes, priority: priorities[t.id] || t.priority,
    detail: `保留固定时段 ${t.start_time}–${t.end_time}；${t.detail || ''}`,
  })))
  plan.sort((a, b) => a.date.localeCompare(b.date) || a.priority-b.priority)
  return { exam_id: examId, days_left: daysLeft, weights, plan, scheduling, fingerprint, priorities, base, candidate, feedbackKey, done_tasks: done, total_tasks: own.length, completion_rate: own.length ? done / own.length : 0, wrong_questions: Object.values(counts).reduce((a, b) => a + b, 0), applied: false, note: '演示预览：保留手动与已完成任务，按反馈追加针对性练习，统一校验全科容量；同一批反馈不会重复追加，有冲突时不能应用。' }
}
