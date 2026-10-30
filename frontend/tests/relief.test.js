import test from 'node:test'
import assert from 'node:assert/strict'
import {buildReliefPreview,applyReliefPlan} from '../src/utils/relief.js'
const today='2026-10-30',exams=[{id:1,exam_date:'2026-11-02'},{id:3,exam_date:'2026-11-03'}]
const task=(id=1,minutes=60,changes={})=>({id,exam_id:1,title:`任务${id}`,plan_date:today,estimated_minutes:minutes,priority:2,is_done:false,source:'manual',start_time:null,end_time:null,detail:'保留内容',...changes})
test('下午休息仍保留上午任务，显示并应用具体时间',()=>{
  const tasks=[task(1),task(2),task(3)], before=structuredClone(tasks)
  const p=buildReliefPreview(tasks,exams,240,today,'halfday','afternoon')
  assert.equal(p.conflicts.length,0);assert.equal(p.today_capacity,120)
  assert.deepEqual(p.retained.map(t=>[t.start_time,t.end_time]),[['08:05','09:05'],['09:05','10:05']])
  assert.equal(p.moves[2].to_date,'2026-10-31');assert.deepEqual(tasks,before)
  const saved=applyReliefPlan(tasks,exams,240,today,p)
  assert.equal(saved[0].start_time,'08:05');assert.equal(saved[0].detail,'保留内容')
  assert.equal(saved.reduce((s,t)=>s+t.estimated_minutes,0),180)
})
test('上午休息安排到12点以后，完成历史占用预算且不改写',()=>{
  const done=task(2,45,{is_done:true,done_at:today+'T07:00:00',start_time:'08:00',end_time:'08:45'})
  const tasks=[task(),done],p=buildReliefPreview(tasks,exams,240,today,'halfday','morning')
  assert.equal(p.conflicts.length,0);assert.equal(p.retained[0].start_time,'12:00')
  assert.deepEqual(applyReliefPlan(tasks,exams,240,today,p)[1],done)
})
test('中午首尾相接允许，跨越休息边界的固定任务阻止确认',()=>{
  for(const [start_time,end_time,conflict] of [['11:00','12:00',false],['12:00','13:00',true],['11:30','12:30',true]]){
    const rows=[task(1,60,{start_time,end_time})],p=buildReliefPreview(rows,exams,240,today,'halfday')
    assert.equal(Boolean(p.conflicts.length),conflict);assert.equal(p.moves.length,0)
    if(conflict)assert.throws(()=>applyReliefPlan(rows,exams,240,today,p))
  }
})
test('剩余时间必须连续；下午不安排到已经过去的上午',()=>{
  const p=buildReliefPreview([task(1,40),task(2,30,{start_time:'11:00',end_time:'11:30'})],[{id:1,exam_date:today}],240,today,'halfday','afternoon','10:30')
  assert.ok(p.conflicts.length);assert.equal(p.moves.length,0)
  const late=buildReliefPreview([task()],exams,240,today,'halfday','afternoon','23:58')
  assert.equal(late.retained.length,0);assert.equal(late.moves[0].to_date,'2026-10-31')
  assert.ok(buildReliefPreview([task()],exams,240,today,'halfday','morning','13:00').conflicts.length)
})
test('任务、考试或预算变更使旧演示预览失效',()=>{
  const rows=[task()],p=buildReliefPreview(rows,exams,240,today,'halfday')
  assert.throws(()=>applyReliefPlan([{...rows[0],detail:'编辑'}],exams,240,today,p),/重新预览/)
  assert.throws(()=>applyReliefPlan(rows,exams,180,today,p),/重新预览/)
  assert.throws(()=>applyReliefPlan(rows,[{id:1,exam_date:'2026-11-01'}],240,today,p),/重新预览/)
})
test('完成超过半日容量只后移待办，长任务与已满未来日明确冲突',()=>{
  const rows=[task(),task(2,180,{is_done:true})],p=buildReliefPreview(rows,exams,240,today,'halfday')
  assert.equal(p.conflicts.length,0);assert.equal(p.moves[0].to_date,'2026-10-31')
  assert.ok(buildReliefPreview([task(1,300)],exams,240,today,'halfday').conflicts.length)
  const fixed=[task(2,180,{plan_date:'2026-10-31',start_time:'09:00',end_time:'12:00'}),task(3,180,{plan_date:'2026-10-31',start_time:'09:00',end_time:'12:00'})]
  const blocked=buildReliefPreview(fixed,exams,240,today,'halfday')
  assert.ok(blocked.conflicts.some(c=>c.reason.includes('预算')));assert.ok(blocked.conflicts.some(c=>c.reason.includes('重叠')))
})
test('移动重复实例只脱离本项，减轻当日选项不受上次半天选择影响',()=>{
  const rows=[task(1,150,{repeat_group_id:'group',repeat_rule:'daily',repeat_until:'2026-11-01'}),task(2,60,{plan_date:'2026-10-31',repeat_group_id:'group'})]
  const p=buildReliefPreview(rows,exams,240,today,'halfday')
  const out=applyReliefPlan(rows,exams,240,today,p)
  assert.equal(out[0].repeat_group_id,null);assert.equal(out[1].repeat_group_id,'group')
  const light=buildReliefPreview(rows,exams,240,today,'lighten','morning')
  assert.doesNotThrow(()=>applyReliefPlan(rows,exams,240,today,light))
})
