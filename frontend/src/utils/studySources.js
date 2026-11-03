export function matchingSources(items, knowledgePoint, sourceIds=[]) {
  const chosen=new Set(sourceIds)
  return items.filter(item=>chosen.size ? chosen.has(item.id) : item.knowledge_points?.some(p=>p.name===knowledgePoint))
    .sort((a,b)=>a.material_id-b.material_id || a.start-b.start)
}
export function sourceLabel(unit) {
  return `${unit.material_title} · ${unit.label || unit.location}`
}
export function sourceMethod(unit, knowledgePoint, sourceIds=[]) {
  const methods=sourceIds.includes(unit.id) ? ['model'] : unit.knowledge_points?.filter(p=>p.name===knowledgePoint).map(p=>p.method) || []
  return methods.includes('model') ? '已关联来源，请核对原文' : methods.includes('quote') ? '按原文引文定位' : methods.includes('keyword') ? '本地关键词匹配，需核对' : '未关联知识点'
}
