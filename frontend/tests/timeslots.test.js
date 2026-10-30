import test from 'node:test'
import assert from 'node:assert/strict'
import { recommendTimeslots } from '../src/utils/timeslots.js'
const now='2026-10-30T20:00:00+08:00'
const session=(day,hour,exam_id=1)=>({exam_id,duration_minutes:25,start_time:`2026-10-${day}T${hour}:00:00+08:00`,end_time:`2026-10-${day}T${hour}:25:00+08:00`})
const history=()=>[27,28,29].flatMap(d=>['09','19'].map(h=>session(d,h)))
test('history is ranked with evidence and shared budget',()=>{
  const r=recommendTimeslots(history(),[],240,now)
  assert.equal(r.mode,'history'); assert.equal(r.history_minutes,150)
  assert.deepEqual(r.slots.map(s=>[s.start,s.minutes,s.study_days]),[['08:00',120,3],['18:00',120,3]])
})
test('no records and sparse course show honest fallback; checkin is not study time',()=>{
  const r=recommendTimeslots(history(),[{exam_id:2,is_done:true,done_at:'2026-10-29T12:00:00',estimated_minutes:999}],240,now,2)
  assert.equal(r.mode,'insufficient');assert.equal(r.history_minutes,0);assert.equal(r.checkin_count,1)
  assert.match(r.note,/记录不足/)
})
test('duplicate and partial overlap are unioned',()=>{
  const rows=history(); rows.push(rows[0],{...rows[0],start_time:'2026-10-27T09:10:00+08:00',end_time:'2026-10-27T09:35:00+08:00'})
  const r=recommendTimeslots(rows,[],240,now)
  assert.equal(r.history_minutes,160);assert.equal(r.ignored_sessions,1)
})
test('window, midnight, future and invalid times do not inflate history',()=>{
  const rows=[{exam_id:1,duration_minutes:30,start_time:'2026-10-02T23:45:00',end_time:'2026-10-03T00:15:00'},
    session(31,'09'),{...session(29,'10'),duration_minutes:100},
    {exam_id:1,duration_minutes:30,start_time:'2026-10-29T23:45:00',end_time:'2026-10-30T00:15:00'}]
  const r=recommendTimeslots(rows,[],30,now)
  assert.equal(r.window_start,'2026-10-03');assert.equal(r.history_minutes,45);assert.equal(r.study_days,3)
})
test('all budgets conserve allocated plus explicit remaining minutes',()=>{
  for(const budget of [30,31,120,240,960]) for(const rows of [[],history()]){
    const r=recommendTimeslots(rows,[],budget,now)
    assert.equal(r.slots.reduce((s,r)=>s+r.minutes,0)+r.unallocated_minutes,budget)
    assert.ok(r.slots.every(s=>s.minutes>0&&s.minutes<=120))
  }
})
