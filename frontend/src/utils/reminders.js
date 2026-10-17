export const reminderDate = (date, clock, advance) =>
  new Date(
    new Date(`${date}T${clock}:00+08:00`).getTime() - advance * 60000,
  ).toISOString()

export const notificationTime = (value) =>
  new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
