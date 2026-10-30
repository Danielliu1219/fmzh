import { findTaskOverlaps } from './taskConflicts.js'
const number = value => Math.round(Date.parse(`${value}T00:00:00Z`)/86400000)
const date = value => new Date(value*86400000).toISOString().slice(0,10)
const minute = value => Number(value.slice(0,2))*60+Number(value.slice(3,5))
const hhmm = value => `${String(Math.floor(value/60)).padStart(2,'0')}:${String(value%60).padStart(2,'0')}`

// 静态演示以08:00为规划时刻；正式模式使用后端北京时间和锁内校验。
export function buildReliefPreview(tasks, exams, budget, today, option, half='afternoon', at='08:00') {
  if (!['lighten','halfday'].includes(option) || !['morning','afternoon'].includes(half)) throw new Error('不支持的减负选项或休息半天')
  if(option==='lighten') half='afternoon'
  const capacity=Math.floor(budget/2), rest=half==='morning'?[0,720]:[720,1440], earliest=minute(at)+5
  const available=half==='morning'?[Math.max(720,earliest),1439]:[Math.max(0,earliest),720]
  const load=new Map(), occupied=[], conflicts=[], moves=[]
  const completed=tasks.filter(t=>t.is_done&&t.plan_date===today).reduce((s,t)=>s+t.estimated_minutes,0)
  const movable=tasks.filter(t=>!t.is_done&&t.plan_date<=today&&!t.start_time)
  const frozen=tasks.filter(t=>t.is_done||t.plan_date>today||t.start_time)
  const issue=(t,reason)=>conflicts.push({task_id:t.id,title:t.title,reason})
  if(option==='halfday'&&half==='morning'&&earliest>=720) conflicts.push({task_id:0,title:'休息时段',reason:'今日上午已结束，请选择下午休息或明天再规划'})
  for(const t of frozen){
    if(t.plan_date<today){ if(!t.is_done&&t.start_time)issue(t,'固定时段已过，请先手动改期或打卡'); continue }
    load.set(t.plan_date,(load.get(t.plan_date)||0)+t.estimated_minutes)
    const exam=exams.find(e=>e.id===t.exam_id)
    if(!t.is_done&&(!exam||t.plan_date>exam.exam_date))issue(t,'已有任务晚于考试日或考试不存在，请先调整原安排')
    if(t.plan_date!==today||!t.start_time)continue
    const a=minute(t.start_time), b=minute(t.end_time); occupied.push([a,b])
    if(!t.is_done&&option==='halfday'&&a<rest[1]&&b>rest[0]) issue(t,'固定任务与休息半天重叠，请先在课程管理调整；系统保留原时段')
    else if(!t.is_done&&option==='halfday'&&b<=earliest-5) issue(t,'今日固定时段已过，请先手动改期或打卡')
  }
  if((load.get(today)||0)>Math.max(capacity,completed))conflicts.push({task_id:0,title:'今日固定安排',reason:'固定时段与已完成任务已超过减负后的今日容量，请先调整固定时段'})
  for(const [day,used] of [...load].sort(([a],[b])=>a.localeCompare(b)))if(day>today&&used>budget)conflicts.push({task_id:0,title:day,reason:'已有任务超过全科日预算，请先调整该日安排'})
  for(const o of findTaskOverlaps(frozen.filter(t=>t.plan_date>=today)))conflicts.push({task_id:o.second.task_id||0,title:o.second.title,reason:`${o.date} 固定时段重叠 ${o.start_time}–${o.end_time}，请先调整`})
  function gap(duration){
    let cursor=available[0]
    for(const [a,b] of [...occupied].sort((x,y)=>x[0]-y[0]||x[1]-y[1])){
      if(b<=cursor)continue
      if(cursor+duration<=Math.min(a,available[1]))return cursor
      cursor=Math.max(cursor,b)
    }
    return cursor+duration<=available[1]?cursor:null
  }
  const deadline=t=>exams.find(e=>e.id===t.exam_id)?.exam_date||'9999'
  movable.sort((a,b)=>a.priority-b.priority||deadline(a).localeCompare(deadline(b))||a.plan_date.localeCompare(b.plan_date)||a.id-b.id)
  for(const t of movable){
    const exam=exams.find(e=>e.id===t.exam_id)
    if(!exam){issue(t,'考试不存在，请先检查任务归属');continue}
    let chosen=null
    for(let n=number(today);n<=Math.min(number(exam.exam_date),number(today)+365);n++){
      const day=date(n),cap=day===today?capacity:budget
      if((load.get(day)||0)+t.estimated_minutes>cap)continue
      const start=option==='halfday'&&day===today?gap(t.estimated_minutes):null
      if(option!=='halfday'||day!==today||start!==null){chosen=[day,start];break}
    }
    if(!chosen){issue(t,'考前容量或连续空档不足；任务整项保留，请减少任务、拆分或增加可用时间');continue}
    const [day,start]=chosen, end=start===null?null:start+t.estimated_minutes
    load.set(day,(load.get(day)||0)+t.estimated_minutes)
    if(start!==null)occupied.push([start,end])
    const a=start===null?null:hhmm(start), b=end===null?null:hhmm(end)
    if(day!==t.plan_date||a!==(t.start_time||null)||b!==(t.end_time||null))moves.push({task_id:t.id,title:t.title,from_date:t.plan_date,to_date:day,minutes:t.estimated_minutes,from_start:t.start_time||null,from_end:t.end_time||null,to_start:a,to_end:b})
  }
  const retained=[]
  for(const t of tasks){
    const m=moves.find(m=>m.task_id===t.id)
    if(!t.is_done&&(m?.to_date||t.plan_date)===today)retained.push({task_id:t.id,title:t.title,minutes:t.estimated_minutes,start_time:m?m.to_start:t.start_time||null,end_time:m?m.to_end:t.end_time||null})
  }
  return {option,half:option==='halfday'?half:null,date:today,rest_start:option==='halfday'?hhmm(rest[0]):null,rest_end:option==='halfday'?hhmm(rest[1]):null,
    daily_minutes:budget,daily_hours:budget/60,today_capacity:capacity,completed_minutes:completed,today_pending_minutes:retained.reduce((s,t)=>s+t.minutes,0),retained,moves,conflicts,
    note:'固定任务与已完成历史保持原样；未定时任务按整项安排，不拆分或减少分钟。半天休息仅调整今日计划，不创建长期禁排时段。',
    summary:conflicts.length?`预览含${moves.length}项调整，${conflicts.length}项约束需处理`:`确认后调整${moves.length}项，今日保留${retained.length}项待办；已完成记录保留`,
    preview_clock:at,fingerprint:JSON.stringify([tasks,exams,budget,today,option,half,at])}
}

export function applyReliefPlan(tasks,exams,budget,today,plan){
  const current=buildReliefPreview(tasks,exams,budget,today,plan.option,plan.half||'afternoon',plan.preview_clock)
  if(current.fingerprint!==plan.fingerprint)throw new Error('任务、考试或预算已变化，请重新预览后确认')
  if(current.conflicts.length)throw new Error('仍有约束未解决，请先调整固定安排或每日预算')
  return tasks.map(t=>{
    const m=current.moves.find(m=>m.task_id===t.id)
    if(!m)return t
    return {...t,plan_date:m.to_date,start_time:m.to_start,end_time:m.to_end,
      ...(t.repeat_group_id&&t.plan_date!==m.to_date?{repeat_group_id:null,repeat_rule:'none',repeat_until:null}:{})}
  })
}
