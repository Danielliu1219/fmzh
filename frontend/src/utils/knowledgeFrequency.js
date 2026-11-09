export function knowledgeFrequencyLabel(point) {
  const percent = `${Math.round(point.weight * 100)}%`
  const count = point.occurrence_count
  return Number.isInteger(count) && count > 0 ? `${percent} · 已定位 ${count} 次` : percent
}
