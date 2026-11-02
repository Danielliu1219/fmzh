import request from './request'
const pending=new Map()
export async function modelJob(kind,payload){
  const key=`${localStorage.getItem('fmzh_token')}:${kind}:${JSON.stringify(payload)}`
  if(!pending.has(key)) pending.set(key,crypto.randomUUID())
  let job
  try { job=await request.post('/ai/jobs',{kind,payload,request_key:pending.get(key)},{timeout:10000}) }
  catch(error){ if(error.response) pending.delete(key); throw error }
  const until=Date.now()+(kind==='analysis'?1860000:150000)
  while(job.status==='queued'||job.status==='running'){
    if(Date.now()>until) {
      const message=`任务仍在处理中，请稍后点击生成以继续查询（任务 ${job.id}）`
      const {ElMessage}=await import('element-plus')
      ElMessage.warning(message)
      throw new Error(message)
    }
    await new Promise(resolve=>setTimeout(resolve,500))
    job=await request.get(`/ai/jobs/${job.id}`,{timeout:10000})
  }
  pending.delete(key)
  if(job.status==='failed'){
    const error=new Error(`${job.error||'生成失败'}${job.request_id?`（请求编号 ${job.request_id}）`:''}`)
    error.response={status:job.error_status,data:{detail:error.message}}
    const {ElMessage}=await import('element-plus')
    ElMessage.error(error.message)
    throw error
  }
  return job.result
}
