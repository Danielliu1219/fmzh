<template>
  <div class="task-sources">
    <p v-if="loading" class="source-status">正在定位复习内容…</p>
    <template v-else>
      <p v-if="staleCount" class="source-status">{{ staleCount }} 项旧来源定位已失效；重新选择并加入任务时会替换失效关联。</p>
      <div v-for="item in matches.slice(0,2)" :key="item.id" class="source-shortcut">
        <button type="button" :aria-label="sourceLabel(item)" @click.stop="open(item)">
          <span class="source-file">{{ item.material_title }}</span>
          <strong class="source-location">{{ item.kind === 'question' ? '练习' : '阅读' }} · {{ item.label || item.location }} ↗</strong>
        </button>
        <small v-if="knowledgePoint" class="source-topic">对应知识点 · {{ knowledgePoint }}</small>
        <small>{{ sourceMethod(item,knowledgePoint,effectiveIds,citations) }}</small>
      </div>
      <button class="browse-source" type="button" @click.stop="browse">{{ matches.length>2 ? `还有 ${matches.length-2} 项 · 查看全部来源` : matches.length ? '浏览本科其他题目 / 课件' : error ? '来源加载失败 · 重试' : '暂无匹配来源 · 浏览题目 / 课件' }}</button>
    </template>
    <el-dialog v-model="visible" :title="selected ? '复习原题与课件' : '选择可定位的复习内容'" width="min(960px, 94vw)" append-to-body destroy-on-close @closed="selected=null">
      <template v-if="selected"><el-button text @click="selected=null">← 返回来源列表</el-button><el-button v-if="taskId" :loading="saving" @click="toggleSource">{{ effectiveIds.includes(selected.id) ? '取消本任务关联' : '将此来源加入本任务' }}</el-button><StudySourceViewer :key="selected.id" :unit="selected" :knowledge-point="knowledgePoint" /></template>
      <template v-else>
        <p class="source-status">题号由本地规则识别，请以原页为准。{{ knowledgePoint ? `当前知识点：${knowledgePoint}` : '' }}</p>
        <div class="source-filters"><el-input v-model="query" placeholder="搜索资料、题号、页码或知识点" clearable /><el-select v-model="kind" aria-label="筛选练习或阅读"><el-option label="题目和课件" value="" /><el-option label="题目练习" value="question" /><el-option label="课件 / 知识阅读" value="reading" /></el-select><el-checkbox v-if="matches.length" v-model="onlyMatched">仅当前知识点</el-checkbox></div>
        <p v-if="!filtered.length">{{ error || '没有可定位内容。请先上传并解析资料；无法识别题号时会保留原页/段落供核对。' }}</p>
        <ul class="source-list"><li v-for="item in filtered.slice((page-1)*20,page*20)" :key="item.id"><button type="button" @click="selected=item"><strong>{{ sourceLabel(item) }}</strong><span v-if="item.kind !== 'question'">{{ item.preview }}</span><small>{{ sourceMethod(item,knowledgePoint,effectiveIds) }}{{ item.knowledge_points?.length ? ' · '+item.knowledge_points.map(p=>p.name).filter((v,i,a)=>a.indexOf(v)===i).join(' / ') : '' }}</small></button></li></ul>
        <el-pagination v-if="filtered.length>20" v-model:current-page="page" :page-size="20" :total="filtered.length" layout="prev, pager, next" />
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { sourceApi } from '../api/studySources'
import { matchingSources, sourceLabel, sourceMethod } from '../utils/studySources'
import { USE_MOCK } from '../mock/dashboard'
import StudySourceViewer from './StudySourceViewer.vue'
import { taskApi } from '../api'
import { ElMessage } from 'element-plus'
const props=defineProps({examId:Number,analysisId:Number,taskId:Number,knowledgePoint:{type:String,default:''},sourceIds:{type:Array,default:()=>[]},citations:{type:Array,default:()=>[]}})
const emit=defineEmits(['updated'])
const items=ref([]),loading=ref(false),error=ref(''),visible=ref(false),selected=ref(null),query=ref(''),kind=ref(''),onlyMatched=ref(false),page=ref(1)
let sequence=0
const savedIds=ref(null),saving=ref(false)
const effectiveIds=computed(()=>savedIds.value ?? props.sourceIds)
const staleCount=computed(()=>error.value || loading.value ? 0 : effectiveIds.value.filter(id=>!items.value.some(item=>item.id===id)).length)
const matches=computed(()=>matchingSources(items.value,props.knowledgePoint,effectiveIds.value,props.citations))
watch(()=>[props.taskId,props.sourceIds],()=>{savedIds.value=null})
const filtered=computed(()=> (onlyMatched.value?matches.value:items.value).filter(u=>(!kind.value || u.kind===kind.value) && `${sourceLabel(u)} ${u.preview} ${u.knowledge_points.map(p=>p.name).join(' ')}`.toLowerCase().includes(query.value.trim().toLowerCase())))
watch([query,kind,onlyMatched],()=>page.value=1)
async function load(refresh=false){
  const seq=++sequence;items.value=[];error.value=''
  if(!props.examId || USE_MOCK){error.value=USE_MOCK?'演示模式不读取私人原文件，请在本地应用中上传资料。':'';return}
  loading.value=true
  try{const result=await sourceApi.library(props.examId,props.analysisId,refresh);if(seq===sequence)items.value=result.items}
  catch(e){if(seq===sequence)error.value=e?.response?.data?.detail || e.message}
  finally{if(seq===sequence)loading.value=false}
}
watch(()=>[props.examId,props.analysisId],()=>{visible.value=false;selected.value=null;load()},{immediate:true})
function open(item){selected.value=item;visible.value=true}
async function browse(){await load(true);onlyMatched.value=matches.value.length>0;selected.value=null;visible.value=true}
async function toggleSource(){
  const id=selected.value.id
  const current=effectiveIds.value.filter(s=>items.value.some(item=>item.id===s))
  const ids=current.includes(id)?current.filter(s=>s!==id):[...current,id]
  if(ids.length>8){ElMessage.warning('每项任务最多关联8个来源，请先移除不需要的内容。');return}
  saving.value=true
  try{const task=await taskApi.update(props.taskId,{source_ids:ids});savedIds.value=task.source_ids;emit('updated',task);ElMessage.success('任务来源已保存')}
  catch(e){if(!e.notified)ElMessage.error(e.message || '保存失败')}
  finally{saving.value=false}
}
</script>

<style scoped>
.source-shortcut { padding: 10px 14px; border-left: 3px solid var(--coral); background: var(--coral-soft); border-radius: 0 6px 6px 0; }
.source-file { display: block; color: var(--ink-2); font-size: 12px; }
.source-location { display: block; margin-top: 3px; font-size: 14px; color: var(--coral-deep); }
.source-shortcut .source-topic { margin-top: 5px; color: var(--ink-1); font-size: 12px; }
.source-shortcut button:focus-visible { outline: 2px solid var(--coral-deep); outline-offset: 3px; }
.task-sources {margin:10px 0;min-width:0;font-size:13px;line-height:1.7}.source-shortcut {margin:8px 0}.source-shortcut button,.browse-source {border:0;background:none;padding:0;color:var(--coral);cursor:pointer;text-align:left;font:inherit;overflow-wrap:anywhere}.source-shortcut small {display:block;color:var(--ink-3);font-size:11px}.browse-source {color:var(--ink-2);text-decoration:underline;text-underline-offset:4px}.source-status {font-size:12px;color:var(--ink-3)}.source-filters {display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.source-filters .el-input {flex:1;min-width:200px}.source-filters .el-select {width:170px}.source-list {list-style:none;padding:0}.source-list li {border-bottom:1px solid var(--line)}.source-list button {border:0;background:none;width:100%;text-align:left;padding:16px 0;cursor:pointer;color:var(--ink-1);font:inherit}.source-list strong,.source-list span,.source-list small {display:block;overflow-wrap:anywhere}.source-list span {margin:6px 0;color:var(--ink-2);font-size:13px}.source-list small {color:var(--ink-3);font-size:12px}
</style>
