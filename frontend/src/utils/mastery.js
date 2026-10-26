const normalize = (value) => String(value ?? '').normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase()

export const masteryLabels = { untested: '未测', weak: '薄弱', mastered: '已掌握' }
export const masteryTypes = { untested: 'info', weak: 'warning', mastered: 'success' }

// 与后端口径一致：每个知识点最近一次已交卷的有效题目，空答计错。
export function buildMastery(names, attempts) {
  const latest = new Map()
  const submitted = attempts.filter(a => a.status === 'submitted' && a.submitted_at)
    .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at) || b.created_at.localeCompare(a.created_at) || String(b.id).localeCompare(String(a.id)))
  for (const attempt of submitted) {
    const grouped = new Map()
    for (const item of attempt.result?.items || []) {
      const key = normalize(item.knowledge_point)
      if (!key || !item.question || typeof item.correct !== 'boolean') continue
      if (!grouped.has(key)) grouped.set(key, new Map())
      grouped.get(key).set(normalize(item.question), { question: item.question, correct: item.correct, unanswered: !!item.unanswered })
    }
    for (const [key, evidence] of grouped) {
      if (!latest.has(key)) latest.set(key, { attempt_id: attempt.id, last_submitted_at: attempt.submitted_at, evidence: [...evidence.values()] })
    }
  }
  return names.map(name => {
    const record = latest.get(normalize(name))
    const evidence = record?.evidence || []
    const correct = evidence.filter(item => item.correct).length
    const score = evidence.length ? Math.round(correct / evidence.length * 1000) / 10 : null
    return { name, status: score === null ? 'untested' : score >= 80 ? 'mastered' : 'weak', total: evidence.length, correct, score,
      attempt_id: record?.attempt_id ?? null, last_submitted_at: record?.last_submitted_at ?? null, evidence }
  })
}
