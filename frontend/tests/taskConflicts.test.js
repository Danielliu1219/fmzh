import test from 'node:test'
import assert from 'node:assert/strict'
import { describeOverlap, findTaskOverlaps } from '../src/utils/taskConflicts.js'
import { buildTaskPreview } from '../src/utils/taskDetails.js'
import { buildStudyPlan } from '../src/utils/studyPlan.js'

const day='2026-10-29', exams=[{id:1,subject:'数学',exam_date:'2026-11-12'},{id:2,subject:'英语',exam_date:'2026-11-13'}]
const task=(id,start_time,end_time,changes={})=>({id,exam_id:1,title:'复习'+id,plan_date:day,start_time,end_time,estimated_minutes:60,priority:2,source:'manual',is_done:false,...changes})

test('交集/包含/同起止正确计算，首尾相接与未定时不算重叠',()=>{
  const first=task(1,'09:00','10:00')
  for(const [start,end,minutes] of [['09:30','10:30',30],['08:00','11:00',60],['09:15','09:45',30],['09:00','10:00',60]]){
    const overlaps=findTaskOverlaps([first],[task(2,start,end)],exams)
    assert.equal(overlaps.length,1);assert.equal(overlaps[0].overlap_minutes,minutes)
  }
  assert.equal(findTaskOverlaps([first,task(2,'08:00','09:00'),task(3,'10:00','11:00'),task(4,null,null)]).length,0)
})

test('跨科/已完成仍占用时段，日期隔离，不重复列已有冲突',()=>{
  const tasks=[task(1,'09:00','10:00'),task(2,'09:30','10:30',{exam_id:2,is_done:true})]
  const before=JSON.stringify(tasks), overlap=findTaskOverlaps(tasks,null,exams)[0]
  assert.match(describeOverlap(overlap),/数学.*英语/);assert.equal(JSON.stringify(tasks),before)
  assert.equal(findTaskOverlaps(tasks,[task(3,'11:00','12:00')]).length,0)
  assert.equal(findTaskOverlaps(tasks,[task(3,'09:00','10:00',{plan_date:'2026-10-30'})]).length,0)
})

test('重复预览逐日拦截重叠，编辑排除自身，改期失败不写入',()=>{
  const tasks=[task(1,'09:00','10:00',{plan_date:'2026-10-30',exam_id:2})], before=JSON.stringify(tasks)
  const payload=task(null,'09:30','10:30',{repeat_rule:'daily',repeat_until:'2026-10-31'})
  const preview=buildTaskPreview(payload,tasks,exams,240)
  assert.equal(preview.can_save,false);assert.equal(preview.overlaps.length,1);assert.equal(preview.overlaps[0].date,'2026-10-30')
  assert.equal(JSON.stringify(tasks),before)
  assert.equal(buildTaskPreview(tasks[0],tasks,exams,240,1).overlaps.length,0)
})

test('历史重叠仍可编辑文字，实际改动时段必须消除冲突',()=>{
  const tasks=[task(1,'09:00','10:00'),task(2,'09:30','10:30')]
  assert.equal(buildTaskPreview({...tasks[0],title:'只改标题'},tasks,exams,240,1).can_save,true)
  assert.equal(buildTaskPreview({...tasks[0],start_time:'09:05'},tasks,exams,240,1).can_save,false)
  assert.equal(buildTaskPreview({...tasks[0],start_time:'08:00',end_time:'09:00'},tasks,exams,240,1).can_save,true)
  assert.ok(buildStudyPlan(tasks,exams,240,day).conflicts.some(c=>c.reason.includes('时段重叠')))
})
