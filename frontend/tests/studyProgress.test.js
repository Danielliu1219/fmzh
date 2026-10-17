import test from 'node:test'
import assert from 'node:assert/strict'
import {
  checkinHistory,
  daysUntil,
  taskProgress,
} from '../src/utils/studyProgress.js'

test('task progress handles empty, partial, complete and undone task lists', () => {
  assert.deepEqual(taskProgress([]), { total: 0, done: 0, rate: 0 })
  const tasks = Array.from({ length: 8 }, (_, i) => ({ is_done: i < 3 }))
  assert.equal(taskProgress(tasks).rate, 0.375)
  tasks[3].is_done = true
  assert.equal(taskProgress(tasks).rate, 0.5)
  tasks.forEach((task) => {
    task.is_done = true
  })
  assert.equal(taskProgress(tasks).rate, 1)
  tasks.forEach((task) => {
    task.is_done = false
  })
  assert.equal(taskProgress(tasks).rate, 0)
})

test('check-in dates use completion time rather than planned date', () => {
  const tasks = [
    { is_done: true, plan_date: '2026-10-22', done_at: '2026-10-17T09:00:00' },
    { is_done: true, plan_date: '2026-10-01', done_at: '2026-10-16T18:00:00' },
    { is_done: true, plan_date: '2026-10-17', done_at: null },
    { is_done: false, done_at: '2026-10-15T18:00:00' },
  ]
  const history = checkinHistory(tasks, '2026-10-17')
  assert.equal(history.streak, 2)
  assert.deepEqual(
    history.week.filter((day) => day.done).map((day) => day.date),
    ['2026-10-16', '2026-10-17'],
  )
  assert.equal(history.week.find((day) => day.today).date, '2026-10-17')
  assert.equal(history.week.at(-1).future, true)
})

test('unfinished today preserves yesterday streak, gaps break it, undo removes evidence', () => {
  const tasks = [
    { is_done: true, done_at: '2026-10-16T18:00:00' },
    { is_done: true, done_at: '2026-10-14T18:00:00' },
  ]
  assert.equal(checkinHistory(tasks, '2026-10-17').streak, 1)
  tasks[0].is_done = false
  assert.equal(checkinHistory(tasks, '2026-10-17').streak, 0)
  assert.equal(checkinHistory([], '2026-10-17').week.length, 7)
})

test('calendar countdown distinguishes past exams, today and month boundaries', () => {
  assert.equal(daysUntil('2026-10-16', '2026-10-17'), -1)
  assert.equal(daysUntil('2026-10-17', '2026-10-17'), 0)
  assert.equal(daysUntil('2026-11-01', '2026-10-17'), 15)
  assert.equal(daysUntil('2028-03-01', '2028-02-28'), 2)
})
