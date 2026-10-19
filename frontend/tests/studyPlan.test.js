import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildStudyPlan,
  applyStudyPlan,
  buildReliefPreview,
} from '../src/utils/studyPlan.js'
const exams = [
  { id: 1, exam_date: '2026-10-20' },
  { id: 2, exam_date: '2026-10-21' },
  { id: 3, exam_date: '2026-10-22' },
]
const task = (id, exam_id, estimated_minutes, extra = {}) => ({
  id,
  exam_id,
  estimated_minutes,
  plan_date: '2026-10-17',
  title: `task ${id}`,
  source: 'ai',
  is_done: false,
  priority: 2,
  ...extra,
})
test('跨科计划共享每日容量，保持总工作量和截止日', () => {
  const plan = buildStudyPlan(
    [task(1, 1, 300), task(2, 2, 240), task(3, 3, 180)],
    exams,
    240,
    '2026-10-17',
  )
  assert.equal(plan.conflicts.length, 0)
  assert.ok(plan.days.every((d) => d.minutes <= 240))
  assert.equal(
    plan.assignments.reduce((n, a) => n + a.minutes, 0),
    720,
  )
  assert.ok(
    new Set(
      plan.assignments
        .filter((a) => a.date === '2026-10-17')
        .map((a) => a.exam_id),
    ).size > 1,
  )
  assert.ok(
    plan.assignments.every(
      (a) => a.date < exams.find((e) => e.id === a.exam_id).exam_date,
    ),
  )
})
test('超长任务拆分并保留原身份；完成与手动记录不移动', () => {
  const tasks = [
    task(1, 1, 360),
    task(2, 2, 30, { source: 'manual', plan_date: '2026-10-19' }),
    task(3, 2, 40, { is_done: true, plan_date: '2026-10-16' }),
  ]
  const plan = buildStudyPlan(tasks, exams, 130, '2026-10-17'),
    applied = applyStudyPlan(tasks, plan)
  assert.equal(plan.conflicts.length, 0)
  assert.equal(
    applied
      .filter((t) => t.source === 'ai' && !t.is_done)
      .reduce((n, t) => n + t.estimated_minutes, 0),
    360,
  )
  assert.deepEqual(
    applied.find((t) => t.id === 2),
    tasks[1],
  )
  assert.deepEqual(
    applied.find((t) => t.id === 3),
    tasks[2],
  )
  assert.equal(new Set(applied.map((t) => t.id)).size, applied.length)
})
test('容量不足明确列出缺口，不能确认部分结果', () => {
  const tasks = [task(1, 1, 800)],
    plan = buildStudyPlan(tasks, exams, 120, '2026-10-17')
  assert.ok(plan.conflicts.length)
  assert.equal(
    plan.assignments.reduce((n, a) => n + a.minutes, 0) +
      plan.conflicts.reduce((n, c) => n + c.minutes, 0),
    800,
  )
  assert.throws(() => applyStudyPlan(tasks, plan))
})

test('减负沿用全科预算，不把超长任务硬塞进容量', () => {
  const plan = buildReliefPreview(
    [task(1, 1, 360)],
    exams,
    120,
    '2026-10-17',
    'lighten',
  )
  assert.equal(plan.today_capacity, 60)
  assert.ok(plan.conflicts.length)
  assert.equal(plan.moves.length, 0)
})
test('减负给已完成任务保留时间，后移任务有真实 ID 和日期', () => {
  const tasks = [task(1, 1, 90), task(2, 2, 45, { is_done: true })]
  const plan = buildReliefPreview(tasks, exams, 120, '2026-10-17', 'lighten')
  assert.equal(plan.conflicts.length, 0)
  assert.equal(plan.moves[0].task_id, 1)
  assert.ok(plan.moves[0].to_date > '2026-10-17')
})
