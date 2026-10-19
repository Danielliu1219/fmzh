import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { clearSession, readSession } from '../src/utils/session.js'
import { readMistake, answerLabel, validQuizDraft } from '../src/utils/quiz.js'
import { mockNotebook, startMockQuiz, submitMockQuiz, resetMockQuizzes, saveMockQuizDraft, mockQuizDetail } from '../src/mock/quizzes.js'

beforeEach(() => {
  globalThis.localStorage = {
    getItem(key) { return Object.hasOwn(this, key) ? this[key] : null },
    setItem(key, value) { this[key] = String(value) },
    removeItem(key) { delete this[key] },
  }
  resetMockQuizzes()
})

test('损坏或不完整的登录缓存会清理，不阻断路由', () => {
  localStorage.setItem('fmzh_token', 'old')
  localStorage.setItem('fmzh_user', '{bad json')
  assert.deepEqual(readSession(), { token: '', user: null })
  assert.equal(localStorage.getItem('fmzh_token'), null)
})

test('退出清理自测草稿，保留教程设置和无关本地数据', () => {
  localStorage.setItem('fmzh_token', 'old')
  localStorage.setItem('fmzh_quiz_draft:old:attempt', 'answers')
  localStorage.setItem('fmzh_onboarding_v2:old', 'done')
  clearSession()
  assert.equal(localStorage.getItem('fmzh_quiz_draft:old:attempt'), null)
  assert.equal(localStorage.getItem('fmzh_onboarding_v2:old'), 'done')
})

test('错题详情兼容历史纯文本，答案可读', () => {
  assert.deepEqual(readMistake('旧解析'), { raw: '旧解析' })
  assert.equal(answerLabel('false', { kind: 'boolean' }), '错误')
  assert.equal(answerLabel(['A', 'C']), 'A、C')
  assert.equal(answerLabel(''), '未作答')
})

test('损坏的自测草稿不恢复，避免隐藏的非法选项阻止提交', () => {
  const questions = [{ kind: 'multiple', options: [{ value: 'A' }, { value: 'B' }] }]
  assert.equal(validQuizDraft([['A']], questions), true)
  assert.equal(validQuizDraft([['Z']], questions), false)
  assert.equal(validQuizDraft(['A'], questions), false)
})

test('演示自测作答后错题跨页面共享，并对重复题去重', () => {
  const raw = [{ question: '题目', options: ['A. 错', 'B. 对'], answer: 'B', analysis: '解析' }]
  const attempt = startMockQuiz('analysis', '高数', raw)
  assert.equal('answer' in attempt.questions[0], false)
  saveMockQuizDraft(attempt.id, ['A'])
  assert.deepEqual(mockQuizDetail(attempt.id).draft_answers, ['A'])
  const result = submitMockQuiz(attempt.id, ['A'])
  assert.equal(result.result.score, 0)
  assert.equal(mockNotebook.value.filter(c => c.item_type === 'question').length, 1)
  const again = startMockQuiz('analysis', '高数', raw)
  assert.equal(submitMockQuiz(again.id, ['A']).result.mistakes_added, 0)
  assert.equal(mockNotebook.value.filter(c => c.item_type === 'question').length, 1)
})
