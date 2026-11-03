<template>
  <section v-if="data" class="source-study" v-loading="busy">
    <h3>{{ data.material_title }}</h3><p>{{ data.label }}</p>
    <p class="note">{{ data.recognition }}<span v-if="data.subquestions.length"> 包含小问 {{ data.subquestions.join('、') }}，共同题干一并保留。</span></p>
    <OriginalSource :key="data.id" :material-id="data.material_id" :file-type="data.file_type" :title="data.material_title" :pages="data.pages" :unit-id="data.id" :revision="data.revision" auto-preview />
    <details :open="!data.pages.length"><summary>{{ data.kind === 'question' ? '查看识别题干（公式以原页为准）' : '查看该页/段落的识别文字' }}</summary><pre>{{ data.question_text }}</pre></details>
    <div class="study-actions">
      <el-button @click="showSteps=!showSteps">{{ showSteps ? '收起复习步骤' : '分步复习' }}</el-button>
      <el-button @click="showAnswer=!showAnswer">{{ data.original_answer ? '对照原文答案' : '查看答案情况' }}</el-button>
      <el-button :loading="saving" @click="markDifficult">标记不会 · 加入错题本</el-button>
    </div>
    <ol v-if="showSteps"><li v-for="step in data.steps" :key="step">{{ step }}</li></ol>
    <div v-if="showAnswer" class="answer"><p class="note">{{ data.answer_note }}</p><pre>{{ data.original_answer || '这个片段没有明确标注答案。可以下载原文件查看其他页；也可以主动请 AI 提供参考解答。' }}</pre></div>
    <div class="ai-help"><p class="note">以下按钮会额外调用大模型并消耗你的 Token；不会自动调用。公式识别不完整时，请先核对原页。</p>
      <el-button :loading="asking==='hint'" :disabled="!!asking" @click="ask('hint')">请 AI 给解题提示</el-button>
      <el-button :loading="asking==='answer'" :disabled="!!asking" @click="ask('answer')">请 AI 给参考解答</el-button>
    </div>
    <p v-if="aiError" role="alert">{{ aiError }}</p><pre v-if="aiAnswer" class="answer">{{ aiAnswer }}</pre>
  </section>
  <p v-else-if="busy" role="status">正在读取来源…</p>
  <el-alert v-else-if="error" :title="error" type="warning" :closable="false" />
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { sourceApi } from '../api/studySources'
import { aiApi } from '../api'
import OriginalSource from './OriginalSource.vue'
const props=defineProps({unit:{type:Object,required:true},knowledgePoint:String})
const data=ref(null),busy=ref(false),error=ref(''),showSteps=ref(false),showAnswer=ref(false),saving=ref(false),asking=ref(''),aiAnswer=ref(''),aiError=ref('')
let sequence=0,conversation=null
watch(()=>props.unit.id,async()=>{
  const seq=++sequence; data.value=null;busy.value=true;error.value='';showSteps.value=false;showAnswer.value=false;aiAnswer.value='';aiError.value='';asking.value='';conversation=null
  try {const result=await sourceApi.unit(props.unit);if(seq===sequence)data.value=result}
  catch(e){if(seq===sequence)error.value=e?.response?.data?.detail || e.message}
  finally{if(seq===sequence)busy.value=false}
},{immediate:true})
async function markDifficult(){
  saving.value=true
  try {
    await sourceApi.difficult(data.value,props.knowledgePoint)
    ElMessage.success('已加入错题本')
  } catch(e){if(!e.notified)ElMessage.error(e.message || '保存失败')}
  finally{saving.value=false}
}
async function ask(kind){
  const seq=sequence, unit=data.value;asking.value=kind;aiError.value=''
  try{
    const conversationId=conversation || (await aiApi.createQaConversation(unit.exam_id)).id
    if(seq!==sequence)return
    conversation=conversationId
    const content=`请针对本次指定来源${kind==='hint'?'只给分步提示，先不要公布最终答案':'给出参考解答并说明关键步骤；不确定的识别内容请指出，不能当作原卷标准答案'}。\n来源：${unit.material_title} · ${unit.label}\n知识点：${props.knowledgePoint || '请依据原文判断'}`.slice(0,1900)
    const result=await aiApi.askQa(conversation,content,{source_material_id:unit.material_id,source_unit_id:unit.id})
    if(seq===sequence)aiAnswer.value=result.messages.filter(m=>m.role==='assistant').at(-1)?.content || ''
  }catch(e){if(seq===sequence)aiError.value=e?.response?.data?.detail || e.message}
  finally{if(seq===sequence)asking.value=''}
}
onBeforeUnmount(()=>{sequence++})
</script>

<style scoped>
.source-study h3 { margin:0 0 8px; }.note { color:var(--ink-3); font-size:12px;line-height:1.8; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; line-height:1.9; padding:16px; background:var(--bg-page); }
details { margin:16px 0; }summary { cursor:pointer; }li { line-height:1.9; margin:8px 0; }
.study-actions {display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.study-actions .el-button {margin:0}
.ai-help { border-top:1px solid var(--line);padding-top:12px; }.answer {border-left:3px solid var(--coral);}
</style>
