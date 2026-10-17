// All progress displays use task counts; planned minutes never stand in for focus time.
export function taskProgress(tasks) {
  const total = tasks.length
  const done = tasks.filter((task) => task.is_done).length
  return { total, done, rate: total ? done / total : 0 }
}

export function localDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function daysUntil(date, today) {
  // Calendar arithmetic in UTC avoids DST changing the length of a local day.
  return Math.round(
    (Date.parse(`${date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) /
      86400000,
  )
}

export function checkinHistory(tasks, today) {
  // Completion time, rather than the planned date, is evidence of a check-in.
  const dates = new Set(
    tasks
      .filter((task) => task.is_done && task.done_at)
      .map((task) => localDate(new Date(task.done_at))),
  )
  const now = new Date(`${today}T12:00:00`)
  const monday = new Date(now)
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7))
  const week = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(monday)
    date.setDate(monday.getDate() + i)
    const key = localDate(date)
    return {
      date: key,
      label: ['一', '二', '三', '四', '五', '六', '日'][i],
      done: dates.has(key),
      today: key === today,
      future: key > today,
    }
  })
  let streak = 0
  const cursor = new Date(now)
  // An unfinished today does not erase the streak established yesterday.
  if (!dates.has(today)) cursor.setDate(cursor.getDate() - 1)
  while (dates.has(localDate(cursor))) {
    streak++
    cursor.setDate(cursor.getDate() - 1)
  }
  return { week, streak }
}
