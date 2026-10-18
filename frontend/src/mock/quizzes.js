// 静态 Pages 演示：仅在当前会话保存，与真实后端判分分开。
import { ref } from 'vue'

export const mockNotebook = ref([
  { id: 1, item_type: 'material', material_id: 2, title: '极限与连续 老师标注重点', content: '', source: 'manual', created_at: '2026-10-12T10:00:00' },
])
const attempts = new Map()
export const mockAnalysisSessions = new Map()
const normalize = (s) => String(s).normalize('NFKC').trim().replace(/\s+/g, ' ')
const publicAttempt = (a) => ({ ...a, questions: a.questions.map(({ answer, analysis, accepted_answers, ...q }) => q) })

export function mockQuizHistory(analysisId) {
  return [...attempts.values()].filter(a => a.analysis_id === analysisId).reverse().map(a => ({ id: a.id, status: a.status, created_at: a.created_at, score: a.result?.score ?? null }))
}
export function mockQuizDetail(id) { return structuredClone(publicAttempt(attempts.get(id))) }
export function saveMockQuizDraft(id, answers) {
  const attempt = attempts.get(id)
  if (attempt?.status === 'active') attempt.draft_answers = JSON.parse(JSON.stringify(answers))
}
export function startMockQuiz(analysisId, subject, raw) {
  const questions = raw.map((q, index) => ({
    ...JSON.parse(JSON.stringify(q)), index, kind: q.kind || (q.options?.length ? 'single' : 'fill'),
    options: (q.options || []).map((o, i) => ({ value: String.fromCharCode(65+i), label: o.replace(/^[A-Z][.、:：)]\s*/, '') })),
  }))
  const a = { id: crypto.randomUUID(), analysis_id: analysisId, subject, questions, status: 'active', created_at: new Date().toISOString(), result: null }
  attempts.set(a.id, a)
  return mockQuizDetail(a.id)
}
export function submitMockQuiz(id, answers) {
  const a = attempts.get(id)
  if (a.status === 'submitted') return mockQuizDetail(id)
  let added = 0
  const items = a.questions.map((q, index) => {
    let answer = answers[index]
    let expected = q.answer
    if (q.kind === 'multiple') {
      answer = [...answer].sort()
      expected = (Array.isArray(expected) ? expected : expected.split(/[,、]/)).sort()
    } else {
      answer = normalize(answer)
      expected = normalize(expected)
    }
    const unanswered = answer === '' || (Array.isArray(answer) && !answer.length)
    const correct = !unanswered && (JSON.stringify(answer) === JSON.stringify(expected) || (q.kind === 'fill' && (q.accepted_answers || []).map(normalize).includes(answer)))
    const item = { ...q, answer: expected, submitted_answer: answer, correct, unanswered }
    if (!correct && !mockNotebook.value.some(c => c.item_type === 'question' && normalize(c.title) === normalize(q.question))) {
      mockNotebook.value.unshift({ id: Date.now()+index, item_type: 'question', material_id: null, title: q.question, source: 'quiz', content: JSON.stringify({ ...item, subject: a.subject }), created_at: new Date().toISOString() })
      added++
    }
    return item
  })
  const correct = items.filter(q => q.correct).length
  a.status = 'submitted'
  a.result = { total: items.length, correct, wrong: items.length-correct, unanswered: items.filter(q => q.unanswered).length, score: Math.round(correct/items.length*1000)/10, mistakes_added: added, items }
  return mockQuizDetail(id)
}

export function resetMockQuizzes() {
  attempts.clear()
  mockAnalysisSessions.clear()
  mockNotebook.value = [{ id: 1, item_type: 'material', material_id: 2, title: '极限与连续 老师标注重点', content: '', source: 'manual', created_at: '2026-10-12T10:00:00' }]
}
