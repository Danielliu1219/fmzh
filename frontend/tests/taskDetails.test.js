import test from 'node:test'
import assert from 'node:assert/strict'
import { buildTaskPreview, mockTaskInstances, normalizeTask, occurrenceDates, taskRepeatLabel, taskTimeLabel, timeDuration } from '../src/utils/taskDetails.js'
import { applyStudyPlan, buildReliefPreview, buildStudyPlan } from '../src/utils/studyPlan.js'
import { feedbackReplan } from '../src/utils/replan.js'

const TODAY = '2026-10-29'
const exams = [{ id: 1, exam_date: '2027-04-30' }, { id: 2, exam_date: '2027-04-30' }]
const payload = changes => ({ exam_id: 1, title: '复习', plan_date: TODAY, estimated_minutes: 60, priority: 2, ...changes })

test('固定时段按整分钟计算，清空双时段恢复待安排', () => {
  assert.equal(timeDuration('09:05', '10:20'), 75)
  assert.equal(timeDuration(null, null), null)
  assert.equal(normalizeTask(payload({ start_time: '09:05', end_time: '10:20', estimated_minutes: 1 })).estimated_minutes, 75)
  for (const pair of [['09:00', null], ['09:00', '09:00'], ['23:00','01:00'], ['09:00:30','10:00'], ['24:00','10:00']]) assert.throws(() => timeDuration(...pair))
  assert.equal(taskTimeLabel({}), '时间待安排')
  assert.equal(taskTimeLabel({ start_time:'09:05',end_time:'10:20' }), '09:05–10:20')
})

test('每天、工作日和每周按截止日期展开，跨年闰日正确', () => {
  assert.deepEqual(occurrenceDates('2026-10-30','weekdays','2026-11-05'), ['2026-10-30','2026-11-02','2026-11-03','2026-11-04','2026-11-05'])
  assert.deepEqual(occurrenceDates('2026-12-25','weekly','2027-01-08'), ['2026-12-25','2027-01-01','2027-01-08'])
  assert.deepEqual(occurrenceDates('2028-02-28','daily','2028-03-01'), ['2028-02-28','2028-02-29','2028-03-01'])
  assert.deepEqual(occurrenceDates(TODAY), [TODAY])
})

test('重复任务拒绝无截止、超180项、超一年、无工作日及非法字段', () => {
  for (const args of [[TODAY,'daily'],[TODAY,'none',TODAY],[TODAY,'daily','2027-04-27'],[TODAY,'weekly','2027-10-31'],['2026-10-31','weekdays','2026-11-01'],['2026-02-30','none']]) assert.throws(() => occurrenceDates(...args))
  for (const change of [{ title:' ' },{ estimated_minutes:0 },{ difficulty:'invalid' },{ location:'x'.repeat(121) },{ detail:'x'.repeat(2001) }]) assert.throws(() => normalizeTask(payload(change)))
})

test('只读预览对所有重复日期检查全科预算，编辑排除自身', () => {
  const tasks = [{ id:1,exam_id:2,plan_date:'2026-10-30',estimated_minutes:100 }]
  const before = JSON.stringify(tasks)
  const preview = buildTaskPreview(payload({ start_time:'09:00',end_time:'09:30',repeat_rule:'daily',repeat_until:'2026-10-31' }), tasks, exams, 120)
  assert.equal(preview.count, 3); assert.equal(preview.total_minutes, 90)
  assert.equal(preview.warnings[0].date,'2026-10-30'); assert.equal(preview.warnings[0].planned_minutes,130)
  assert.equal(JSON.stringify(tasks), before)
  assert.equal(buildTaskPreview(payload({ plan_date:'2026-10-30' }),tasks,exams,120,1).warnings.length,0)
  assert.throws(() => buildTaskPreview(payload({ plan_date:'2027-05-01' }),tasks,exams,120))
})

test('预览生成独立任务与重复组，元数据和原任务不丢失', () => {
  const preview = buildTaskPreview(payload({ start_time:'14:00',end_time:'14:45',location:'图书馆',difficulty:'hard',detail:'先做例题',repeat_rule:'daily',repeat_until:'2026-10-30' }),[],exams,120)
  const rows = mockTaskInstances(preview,[{id:7}],'test-group')
  assert.deepEqual(rows.map(t=>t.id),[8,9]); assert.equal(rows[0].repeat_group_id,'test-group')
  assert.equal(rows[0].location,'图书馆'); assert.equal(rows[1].estimated_minutes,45)
  assert.match(taskRepeatLabel(rows[0]),/每天至2026-10-30/)
  assert.equal(taskRepeatLabel({}), '单次')
})

test('全科排程和反馈重排保留已固定时段的AI任务', () => {
  const fixed = { id:1,exam_id:1,title:'积分',plan_date:TODAY,estimated_minutes:60,priority:2,source:'ai',is_done:false,start_time:'09:00',end_time:'10:00',location:'A' }
  const free = { ...fixed,id:2,title:'极限',estimated_minutes:180,start_time:null,end_time:null,detail:'保留内容' }
  const plan = buildStudyPlan([fixed,free],exams,120,TODAY)
  assert.ok(!plan.assignments.some(a=>a.task_id===1)); assert.equal(plan.conflicts.length,0)
  const applied = applyStudyPlan([fixed,free],plan)
  assert.deepEqual(applied.find(t=>t.id===1),fixed)
  assert.ok(applied.filter(t=>t.id!==1).every(t=>t.detail==='保留内容'))
  const feedback = feedbackReplan({ course:'数学',knowledge_points:[{name:'积分',weight:.8}] },1,[fixed,free],exams,120,TODAY)
  assert.ok(feedback.plan.some(p=>p.title==='积分' && p.detail.includes('固定时段')))
  const relief = buildReliefPreview([fixed],exams,120,TODAY,'halfday')
  assert.equal(relief.moves.length,0); assert.ok(relief.conflicts.length)
})

test('过期固定时段需要手动处理，不能被自动挪走', () => {
  const task = { id:1,exam_id:1,title:'固定复习',plan_date:'2026-10-28',estimated_minutes:60,priority:1,source:'ai',is_done:false,start_time:'09:00',end_time:'10:00' }
  const plan = buildStudyPlan([task],exams,120,TODAY)
  assert.equal(plan.assignments.length,0); assert.match(plan.conflicts[0].reason,/固定时段已过/)
})
