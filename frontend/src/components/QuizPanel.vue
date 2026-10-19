<template>
  <section class="quiz-panel" aria-labelledby="quiz-title" v-loading="busy">
    <header class="quiz-heading">
      <div><p class="quiz-eyebrow">把掌握程度测出来</p><h2 id="quiz-title">自测练习</h2></div>
      <span class="quiz-subject">{{ subject }}</span>
    </header>
    <p v-if="error" class="quiz-error" role="alert">{{ error }}</p>
    <div v-if="!attempt" class="quiz-ready">
      <strong>{{ questions.length }}<small> 道客观题</small></strong>
      <p>先独立作答，再看答案与解析。错题会自动收入错题本，方便下次回顾。</p>
      <el-button type="primary" :disabled="busy || !questions.length" @click="start">开始自测</el-button>
      <el-button v-if="error" text @click="loadHistory">重新读取记录</el-button>
    </div>
    <template v-else-if="attempt.status === 'active'">
      <div class="quiz-progress"><span>第 {{ current+1 }} / {{ attempt.questions.length }} 题</span><span>已作答 {{ answered }} 题</span></div>
      <el-progress :percentage="Math.round(answered / attempt.questions.length * 100)" :show-text="false" :stroke-width="4" color="#35554c" />
      <nav class="quiz-number-nav" aria-label="自测题号"><button v-for="(q, i) in attempt.questions" :key="i" :class="{ current: current===i, answered: hasAnswer(answers[i]) }" :aria-label="`第 ${i+1} 题${hasAnswer(answers[i]) ? '，已作答' : ''}`" :aria-current="current===i ? 'step' : undefined" @click="current=i">{{ i+1 }}</button></nav>
      <div class="quiz-question" :key="current">
        <span class="quiz-kind">{{ quizKindLabel(active.kind) }}<span v-if="active.knowledge_point"> · {{ active.knowledge_point }}</span></span>
        <h3 :id="`quiz-question-${current}`">{{ active.question }}</h3>
        <el-radio-group v-if="active.kind==='single'" v-model="answers[current]" class="quiz-choices" :aria-labelledby="`quiz-question-${current}`">
          <el-radio v-for="o in active.options" :key="o.value" :value="o.value" border>{{ o.value }}. {{ o.label }}</el-radio>
        </el-radio-group>
        <el-checkbox-group v-else-if="active.kind==='multiple'" v-model="answers[current]" class="quiz-choices" :aria-labelledby="`quiz-question-${current}`">
          <el-checkbox v-for="o in active.options" :key="o.value" :value="o.value" border>{{ o.value }}. {{ o.label }}</el-checkbox>
        </el-checkbox-group>
        <el-radio-group v-else-if="active.kind==='boolean'" v-model="answers[current]" class="quiz-choices" :aria-labelledby="`quiz-question-${current}`"><el-radio value="true" border>正确</el-radio><el-radio value="false" border>错误</el-radio></el-radio-group>
        <el-input v-else v-model="answers[current]" :aria-labelledby="`quiz-question-${current}`" placeholder="填写你的答案" maxlength="1000" />
        <p class="quiz-rule">{{ active.kind==='multiple' ? '多选题须选全且没有错选才得分。' : active.kind==='fill' ? '填空按参考答案及明确的等价写法判分，忽略首尾空白与全半角差异，区分字母大小写。' : '每题等分，提交后统一显示结果。' }}</p>
      </div>
      <footer class="quiz-actions"><el-button :disabled="current===0 || busy" @click="current--">上一题</el-button><span>{{ USE_MOCK ? '作答在当前演示会话中保留' : '作答草稿保存在当前浏览器' }}</span><el-button v-if="current < attempt.questions.length-1" type="primary" @click="current++">下一题</el-button><el-button v-else type="primary" :disabled="busy" @click="submit">提交并查看结果</el-button></footer>
    </template>
    <template v-else-if="attempt.result">
      <div class="quiz-result" aria-live="polite"><div class="quiz-score"><strong>{{ attempt.result.score }}</strong><small> / 100</small></div><div><h3>答对 {{ attempt.result.correct }} / {{ attempt.result.total }} 题</h3><p>{{ attempt.result.wrong ? `有 ${attempt.result.wrong} 道需要再练习，已自动收入错题本；重复错题不会重复添加。` : '这一轮全部答对，继续按计划巩固。' }}</p><small v-if="attempt.result.unanswered">其中 {{ attempt.result.unanswered }} 道未作答，按答错计入。</small></div></div>
      <div class="quiz-result-actions"><el-button type="primary" @click="start">再测一轮</el-button><router-link :to="{path:'/materials',query:{view:'collection'}}">查看错题本 ↗</router-link></div>
      <div class="quiz-review"><details v-for="(item, index) in attempt.result.items" :key="index" :open="!item.correct"><summary><span :class="item.correct ? 'is-correct' : 'is-wrong'">{{ item.correct ? '答对' : item.unanswered ? '未作答' : '答错' }}</span><b>{{ index+1 }}. {{ item.question }}</b></summary><QuizFeedback :item="item" /></details></div>
    </template>
    <div v-if="history.length" class="quiz-history"><span>最近自测</span><button v-for="h in history" :key="h.id" :class="{ selected: attempt?.id===h.id }" @click="openAttempt(h.id)">{{ h.status==='active' ? '继续作答' : `${h.score} 分` }} · {{ formatDate(h.created_at) }}</button></div>
    <p class="quiz-footnote">{{ USE_MOCK ? '交互演示：结果与错题仅在当前会话有效，刷新后恢复。' : '结果与错题按当前账号保存。自动判分依据题目参考答案，生成内容请结合教材核对。' }}</p>
  </section>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { quizApi } from '../api'
import { USE_MOCK } from '../mock/dashboard'
import { mockQuizHistory, mockQuizDetail, startMockQuiz, submitMockQuiz, saveMockQuizDraft } from '../mock/quizzes'
import { quizKindLabel, validQuizDraft } from '../utils/quiz'
import { readSession } from '../utils/session'
import QuizFeedback from './QuizFeedback.vue'

const props = defineProps({ analysisId: { type: [Number,String], required:true }, questions: { type:Array, default:()=>[] }, subject: { type:String, default:'' } })
const attempt=ref(null), answers=ref([]), current=ref(0), busy=ref(false), error=ref(''), history=ref([])
const active=computed(()=>attempt.value?.questions[current.value])
const hasAnswer=a=>Array.isArray(a) ? a.length>0 : typeof a==='string' && a.trim().length>0
const answered=computed(()=>answers.value.filter(hasAnswer).length)
const formatDate=s=>new Date(s).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})
const draftKey=()=>{const u=readSession().user; return `fmzh_quiz_draft:${u?.id || u?.username}:${u?.created_at || 'demo'}:${attempt.value?.id}`}
let restoring=false
const restore=a=>{
  restoring=true
  attempt.value=a; current.value=0
  answers.value=a.questions.map(q=>q.kind==='multiple' ? [] : '')
  if(a.status==='active') {
    try {const draft=USE_MOCK ? a.draft_answers : JSON.parse(localStorage.getItem(draftKey()) || 'null'); if(validQuizDraft(draft,a.questions)) answers.value=draft} catch { /* discard malformed draft */ }
  }
  restoring=false
}
watch(answers,value=>{
  if(restoring || attempt.value?.status!=='active') return
  if(USE_MOCK) saveMockQuizDraft(attempt.value.id,value)
  else try {localStorage.setItem(draftKey(),JSON.stringify(value))} catch {/* private storage may be unavailable */}
}, {deep:true,flush:'sync'})
const refreshHistory=async()=>{history.value=USE_MOCK ? mockQuizHistory(props.analysisId) : await quizApi.history(props.analysisId)}
const openAttempt=async id=>{
  busy.value=true; error.value=''
  try {restore(USE_MOCK ? mockQuizDetail(id) : await quizApi.detail(id))} catch {error.value='自测记录暂时无法读取，请重试。'} finally {busy.value=false}
}
const loadHistory=async()=>{
  busy.value=true; error.value=''
  try {await refreshHistory(); if(history.value.length) restore(USE_MOCK ? mockQuizDetail(history.value[0].id) : await quizApi.detail(history.value[0].id))} catch {error.value='历史记录暂时无法读取，请重试。'} finally {busy.value=false}
}
const start=async()=>{
  busy.value=true; error.value=''
  try {restore(USE_MOCK ? startMockQuiz(props.analysisId,props.subject,props.questions) : await quizApi.start(props.analysisId)); await refreshHistory()} catch {error.value='暂时无法开始自测，请稍后重试或重新生成分析。'} finally {busy.value=false}
}
const submit=async()=>{
  if(answered.value<attempt.value.questions.length) {
    try {await ElMessageBox.confirm(`还有 ${attempt.value.questions.length-answered.value} 道未作答，提交后将按答错计入错题本。确认提交？`,'提交自测',{confirmButtonText:'确认提交',cancelButtonText:'继续作答'})} catch {return}
  }
  busy.value=true; error.value=''
  try {const result=USE_MOCK ? submitMockQuiz(attempt.value.id,answers.value) : await quizApi.submit(attempt.value.id,answers.value); localStorage.removeItem(draftKey()); restore(result); await refreshHistory()} catch {error.value='提交暂未完成，作答已保留。请重试；重复提交不会重复记分或添加错题。'} finally {busy.value=false}
}
onMounted(loadHistory)
</script>
<style scoped>
.quiz-panel { padding: 28px; margin: 24px 0; border: 1px solid var(--ink-1); border-radius: 10px; background: var(--bg-card, #f8f5ec); box-shadow: 4px 4px 0 var(--line); }
.quiz-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.quiz-eyebrow { color: var(--ink-3); font-size: 11px; margin: 0 0 8px; }
.quiz-heading h2 { margin: 0; font: 700 25px/1.3 var(--font-serif); }
.quiz-subject,.quiz-kind { font-size: 12px; color: var(--ink-3); }
.quiz-ready { padding: 18px 0 28px; max-width: 560px; }.quiz-ready strong { font: 500 40px/1 var(--font-num); }.quiz-ready strong small { font: 14px var(--font-sans); }.quiz-ready p { color: var(--ink-2); line-height: 1.8; font-size: 14px; margin: 18px 0 24px; }
.quiz-progress { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 12px; color: var(--ink-2); }
.quiz-number-nav { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0; }
.quiz-number-nav button,.quiz-history button { background: transparent; border: 1px solid var(--line); color: var(--ink-2); cursor: pointer; border-radius: 4px; transition: background .2s, color .2s; }
.quiz-number-nav button { width: 34px; height: 34px; }.quiz-number-nav button.answered { border-color: #35554c; color: #35554c; }.quiz-number-nav button.current { background: var(--ink-1); color: var(--bg-page); }
.quiz-number-nav button:focus-visible,.quiz-history button:focus-visible { outline: 2px solid var(--coral-deep); outline-offset: 3px; }
.quiz-question { min-height: 220px; padding: 12px 0 20px; }.quiz-question h3 { font-size: 18px; line-height: 1.7; margin: 12px 0 24px; overflow-wrap: anywhere; }
.quiz-choices { display: grid; gap: 10px; width: 100%; }.quiz-choices :deep(.el-radio),.quiz-choices :deep(.el-checkbox) { height: auto; min-height: 46px; margin: 0; padding: 12px 16px; width: 100%; }.quiz-choices :deep(.el-radio__label),.quiz-choices :deep(.el-checkbox__label) { white-space: normal; line-height: 1.6; overflow-wrap: anywhere; }
.quiz-rule,.quiz-footnote { font-size: 11px; color: var(--ink-3); line-height: 1.8; }.quiz-rule { margin: 16px 0 0; }.quiz-footnote { margin: 20px 0 0; }
.quiz-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; border-top: 1px solid var(--line); padding-top: 20px; }.quiz-actions>span { font-size: 11px; color: var(--ink-3); }.quiz-actions :deep(.el-button+.el-button) { margin-left: 0; }
.quiz-result { display: flex; gap: 28px; align-items: center; padding: 16px 0 28px; }.quiz-score { white-space: nowrap; }.quiz-score strong { font: 500 64px/1 var(--font-num); color: #35554c; }.quiz-score small { color: var(--ink-3); }.quiz-result h3 { margin: 0 0 12px; font-size: 18px; }.quiz-result p,.quiz-result small { line-height: 1.8; color: var(--ink-2); font-size: 13px; margin: 0; }
.quiz-result-actions { display: flex; align-items: center; gap: 24px; margin-bottom: 24px; }.quiz-result-actions a { color: var(--coral-deep); font-size: 13px; }
.quiz-review details { border-top: 1px solid var(--line); padding: 18px 0; }.quiz-review summary { cursor: pointer; display: flex; gap: 14px; line-height: 1.7; font-size: 13px; }.quiz-review summary b { flex: 1; overflow-wrap: anywhere; }.quiz-review :deep(.quiz-feedback) { padding: 16px 0 0; }.is-correct { color: #35554c; white-space: nowrap; }.is-wrong { color: var(--coral-deep); white-space: nowrap; }
.quiz-history { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; border-top: 1px solid var(--line); padding-top: 18px; margin-top: 12px; font-size: 11px; }.quiz-history>span { margin-right: 8px; color: var(--ink-3); }.quiz-history button { padding: 7px 10px; }.quiz-history button.selected { border-color: var(--ink-2); background: var(--bg-page); }.quiz-history button:hover { background: var(--bg-page); }
.quiz-error { color: var(--coral-deep); font-size: 13px; line-height: 1.8; }
@media(max-width:600px) { .quiz-panel { padding: 20px 16px; }.quiz-heading h2 { font-size: 21px; }.quiz-subject { max-width: 40%; overflow-wrap: anywhere; }.quiz-result { flex-direction: column; align-items: flex-start; gap: 18px; }.quiz-actions { flex-wrap: wrap; }.quiz-actions>span { width: 100%; order: 3; }.quiz-question h3 { font-size: 16px; }.quiz-review summary { gap: 10px; } }
</style>

