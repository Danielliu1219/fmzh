import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildMastery } from '../src/utils/mastery.js'
import { mockMastery, startMockQuiz, submitMockQuiz, resetMockQuizzes } from '../src/mock/quizzes.js'

const attempt = (id, day, items, status = 'submitted') => ({ id, created_at: day, submitted_at: day, status, result: { items } })
const item = (knowledge_point, question, correct, unanswered = false) => ({ knowledge_point, question, correct, unanswered })

test('没有记录和未交卷的草稿均显示未测，不把空数据标为掌握', () => {
  const points = buildMastery(['积分'], [attempt('draft', '2026-10-26', [item('积分', '题目', true)], 'active')])
  assert.equal(points[0].status, 'untested')
  assert.equal(points[0].score, null)
})

test('按知识点最近一次覆盖取证，旧错题不覆盖新答对，未答计错', () => {
  const points = buildMastery(['积分', '极限', '级数'], [
    attempt('old', '2026-10-25', [item('积分', '旧题', false), item('极限', '空题', false, true)]),
    attempt('new', '2026-10-26', [item('积分', '新题', true)]),
  ])
  assert.equal(points[0].status, 'mastered')
  assert.equal(points[0].attempt_id, 'new')
  assert.equal(points[1].status, 'weak')
  assert.equal(points[1].evidence[0].unanswered, true)
  assert.equal(points[2].status, 'untested')
})

test('80%边界与重复题去重，证据只包含题目和判分结果', () => {
  const questions = [true, true, true, true, false].map((correct, i) => item('积分', '题' + i, correct))
  const point = buildMastery(['积分'], [attempt('a', '2026-10-26', [...questions, questions[0]])])[0]
  assert.equal(point.total, 5)
  assert.equal(point.score, 80)
  assert.equal(point.status, 'mastered')
})

test('演示模式自测提交后更新对应科目，其他科目保持未测', () => {
  resetMockQuizzes()
  const quiz = startMockQuiz(1, '数学', [{ question: '积分题', kind: 'fill', knowledge_point: '积分', answer: '42' }])
  submitMockQuiz(quiz.id, ['42'])
  assert.equal(mockMastery('数学', ['积分'])[0].status, 'mastered')
  assert.equal(mockMastery('英语', ['积分'])[0].status, 'untested')
})
