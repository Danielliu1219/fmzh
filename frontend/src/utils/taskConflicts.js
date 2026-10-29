// 同日 [开始, 结束)；未定时任务不推测时间，已完成任务仍占用时段。
export function findTaskOverlaps(existing, candidates = null, exams = []) {
  const days = new Map(), subjects = new Map(exams.map(e => [e.id, e.subject || '']))
  for (const [proposed, rows] of [[false, existing], [true, candidates || []]]) {
    rows.forEach((row, index) => {
      if (!row.start_time || !row.end_time) return
      const item = { task_id: proposed ? null : row.id, candidate_index: proposed ? index + 1 : null,
        exam_id: row.exam_id ?? null, subject: subjects.get(row.exam_id) || '', title: row.title || '待安排任务',
        start_time: row.start_time.slice(0, 5), end_time: row.end_time.slice(0, 5) }
      if (!days.has(row.plan_date)) days.set(row.plan_date, [])
      days.get(row.plan_date).push(item)
    })
  }
  const overlaps = [], minutes = t => Number(t.slice(0, 2)) * 60 + Number(t.slice(3))
  for (const [day, rows] of [...days].sort(([a], [b]) => a.localeCompare(b))) {
    let active = []
    rows.sort((a, b) => a.start_time.localeCompare(b.start_time) || a.end_time.localeCompare(b.end_time) || (a.task_id || 0)-(b.task_id || 0) || (a.candidate_index || 0)-(b.candidate_index || 0))
    for (const row of rows) {
      active = active.filter(previous => previous.end_time > row.start_time)
      for (const previous of active) {
        if (candidates !== null && !(row.candidate_index || previous.candidate_index)) continue
        const start = previous.start_time > row.start_time ? previous.start_time : row.start_time
        const end = previous.end_time < row.end_time ? previous.end_time : row.end_time
        overlaps.push({ date: day, start_time: start, end_time: end, overlap_minutes: minutes(end)-minutes(start),
          first: previous, second: row, reason: '固定时段重叠，请调整其中一项的日期或时间' })
      }
      active.push(row)
    }
  }
  return overlaps
}

export const scheduleChanged = (original, proposed) => original.plan_date !== proposed.plan_date ||
  (original.start_time || null) !== (proposed.start_time || null) || (original.end_time || null) !== (proposed.end_time || null)

export const describeOverlap = overlap => [overlap.first, overlap.second].map(item =>
  `${item.subject ? item.subject + ' · ' : ''}${item.title}（${item.start_time}–${item.end_time}）`).join(' 与 ')
