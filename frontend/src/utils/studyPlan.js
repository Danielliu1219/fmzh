// 静态演示采用与后端相同的“截止日保障 + 跨科轮转”规则，不调用真实接口。
const dayNumber = (value) =>
  Math.round(Date.parse(`${value}T00:00:00Z`) / 86400000)
const dateString = (value) =>
  new Date(value * 86400000).toISOString().slice(0, 10)
export function buildStudyPlan(tasks, exams, budget, today) {
  const start = dayNumber(today),
    fixed = new Map(),
    jobs = [],
    conflicts = []
  for (const task of tasks) {
    const day = dayNumber(task.plan_date),
      minutes = Math.max(0, task.estimated_minutes || 0)
    if (task.is_done || task.source !== 'ai') {
      fixed.set(day, (fixed.get(day) || 0) + minutes)
      continue
    }
    const exam = exams.find((e) => e.id === task.exam_id),
      examDay = exam ? dayNumber(exam.exam_date) : start - 1
    jobs.push({
      ...task,
      remaining: minutes,
      deadline: examDay >= start ? Math.max(start, examDay - 1) : examDay,
      allocations: new Map(),
    })
  }
  for (const [day, minutes] of fixed)
    if (day >= start && minutes > budget)
      conflicts.push({
        date: dateString(day),
        minutes: minutes - budget,
        reason: '已完成与手动任务已超过当日预算，请先调整手动任务或预算',
      })
  const end = Math.min(
    Math.max(start, ...jobs.map((j) => j.deadline)),
    start + 365,
  )
  for (let day = start; day <= end; day++) {
    let capacity = Math.max(0, budget - (fixed.get(day) || 0))
    const bySubject = new Map()
    const take = (job, want) => {
      const n = Math.min(want, job.remaining)
      if (n <= 0) return 0
      job.allocations.set(day, (job.allocations.get(day) || 0) + n)
      job.remaining -= n
      bySubject.set(job.exam_id, (bySubject.get(job.exam_id) || 0) + n)
      return n
    }
    let active = jobs.filter((j) => j.remaining && j.deadline >= day)
    for (const deadline of [...new Set(active.map((j) => j.deadline))].sort(
      (a, b) => a - b,
    )) {
      const due = active.filter((j) => j.remaining && j.deadline <= deadline)
      let future = 0
      for (let d = day + 1; d <= deadline; d++)
        future += Math.max(0, budget - (fixed.get(d) || 0))
      let required = Math.max(
        0,
        due.reduce((n, j) => n + j.remaining, 0) - future,
      )
      due.sort(
        (a, b) =>
          a.deadline - b.deadline || a.priority - b.priority || a.id - b.id,
      )
      for (const job of due) {
        const n = take(job, Math.min(required, capacity))
        required -= n
        capacity -= n
        if (!required || !capacity) break
      }
    }
    while (capacity) {
      active = jobs.filter((j) => j.remaining && j.deadline >= day)
      if (!active.length) break
      const demand = new Map()
      for (const j of active)
        demand.set(
          j.exam_id,
          (demand.get(j.exam_id) || 0) +
            j.remaining / Math.max(1, j.deadline - day + 1),
        )
      const subject = [...demand].sort(
        (a, b) =>
          b[1] / ((bySubject.get(b[0]) || 0) + 30) -
            a[1] / ((bySubject.get(a[0]) || 0) + 30) || a[0] - b[0],
      )[0][0]
      const job = active
        .filter((j) => j.exam_id === subject)
        .sort(
          (a, b) =>
            a.priority - b.priority ||
            a.plan_date.localeCompare(b.plan_date) ||
            a.id - b.id,
        )[0]
      capacity -= take(job, Math.min(30, capacity))
    }
  }
  const assignments = [],
    totals = new Map()
  for (const [day, minutes] of fixed)
    if (day >= start && day <= end) totals.set(dateString(day), minutes)
  for (const job of jobs) {
    for (const [day, minutes] of job.allocations) {
      const date = dateString(day)
      assignments.push({
        task_id: job.id,
        exam_id: job.exam_id,
        title: job.title,
        from_date: job.plan_date,
        date,
        minutes,
      })
      totals.set(date, (totals.get(date) || 0) + minutes)
    }
    if (job.remaining)
      conflicts.push({
        task_id: job.id,
        title: job.title,
        minutes: job.remaining,
        reason: '考试前剩余时间不足；请减少任务、增加可用时间或调整目标',
      })
  }
  return {
    assignments,
    conflicts,
    days: [...totals]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, minutes]) => ({ date, minutes })),
    daily_minutes: budget,
  }
}
export function applyStudyPlan(tasks, plan) {
  if (plan.conflicts.length) throw new Error('仍有任务无法安排')
  let nextId = Math.max(0, ...tasks.map((t) => t.id)) + 1
  return tasks.flatMap((task) => {
    const segments = plan.assignments
      .filter((a) => a.task_id === task.id)
      .sort((a, b) => a.date.localeCompare(b.date))
    if (!segments.length) return [{ ...task }]
    const title = task.title.replace(/（分段 \d+\/\d+）$/, '')
    return segments.map((part, i) => ({
      ...task,
      id: i ? nextId++ : task.id,
      plan_date: part.date,
      estimated_minutes: part.minutes,
      title:
        title +
        (segments.length > 1 ? `（分段 ${i + 1}/${segments.length}）` : ''),
    }))
  })
}

export function buildReliefPreview(tasks, exams, budget, today, option) {
  const capacity = option === 'halfday' ? 0 : Math.floor(budget / 2)
  const start = dayNumber(today),
    load = new Map(),
    moves = [],
    conflicts = []
  for (const task of tasks)
    if (task.is_done || task.plan_date > today) {
      const day = dayNumber(task.plan_date)
      load.set(day, (load.get(day) || 0) + task.estimated_minutes)
    }
  for (const task of tasks
    .filter((t) => !t.is_done && t.plan_date <= today)
    .sort(
      (a, b) =>
        a.priority - b.priority || a.plan_date.localeCompare(b.plan_date),
    )) {
    const exam = exams.find((e) => e.id === task.exam_id),
      end = exam ? dayNumber(exam.exam_date) : start + 365
    let placed = null
    for (let day = start; day <= Math.min(end, start + 365); day++) {
      if (
        (load.get(day) || 0) + task.estimated_minutes <=
        (day === start ? capacity : budget)
      ) {
        placed = day
        break
      }
    }
    if (placed === null)
      conflicts.push({
        task_id: task.id,
        title: task.title,
        reason: '考前容量不足，请减少任务或增加可用时间',
      })
    else {
      load.set(placed, (load.get(placed) || 0) + task.estimated_minutes)
      if (dateString(placed) !== task.plan_date)
        moves.push({
          task_id: task.id,
          title: task.title,
          from_date: task.plan_date,
          to_date: dateString(placed),
          minutes: task.estimated_minutes,
        })
    }
  }
  return {
    option,
    daily_minutes: budget,
    today_capacity: capacity,
    moves,
    conflicts,
    summary: conflicts.length
      ? '有任务无法在容量内安排，请先调整'
      : moves.length
        ? `将后移 ${moves.length} 个任务，今日负担相应减轻`
        : '当前任务已符合减负后的容量',
  }
}
