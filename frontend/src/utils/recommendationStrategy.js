import { scoreBand, scoreBandText } from './scoreTargets.js'

const PHASES = [
  ['foundation', '基础巩固', '核对本主题的概念、公式与适用条件，跟做资料中的基础例题'],
  ['practice', '常见题型与错题', '独立完成资料中的常见题型，核对步骤并复盘错误原因'],
  ['challenge', '综合与限时训练', '在基础题能独立完成后，练习资料中的综合应用或限时题；缺少相应题目时用于错题复盘'],
]

export function splitMinutes(total, weights) {
  if (!weights.length) return []
  total = Math.max(0, Math.floor(total))
  let denominator = weights.reduce((a, b) => a + b, 0)
  if (denominator <= 0) { weights = weights.map(() => 1); denominator = weights.length }
  const exact = weights.map(w => total * w / denominator)
  const allocated = exact.map(Math.floor)
  const order = weights.map((_, i) => i).sort((a, b) => (exact[b] - allocated[b]) - (exact[a] - allocated[a]) || a - b)
  order.slice(0, total - allocated.reduce((a, b) => a + b, 0)).forEach(i => allocated[i]++)
  return allocated
}

export function strategyFor(profile) {
  const band = scoreBand(profile.target_band)
  const minimum = band?.min ?? ({ pass: 60, medium: 76, high: 90 }[profile.target] ?? 76)
  const progress = Math.max(0, Math.min(1, (minimum - 60) / 30))
  const status = profile.learning_status || 'medium'
  let foundation = Math.floor(65 - 40 * progress + .5) + ({ weak: 12, good: -8 }[status] || 0)
  foundation = Math.min(85, Math.max(15, foundation))
  let practice = Math.min(Math.floor(30 + 10 * progress + .5), 100 - foundation)
  let challenge = 100 - foundation - practice
  const days = Math.max(1, Math.min(366, Math.floor(profile.available_days || 1)))
  if (days <= 3 && challenge > 10) { practice += challenge - 10; challenge = 10 }
  let weak = profile.weak_chapters || []
  if (typeof weak === 'string') { try { weak = JSON.parse(weak) } catch { weak = [] } }
  weak = Array.isArray(weak) ? weak.map(x => String(x).trim().slice(0, 80)).filter(Boolean) : []
  const daily = Math.max(0, Math.min(960, Math.floor(Number(profile.daily_hours || 0) * 60 + 1e-7)))
  return {
    target_band: band?.id || null, target_label: band ? scoreBandText(band.id) : ({ pass: '保及格', medium: '稳中等', high: '冲高分' }[profile.target] || '稳中等'),
    learning_status: status, available_days: days, daily_minutes: daily, available_minutes: daily * days,
    planned_minutes: 0, deferred_minutes: 0, weak_chapters: weak,
    phases: PHASES.map(([phase, label, detail], i) => ({ phase, label, detail, percent: [foundation, practice, challenge][i], minutes: 0 })),
    notes: ['三类练习拆分同一份计划时间，不额外增加每日任务量；比例为复习建议，不代表试卷分值或题型出现频率。', '高目标也先补基础；临考三天内优先常见题与错题，资料未覆盖的难题不另行编造。'],
  }
}

export function refreshStrategy(result) {
  const strategy = result.strategy
  if (!strategy) return result
  strategy.phases.forEach(p => { p.minutes = 0 })
  result.review_plan.forEach(item => {
    const amounts = splitMinutes(item.estimated_minutes, strategy.phases.map(p => p.percent))
    item.activities = strategy.phases.map((p, i) => ({ phase: p.phase, label: p.label, minutes: amounts[i], detail: p.detail })).filter(a => a.minutes)
    strategy.phases.forEach((p, i) => { p.minutes += amounts[i] })
  })
  strategy.planned_minutes = result.review_plan.reduce((sum, p) => sum + p.estimated_minutes, 0)
  const scores = result.knowledge_points.map(point => {
    const weak = strategy.weak_chapters.some(c => c.length >= 2 && (point.name.includes(c) || c.includes(point.name)))
    point.practice_hint = weak ? '你标注的薄弱内容，先补概念和典型例题，再独立练习。' : '先完成资料中的高频基础题，再按本轮比例练习与复盘。'
    return Math.max(.05, point.weight) ** (1 + strategy.phases[0].percent / 100) * (weak ? 1.6 : 1)
  })
  const amounts = splitMinutes(strategy.planned_minutes, scores)
  result.knowledge_points.forEach((p, i) => { p.suggest_minutes = amounts[i]; p.suggest_hours = Math.round(amounts[i] / 60 * 100) / 100 })
  return result
}

export function applyRecommendationStrategy(result, profile, today) {
  const strategy = strategyFor(profile)
  result.strategy = strategy
  const load = new Map()
  result.review_plan = result.review_plan.flatMap(original => {
    const requested = Math.max(0, Math.floor(original.estimated_minutes))
    const index = original.day - 1
    if (index < 0 || index >= strategy.available_days) { strategy.deferred_minutes += requested; return [] }
    const amount = Math.min(requested, Math.max(0, strategy.daily_minutes - (load.get(index) || 0)))
    strategy.deferred_minutes += requested - amount
    if (!amount) return []
    load.set(index, (load.get(index) || 0) + amount)
    const date = new Date(Date.parse(`${today}T00:00:00Z`) + index * 86400000).toISOString().slice(0, 10)
    return [{ ...original, date, estimated_minutes: amount, priority: Math.max(1, Math.min(3, original.priority)) }]
  })
  if (strategy.deferred_minutes) strategy.notes.push(`模型原建议中有 ${strategy.deferred_minutes} 分钟超出本科生成时的可用天数或当日份额，未写入任务；请缩小复习范围或调整预算后重新生成。`)
  return refreshStrategy(result)
}

export const suggestedTime = point => point.suggest_minutes == null ? `${point.suggest_hours || 0} 小时` : point.suggest_minutes ? `${point.suggest_minutes} 分钟` : '本轮暂不安排'
