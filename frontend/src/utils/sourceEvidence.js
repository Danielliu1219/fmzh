export function excerptParts(reference) {
  const context = String(reference.context || '')
  const start = Math.max(0, Math.min(context.length, Number(reference.highlight_start) || 0))
  const end = Math.max(start, Math.min(context.length, Number(reference.highlight_end) || 0))
  return [context.slice(0, start), context.slice(start, end), context.slice(end)]
}

export function sourceRoute(reference, examId) {
  if (reference.status !== 'available') return null
  return { path: '/materials', query: { exam: examId, material: reference.material_id,
    start: reference.start, end: reference.end, hash: reference.content_hash || 'demo', created_at: reference.material_created_at || 'demo' } }
}

export function mockEvidence(item, examId, materials) {
  const title = item.name || item.content || item.type || ''
  const references = materials.filter(row => row.exam_id === Number(examId) && row.parse_status === 'done')
    .map(row => {
      const context = row.text_preview || ''
      const index = title.length >= 2 ? context.indexOf(title) : -1
      return index < 0 ? null : { material_id: row.id, material_title: row.title, source_type: row.source_type,
        file_type: row.file_type, status: 'available', location: '演示解析文本片段', page: null,
        start: index, end: index + title.length, context, highlight_start: index,
        highlight_end: index + title.length, match: 'keyword', content_hash: '',
        note: '演示资料中的关键词片段，真实模式会校验引用与原文位置。' }
    }).filter(Boolean).slice(0, 3)
  return { item_title: title, exam_id: examId, items: references,
    note: references.length ? '演示内容仅供预览；请结合资料核对推荐理由。' : '演示资料中未找到可核验原文，暂不展示出处。' }
}
