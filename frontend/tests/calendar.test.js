import test from 'node:test'
import assert from 'node:assert/strict'
import { addDays, calendarDays, snapMinute, dropMinute, moveProposal, moveCandidate, calendarFingerprint, previewCalendarMove, applyMockCalendarMove, layoutTimedTasks } from '../src/utils/calendar.js'
const today='2026-10-29', exams=[{id:1,exam_date:'2026-11-12'},{id:2,exam_date:'2026-11-13'}]
const task=changes=>({id:1,exam_id:1,title:'复盘',plan_date:today,estimated_minutes:75,priority:2,source:'manual',is_done:false,start_time:null,end_time:null,location:'自习室',difficulty:'hard',detail:'原内容',repeat_rule:'none',repeat_group_id:null,...changes})

test('周一至周日，跨月跨年闰日均使用日期计算',()=>{
  assert.deepEqual(calendarDays('2027-01-01','week'),['2026-12-28','2026-12-29','2026-12-30','2026-12-31','2027-01-01','2027-01-02','2027-01-03'])
  assert.deepEqual(calendarDays(today,'day'),[today]);assert.equal(addDays('2028-02-28',1),'2028-02-29')
  assert.throws(()=>calendarDays('2026-02-30','day'))
})
test('时间轴15分钟定位不越过当天，任务分钟数不舍入',()=>{
  assert.equal(snapMinute(0,1152),0);assert.equal(snapMinute(480,1152),600);assert.equal(snapMinute(1152,1152),1425)
  const original=task(), candidate=moveCandidate(original,moveProposal(original,today,'09:15'))
  assert.equal(candidate.end_time,'10:30');assert.equal(candidate.estimated_minutes,75);assert.equal(original.start_time,null)
})
test('横向跨日保留原分钟，纵向拖动扣除抓取位置再按15分钟定位',()=>{
  assert.equal(dropMinute(480,1152,'09:05',25,0),545)
  assert.equal(dropMinute(500,1152,'09:05',20,200),600)
  assert.equal(dropMinute(480,1152,null,0,200),600)
})
test('月历改期保留时刻，时间待安排区清除双时刻并保留内容',()=>{
  const original=task({start_time:'09:05',end_time:'10:20'})
  const moved=moveCandidate(original,moveProposal(original,'2026-10-30'))
  assert.equal(moved.start_time,'09:05');assert.equal(moved.end_time,'10:20')
  const cleared=moveCandidate(original,moveProposal(original,today,null))
  assert.equal(cleared.start_time,null);assert.equal(cleared.end_time,null);assert.equal(cleared.detail,'原内容');assert.equal(cleared.estimated_minutes,75)
})
test('完成/过期快照/跨午夜和坏日期不能移动，原对象不变',()=>{
  const original=task(), before=JSON.stringify(original), proposal=moveProposal(original,today,'09:00')
  for(const input of [{...proposal,start_time:'23:30'},{...proposal,plan_date:''},{...proposal,fingerprint:'stale'}]) assert.throws(()=>moveCandidate(original,input))
  const done=task({is_done:true});assert.throws(()=>moveCandidate(done,moveProposal(done,today,'09:00')))
  assert.equal(JSON.stringify(original),before)
})
test('跨科冲突/预算/截止日分别校验，失败不改变日程',()=>{
  const original=task(), other=task({id:2,exam_id:2,start_time:'09:30',end_time:'10:00',estimated_minutes:30})
  const rows=[original,other], before=JSON.stringify(rows), proposal=moveProposal(original,today,'09:00')
  assert.equal(previewCalendarMove(original,proposal,rows,exams,240).can_save,false)
  assert.throws(()=>applyMockCalendarMove(original,proposal,rows,exams,240,true))
  assert.throws(()=>applyMockCalendarMove(original,moveProposal(original,'2026-11-14','09:00'),rows,exams,240))
  assert.equal(JSON.stringify(rows),before)
})
test('跨日移动脱离重复组，同日时段变化仅影响本次且保留组',()=>{
  const original=task({repeat_rule:'daily',repeat_until:'2026-10-31',repeat_group_id:'group'}), rows=[original]
  const same=applyMockCalendarMove(original,moveProposal(original,today,'09:00'),rows,exams,240)
  assert.equal(same.repeat_group_id,'group')
  const different=applyMockCalendarMove(original,moveProposal(original,'2026-10-30','09:00'),rows,exams,240)
  assert.equal(different.repeat_group_id,null);assert.equal(different.repeat_rule,'none')
  assert.equal(original.repeat_group_id,'group')
})
test('预算超限需显式确认，确认仍不能覆盖时段冲突',()=>{
  const original=task(), other=task({id:2,estimated_minutes:100})
  const proposal=moveProposal(original,today,'09:00')
  assert.throws(()=>applyMockCalendarMove(original,proposal,[original,other],exams,120))
  assert.equal(applyMockCalendarMove(original,proposal,[original,other],exams,120,true).estimated_minutes,75)
})
test('快照对日期/时长/完成与内容变化敏感',()=>{
  const original=task(), token=calendarFingerprint(original)
  for(const change of [{plan_date:'2026-10-30'},{estimated_minutes:60},{is_done:true},{detail:'新内容'}]) assert.notEqual(calendarFingerprint({...original,...change}),token)
})
test('存量重叠并排展示，相接任务独占一栏，布局不改任务时间',()=>{
  const rows=[task({id:1,start_time:'09:00',end_time:'10:00'}),task({id:2,start_time:'09:30',end_time:'10:30'}),task({id:3,start_time:'10:30',end_time:'11:00'})]
  const before=JSON.stringify(rows), layout=layoutTimedTasks(rows)
  assert.deepEqual(layout.map(r=>[r.lane,r.columns]),[[0,2],[1,2],[0,1]])
  assert.equal(JSON.stringify(rows),before)
})
