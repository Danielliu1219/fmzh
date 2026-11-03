import request from './request'

const cache = new Map()
export const sourceApi = {
  library(examId, analysisId, refresh=false) {
    const key=JSON.stringify([localStorage.getItem('fmzh_token'),examId,analysisId])
    const saved=cache.get(key)
    if (!refresh && saved && Date.now()-saved.at < 15000) return saved.promise
    const promise=request.get('/study-sources',{params:{exam_id:examId,analysis_id:analysisId || undefined}})
    cache.set(key,{at:Date.now(),promise})
    promise.catch(()=>{if(cache.get(key)?.promise===promise) cache.delete(key)})
    return promise
  },
  unit: (unit) => request.get(`/study-sources/${unit.material_id}/unit`,{params:{unit_id:unit.id}}),
  difficult: (unit, knowledgePoint) => request.post(`/study-sources/${unit.material_id}/difficult`,{unit_id:unit.id,knowledge_point:knowledgePoint || ''}),
  original: (id, params) => request.get(`/study-sources/${id}/original`,{params,responseType:'blob'}),
}
