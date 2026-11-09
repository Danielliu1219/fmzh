import request from './request'
const pending=new Map()
export async function modelJob(kind,payload,onProgress){
  const key=`${localStorage.getItem('fmzh_token')}:${kind}:${JSON.stringify(payload)}`
  if(!pending.has(key)) pending.set(key,{requestKey:crypto.randomUUID(),startedAt:Date.now()})
  const tracking=pending.get(key)
  let job
  try { job=await request.post('/ai/jobs',{kind,payload,request_key:tracking.requestKey},{timeout:10000}) }
  catch(error){ if(error.response) pending.delete(key); throw error }
  return waitForModelJob(job, onProgress, tracking.startedAt, () => pending.delete(key))
}

export async function resumeModelJob(id, onProgress) {
  return waitForModelJob(await request.get(`/ai/jobs/${id}`, {timeout:10000}), onProgress)
}

async function waitForModelJob(job, onProgress, startedAt=Date.now(), onFinished) {
  const report=()=>onProgress?.({status:job.status,kind:job.kind,progress:job.progress,startedAt,updatedAt:Date.now()})
  report()
  const until=Date.now()+1860000
  while(job.status==='queued'||job.status==='running'){
    if(Date.now()>until) {
      const message=`任务仍在处理中，请稍后点击生成以继续查询（任务 ${job.id}）`
      const {ElMessage}=await import('element-plus')
      ElMessage.warning(message)
      const error=new Error(message)
      error.notified=true
      throw error
    }
    await new Promise(resolve=>setTimeout(resolve,500))
    job=await request.get(`/ai/jobs/${job.id}`,{timeout:10000})
    report()
  }
  onFinished?.()
  if(job.status==='failed'){
    const error=new Error(`${job.error||'生成失败'}${job.request_id?`（请求编号 ${job.request_id}）`:''}`)
    error.response={status:job.error_status,data:{detail:error.message}}
    const {ElMessage}=await import('element-plus')
    ElMessage.error(error.message)
    error.notified=true
    throw error
  }
  return job.result
}
