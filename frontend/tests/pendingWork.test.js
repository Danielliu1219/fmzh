import test from 'node:test'
import assert from 'node:assert/strict'
import {createPendingWork,createLogoutFlow} from '../src/utils/pendingWork.js'
function setup(overrides={}){
  const work=createPendingWork(),calls=[],messages=[];let current='session-a'
  const flow=createLogoutFlow({work,token:()=>current,confirm:async message=>{calls.push(['confirm',message]);return true},revoke:async token=>calls.push(['revoke',token]),clear:async()=>{calls.push(['clear']);current=''},notify:m=>messages.push(m),...overrides})
  return {work,calls,messages,flow,token:()=>current,setToken:t=>{current=t}}
}
test('取消退出不准备、不撤销、不清理，运行中的计时保持原样',async()=>{
  let running=true,prepared=false;const c=setup({confirm:async()=>false});c.work.register(()=>({warning:'专注中'}),async()=>{prepared=true;running=false})
  assert.equal(await c.flow(),false);assert.equal(prepared,false);assert.equal(running,true);assert.equal(c.token(),'session-a');assert.deepEqual(c.calls,[])
})
test('确认后先保存专注，再撤销原令牌，最后清除草稿',async()=>{
  const c=setup();c.work.register(()=>({warning:'未结束专注'}),async()=>{c.calls.push(['saved']);return true})
  assert.equal(await c.flow(),true);assert.deepEqual(c.calls.map(c=>c[0]),['confirm','saved','revoke','clear']);assert.equal(c.calls[2][1],'session-a');assert.equal(c.token(),'')
})
test('保存失败阻止退出，保留原会话和草稿',async()=>{
  const c=setup();c.work.register(()=>({warning:'专注'}),async()=>false)
  assert.equal(await c.flow(),false);assert.equal(c.token(),'session-a');assert.deepEqual(c.calls.map(c=>c[0]),['confirm'])
})
test('服务器退出失败保留会话并允许重试',async()=>{
  let attempts=0;const c=setup({revoke:async()=>{if(++attempts===1)throw new Error('offline')}})
  assert.equal(await c.flow(),false);assert.equal(c.token(),'session-a');assert.match(c.messages[0],/已保留/)
  assert.equal(await c.flow(),true);assert.equal(attempts,2);assert.equal(c.token(),'')
})
test('写入中不弹确认；确认期间新写入也会阻止退出',async()=>{
  const c=setup();let busy=true;c.work.register(()=>({busy:busy?'上传':''}))
  assert.equal(await c.flow(),false);assert.deepEqual(c.calls,[])
  busy=false;const d=setup({confirm:async()=>{busy=true;return true}});d.work.register(()=>({busy:busy?'保存':''}))
  assert.equal(await d.flow(),false);assert.equal(d.token(),'session-a')
})
test('双击退出只进行一次确认和一次撤销',async()=>{
  let proceed;const gate=new Promise(r=>{proceed=r});let confirms=0,revokes=0
  const c=setup({confirm:async()=>{confirms++;await gate;return true},revoke:async()=>{revokes++}})
  const first=c.flow();assert.equal(await c.flow(),false);proceed();assert.equal(await first,true);assert.equal(confirms,1);assert.equal(revokes,1)
})
test('迟到的旧退出响应不能清除新登录会话',async()=>{
  let resolve;const wait=new Promise(r=>{resolve=r});const c=setup({revoke:async()=>{await wait}})
  const request=c.flow();await Promise.resolve();await Promise.resolve();await Promise.resolve();c.setToken('session-b');resolve()
  assert.equal(await request,false);assert.equal(c.token(),'session-b');assert.ok(!c.calls.some(c=>c[0]==='clear'))
})
test('确认期间换号后不会向新账号发送退出',async()=>{
  const c=setup({confirm:async()=>{c.setToken('session-b');return true}})
  assert.equal(await c.flow(),false);assert.ok(!c.calls.some(c=>c[0]==='revoke'));assert.equal(c.token(),'session-b')
})
test('状态实时读取去重，卸载后不留下幽灵表单',async()=>{
  const work=createPendingWork();let dirty=false;const unregister=work.register(()=>({warning:dirty?'未保存':''}));work.register(()=>({warning:['相同','相同'],busy:['保存','保存']}))
  assert.deepEqual(work.state(),{busy:['保存'],warnings:['相同']});dirty=true;assert.deepEqual(work.state().warnings,['未保存','相同']);unregister();assert.deepEqual(work.state().warnings,['相同'])
})
