import test from 'node:test'
import assert from 'node:assert/strict'
import { feedbackReplan } from '../src/utils/replan.js'
import { applyStudyPlan } from '../src/utils/studyPlan.js'

const today = '2026-10-19'
const exams = [{ id: 1, subject: '数学', exam_date: '2026-10-22' }, { id: 2, subject: '英语', exam_date: '2026-10-23' }]
const result = { course: '数学', knowledge_points: [{ name: '积分', weight: 0.7 }] }
const tasks = [
  { id: 1, exam_id: 1, title: '手动', plan_date: today, estimated_minutes: 45, source: 'manual', is_done: false, priority: 2 },
  { id: 2, exam_id: 1, title: '积分', plan_date: today, estimated_minutes: 90, source: 'ai', is_done: false, priority: 2 },
]
test('反馈重排保留手动占用和原工作量，追加练习也不得突破全科预算', () => {
  const mistakes = [{ subject: '数学', knowledge_point: '积分', correct: false }]
  const preview = feedbackReplan(result, 1, tasks, exams, 60, today, mistakes)
  assert.equal(preview.scheduling.conflicts.length, 0)
  assert.ok(preview.scheduling.days.every(d => d.minutes <= 60))
  const applied = applyStudyPlan(preview.candidate, preview.scheduling)
  assert.equal(applied.filter(t => t.source === 'ai').reduce((n, t) => n + t.estimated_minutes, 0), 120)
  assert.equal(applied.find(t => t.id === 1).estimated_minutes, 45)
  const saved = { ...result, replan_base_weights: preview.base, replan_feedback_key: preview.feedbackKey }
  const next = feedbackReplan(saved, 1, applied, exams, 60, today, mistakes)
  assert.equal(next.candidate.reduce((n, t) => n + t.estimated_minutes, 0), 165)
})
test('其他课程的同名错题不增加当前课程负担', () => {
  const preview = feedbackReplan(result, 1, tasks, exams, 60, today, [{ subject: '英语', knowledge_point: '积分', correct: false }])
  assert.equal(preview.wrong_questions, 0)
  assert.equal(preview.candidate.length, tasks.length)
})
test('过期考试拒绝重排，容量不足给出冲突', () => {
  assert.throws(() => feedbackReplan(result, 1, tasks, exams, 60, '2026-10-23'), /已经结束/)
  const preview = feedbackReplan(result, 1, tasks, [{ ...exams[0], exam_date: '2026-10-20' }], 60, today)
  assert.ok(preview.scheduling.conflicts.length)
})
