function citationMatches(unit, citations) {
  return citations.some(reference => reference.match === 'quote' && reference.material_id === unit.material_id
    && reference.content_hash === unit.revision && reference.start < unit.end && reference.end > unit.start)
}
export function matchingSources(items, knowledgePoint, sourceIds=[], citations=[]) {
  const chosen=new Set(sourceIds)
  return items.filter(item=>chosen.size ? chosen.has(item.id) : citationMatches(item, citations) || item.knowledge_points?.some(p=>p.name===knowledgePoint))
    .sort((a,b)=>a.material_id-b.material_id || a.start-b.start)
}
export function sourceLabel(unit) {
  return `${unit.material_title} · ${unit.label || unit.location}`
}
export function sourceMethod(unit, knowledgePoint, sourceIds=[], citations=[]) {
  const methods=sourceIds.includes(unit.id) ? ['model'] : unit.knowledge_points?.filter(p=>p.name===knowledgePoint).map(p=>p.method) || []
  return methods.includes('model') ? '已关联来源，请核对' : methods.includes('quote') || citationMatches(unit, citations) ? '按原文引文定位' : methods.includes('keyword') ? '本地关键词匹配，需核对' : '未关联知识点'
}
