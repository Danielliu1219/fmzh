export const quizKindLabel = (kind) => ({ single: '单选', multiple: '多选', boolean: '判断', fill: '填空' }[kind] || '自测')

export function validQuizDraft(draft, questions) {
  return Array.isArray(draft) && draft.length === questions.length && draft.every((value, i) => {
    const q = questions[i]
    const keys = (q.options || []).map(o => o.value)
    if (q.kind === 'multiple') return Array.isArray(value) && value.every(v => keys.includes(v))
    if (typeof value !== 'string') return false
    if (q.kind === 'single') return value === '' || keys.includes(value)
    if (q.kind === 'boolean') return ['', 'true', 'false'].includes(value)
    return value.length <= 1000
  })
}

export function answerLabel(value, question = {}) {
  if (value === '' || value == null || (Array.isArray(value) && !value.length)) return '未作答'
  if (question.kind === 'boolean') return value === 'true' ? '正确' : '错误'
  return Array.isArray(value) ? value.join('、') : String(value)
}

export function readMistake(content) {
  try {
    const data = JSON.parse(content || '{}')
    return data && typeof data === 'object' && !Array.isArray(data) ? data : { raw: content }
  } catch { return { raw: content } }
}
