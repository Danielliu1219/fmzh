import test from 'node:test'
import assert from 'node:assert/strict'
import { matchingSources, sourceLabel, sourceMethod } from '../src/utils/studySources.js'
const items=[{id:'a',material_id:2,start:10,material_title:'真题',label:'第 3 题 · 第 2 页',knowledge_points:[{name:'极限',method:'keyword'}]},{id:'b',material_id:1,start:0,material_title:'讲义',label:'第 5 张幻灯片',knowledge_points:[{name:'极限',method:'quote'}]}]
test('task selections take precedence over broad knowledge point matches',()=>{
  assert.deepEqual(matchingSources(items,'极限',['a']).map(u=>u.id),['a'])
  assert.deepEqual(matchingSources(items,'极限').map(u=>u.id),['b','a'])
  assert.deepEqual(matchingSources(items,'极限',['stale']),[])
})
test('source labels preserve exact location and distinguish local matching',()=>{
  assert.equal(sourceLabel(items[0]),'真题 · 第 3 题 · 第 2 页')
  assert.match(sourceMethod(items[0],'极限'),/关键词.*需核对/)
  assert.match(sourceMethod(items[1],'极限'),/引文/)
  assert.match(sourceMethod(items[0],'极限',['a']),/已关联/)
})
