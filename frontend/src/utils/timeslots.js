// 静态演示与后端使用同一统计口径；正式模式始终读取服务端结果。
const MINUTE = 60000, DAY = 86400000, SHIFT = 8 * 3600000
const stamp = value => Date.parse(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}+08:00`)
const day = value => new Date(value + SHIFT).toISOString().slice(0, 10)

export function recommendTimeslots(sessions, tasks, budget, nowValue, examId) {
  const now = stamp(nowValue), first = day(now - 27 * DAY), start = stamp(`${first}T00:00:00`)
  const intervals = [], seen = new Set()
  let ignored = 0
  for (const row of sessions) {
    if (examId != null && row.exam_id !== examId) continue
    let a = stamp(row.start_time), b = stamp(row.end_time)
    if (b <= start || a >= now) continue
    if (!Number.isFinite(a + b) || !(row.duration_minutes >= 1 && row.duration_minutes <= 180) || b <= a || b > now || Math.abs((b-a)/MINUTE-row.duration_minutes) > 1) { ignored++; continue }
    a = Math.max(a, start)
    const key = `${a}/${b}`
    if (seen.has(key)) { ignored++; continue }
    seen.add(key); intervals.push([a, b])
  }
  const merged = []
  for (const [a,b] of intervals.sort((x,y) => x[0]-y[0] || x[1]-y[1])) {
    const last = merged.at(-1)
    if (last && a <= last[1]) last[1] = Math.max(b, last[1])
    else merged.push([a,b])
  }
  const minutes = Array(12).fill(0), days = Array.from({length:12}, () => new Set()), studyDays = new Set()
  for (let [a,b] of merged) while (a < b) {
    const index = Math.floor(new Date(a+SHIFT).getUTCHours()/2)
    const boundary = Math.floor((a+SHIFT)/(2*3600000))*(2*3600000)+2*3600000-SHIFT
    const end = Math.min(b,boundary)
    minutes[index] += (end-a)/MINUTE; days[index].add(day(a)); studyDays.add(day(a)); a = end
  }
  const total = Math.floor(minutes.reduce((a,b)=>a+b,0))
  const candidates = minutes.map((_,i)=>i).filter(i=>days[i].size>=2 && minutes[i]>=20)
  const enough = studyDays.size>=3 && intervals.length>=5 && total>=90 && candidates.length>0
  const chosen = enough ? candidates.sort((a,b)=>minutes[b]-minutes[a] || days[b].size-days[a].size || a-b).slice(0,3) : [null,null,null]
  let remaining = budget
  const slots = []
  for (const [index,i] of chosen.entries()) {
    if (remaining<=0) break
    const hour = i == null ? [9,14,19][index] : i*2
    const amount = Math.min(120,remaining,Math.max(1,Math.ceil(budget/chosen.length)))
    remaining -= amount
    const evidence = i == null ? 0 : Math.floor(minutes[i]), count = i == null ? 0 : days[i].size
    slots.push({name:enough ? `习惯时段 ${index+1}` : ['上午','下午','晚上'][index],start:`${String(hour).padStart(2,'0')}:00`,end:`${String(hour+2).padStart(2,'0')}:00`,minutes:amount,
      focus:'选择一项重点任务，中间留出休息时间',history_minutes:evidence,study_days:count,
      reason:enough ? `近28天有${count}天在此专注，累计${evidence}分钟` : '通用参考时段，尚无足够个人记录'})
  }
  let note = enough ? '根据重复出现的专注时段推荐，只反映习惯，不代表效率或空闲时间。' : `记录不足：近28天有效专注${intervals.length}条、${studyDays.size}天、${total}分钟；至少需5条、3天、90分钟，且同一时段在2天出现并累计20分钟。暂显示通用参考。`
  if (remaining) note += ` 还有${remaining}分钟预算未分配，请按实际作息另行安排。`
  if (ignored) note += ` 已忽略${ignored}条重复或异常记录。`
  note += ' 打卡仅统计完成次数，不推算专注时长；推荐不会改动任务安排。'
  return {daily_hours:budget/60,daily_minutes:budget,mode:enough?'history':'insufficient',scope:examId!=null?'course':'all',exam_id:examId??null,
    window_start:first,window_end:day(now),timezone:'Asia/Shanghai',session_count:intervals.length,study_days:studyDays.size,history_minutes:total,
    checkin_count:tasks.filter(t=>t.is_done && t.done_at && stamp(t.done_at)>=start && stamp(t.done_at)<=now && (examId==null || t.exam_id===examId)).length,
    ignored_sessions:ignored,recommended_minutes:budget-remaining,unallocated_minutes:remaining,slots,note}
}
