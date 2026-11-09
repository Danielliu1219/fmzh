<template>
  <section v-if="data" class="source-study">
    <h3>{{ data.material_title }}</h3>
    <p>{{ data.label }}</p>
    <p class="note">{{ data.recognition }}<span v-if="data.subquestions.length"> 包含小问 {{ data.subquestions.join('、') }}。</span></p>
    <OriginalSource :key="data.id" :material-id="data.material_id" :file-type="data.file_type" :title="data.material_title" :pages="data.pages" :unit-id="data.id" :revision="data.revision" auto-preview />
    <details :open="!!data.input_hash">
      <summary>{{ data.input_hash ? '已重新识别的原题与公式' : data.kind === 'question' ? '查看识别文字（可能缺失公式，请以原页为准）' : '查看该页/段落的识别文字' }}</summary>
      <MarkdownContent v-if="data.input_hash" :content="data.question_text" />
      <pre v-else>{{ data.question_text }}</pre>
    </details>
    <div class="study-actions">
      <el-button @click="showSteps = !showSteps">{{ showSteps ? '收起复习步骤' : '分步复习' }}</el-button>
      <el-button @click="showAnswer = !showAnswer">{{ data.original_answer ? '对照原文答案' : '查看答案情况' }}</el-button>
      <el-button :loading="saving" @click="markDifficult">标记不会 · 加入错题本</el-button>
    </div>
    <ol v-if="showSteps"><li v-for="step in data.steps" :key="step">{{ step }}</li></ol>
    <div v-if="showAnswer" class="answer">
      <p class="note">{{ data.answer_note }}</p>
      <pre>{{ data.original_answer || '这个片段没有明确标注答案。可以下载原文件查看其他页，也可以主动请大模型提供参考解答。' }}</pre>
    </div>
    <section class="ai-help" aria-label="大模型题目问答">
      <p class="note">已生成内容自动保存，重新打开可直接查看。首次生成和重新生成会消耗 Token。公式识别不完整时，请先核对原页。</p>
      <p v-if="historyLoading" role="status">正在读取已保存的提示与解答…</p>
      <p v-if="historyError" role="alert">{{ historyError }} <el-button text @click="restore">重试读取</el-button></p>
      <div class="study-actions">
        <el-button :loading="asking === 'hint'" :disabled="helpDisabled" @click="ask('hint')">{{ latest('hint') ? '查看已保存提示' : '请大模型给解题提示' }}</el-button>
        <el-button :loading="asking === 'answer'" :disabled="helpDisabled" @click="ask('answer')">{{ latest('answer') ? '查看已保存解答' : '请大模型给参考解答' }}</el-button>
      </div>
      <p v-if="asking" class="note" role="status">正在生成{{ kindLabel(asking) }}，完成后自动保存。关闭窗口后仍可重新打开查看。</p>
      <AnalysisWait v-if="asking" :job="modelProgress" kind="qa" />
      <p v-if="aiError" role="alert">{{ aiError }}</p>
      <article v-if="asking && modelProgress?.progress?.content" class="answer ai-answer" aria-label="正在生成的解答">
        <h4>{{ kindLabel(asking) }} · 正在生成</h4>
        <p class="reference-notice" role="note">大模型生成，仅供参考。当前内容尚未完整生成，请等待保存后核对。</p>
        <MarkdownContent :content="modelProgress.progress.content" />
      </article>
      <article v-if="selectedAnswer" class="answer ai-answer">
        <header class="answer-header">
          <h4>{{ kindLabel(selectedAnswer.kind) }}</h4>
          <el-select v-model="selectedId" aria-label="查看已保存的提示与解答">
            <el-option v-for="answer in [...answers].reverse()" :key="answer.id" :value="answer.id" :label="kindLabel(answer.kind) + ' · ' + savedTime(answer.created_at)" />
          </el-select>
        </header>
        <p class="reference-notice" role="note">大模型生成，仅供参考，可能存在错误，不保证答案正确。请结合原题、教材和教师提供的答案核对。</p>
        <p v-if="selectedAnswer.current_input === false" class="note">此回答使用旧版识别文字生成，可使用当前已重新识别的公式生成新版回答。</p>
        <MarkdownContent :content="selectedAnswer.content" />
        <footer class="answer-footer">
          <span class="note">已保存 · {{ savedTime(selectedAnswer.created_at) }} · 再次查看不消耗 Token</span>
          <el-button text :disabled="helpDisabled" @click="ask(selectedAnswer.kind, true)">重新生成{{ kindLabel(selectedAnswer.kind) }}（消耗 Token）</el-button>
        </footer>
      </article>
    </section>
  </section>
  <p v-else-if="busy" role="status">正在读取并识别原题与公式，首次加载需要下载本机模型，完成后会自动缓存…</p>
  <el-alert v-else-if="error" :title="error" type="warning" :closable="false" />
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { sourceApi } from '../api/studySources'
import { aiApi } from '../api'
import { resumeModelJob } from '../api/modelJobs'
import OriginalSource from './OriginalSource.vue'
import MarkdownContent from './MarkdownContent.vue'
import AnalysisWait from './AnalysisWait.vue'

const props = defineProps({ unit: { type: Object, required: true }, knowledgePoint: String })
const data = ref(null), busy = ref(false), error = ref('')
const showSteps = ref(false), showAnswer = ref(false), saving = ref(false)
const asking = ref(''), aiError = ref(''), historyLoading = ref(false), historyError = ref('')
const answers = ref([]), selectedId = ref(null)
const modelProgress = ref(null)
const selectedAnswer = computed(() => answers.value.find(answer => answer.id === selectedId.value))
const helpDisabled = computed(() => !!asking.value || historyLoading.value || !!historyError.value)
let sequence = 0

const kindLabel = kind => kind === 'hint' ? '解题提示' : '参考解答'
const latest = kind => answers.value.findLast(answer => answer.kind === kind && answer.current_input !== false)
const savedTime = value => new Date(value).toLocaleString('zh-CN', { hour12: false })
const errorMessage = e => e?.response?.data?.detail || e.message

async function readHistory(seq, kind) {
  const result = await sourceApi.aiHelp(data.value)
  if (seq !== sequence) return null
  answers.value = result.messages
  selectedId.value = (kind && latest(kind)?.id) || selectedAnswer.value?.id || answers.value.at(-1)?.id || null
  return result
}

async function resumeJobs(jobs, seq) {
  asking.value = jobs[0].kind
  const results = await Promise.allSettled(jobs.map(job => resumeModelJob(job.id, progress => {
    if (seq === sequence) modelProgress.value = progress
  })))
  if (seq !== sequence) return
  const failure = results.find(result => result.status === 'rejected')
  if (failure) aiError.value = errorMessage(failure.reason)
  await readHistory(seq, jobs.at(-1).kind)
}

async function restore() {
  const seq = sequence
  historyLoading.value = true
  historyError.value = ''
  aiError.value = ''
  try {
    const result = await readHistory(seq)
    if (result?.pending_jobs.length) await resumeJobs(result.pending_jobs, seq)
  } catch (e) {
    if (seq === sequence) historyError.value = '已保存内容读取失败，请重试后再生成。' + errorMessage(e)
  } finally {
    if (seq === sequence) { historyLoading.value = false; asking.value = '' }
  }
}

watch(() => props.unit.id, async () => {
  const seq = ++sequence
  data.value = null; busy.value = true; error.value = ''
  showSteps.value = false; showAnswer.value = false; asking.value = ''; aiError.value = ''
  modelProgress.value = null
  answers.value = []; selectedId.value = null; historyError.value = ''; historyLoading.value = false
  try {
    const result = await sourceApi.unit(props.unit)
    if (seq !== sequence) return
    data.value = result
    busy.value = false
    await restore()
  } catch (e) {
    if (seq === sequence) error.value = errorMessage(e)
  } finally {
    if (seq === sequence) busy.value = false
  }
}, { immediate: true })

async function markDifficult() {
  saving.value = true
  try {
    await sourceApi.difficult(data.value, props.knowledgePoint)
    ElMessage.success('已加入错题本')
  } catch (e) {
    if (!e.notified) ElMessage.error(e.message || '保存失败')
  } finally { saving.value = false }
}

async function ask(kind, regenerate = false) {
  if (helpDisabled.value) return
  const seq = sequence, unit = data.value
  asking.value = kind; aiError.value = ''
  modelProgress.value = { status: 'submitting', startedAt: Date.now() }
  try {
    // 每次操作先核对服务器，复用其他窗口已保存或正在生成的结果。
    const saved = await readHistory(seq, kind)
    if (!saved) return
    if (saved.pending_jobs.length) { await resumeJobs(saved.pending_jobs, seq); return }
    if (!regenerate && latest(kind)) return
    const conversationId = latest(kind)?.conversation_id || (await aiApi.createQaConversation(unit.exam_id)).id
    if (seq !== sequence) return
    const instruction = kind === 'hint' ? '只给分步提示，先不要公布最终答案' : '给出参考解答并说明关键步骤'
    const content = ('请针对本次指定来源' + instruction + '。只标注题号和位置，不复述识别题干。公式或条件缺失时请明确指出并请用户补充，不得猜测或另设题目。使用 Markdown 和 LaTeX 排版。\n来源：' + unit.material_title + ' · ' + unit.label + '\n知识点：' + (data.value.input_hash ? '请依据重新识别的原题判断' : props.knowledgePoint || '请依据原文判断')).slice(0, 1900)
    await aiApi.askQa(conversationId, content, {
      source_material_id: unit.material_id, source_unit_id: unit.id,
      source_help_kind: kind, source_regenerate: regenerate,
      source_input_hash: data.value.input_hash || undefined,
    }, progress => { if (seq === sequence) modelProgress.value = progress })
    if (seq === sequence) await readHistory(seq, kind)
  } catch (e) {
    if (seq === sequence) {
      aiError.value = errorMessage(e)
      try { await readHistory(seq, kind) }
      catch { historyError.value = '已保存内容读取失败，请重试读取。' }
    }
  } finally { if (seq === sequence) asking.value = '' }
}
onBeforeUnmount(() => { sequence++ })
</script>

<style scoped>
.source-study { min-width:0; }
.source-study h3 { margin:0 0 8px; }
.note { color:var(--ink-3); font-size:12px; line-height:1.8; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; line-height:1.9; padding:16px; background:var(--bg-page); }
details { margin:16px 0; } summary { cursor:pointer; } li { line-height:1.9; margin:8px 0; }
.study-actions { display:flex; gap:8px; flex-wrap:wrap; margin:16px 0; }
.study-actions .el-button { margin:0; }
.ai-help { border-top:1px solid var(--line); padding-top:12px; }
.answer { border-left:3px solid var(--coral); background:var(--bg-page); }
.ai-answer { margin-top:20px; padding:20px; }
.answer-header { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.answer-header h4 { margin:0; font-size:16px; color:var(--ink-1); }
.answer-header .el-select { width:280px; max-width:100%; }
.reference-notice { margin:16px 0 20px; padding:12px 14px; border:1px solid var(--coral); color:var(--ink-2); font-size:13px; line-height:1.8; }
.answer-footer { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; margin-top:24px; padding-top:12px; border-top:1px solid var(--line); }
@media (max-width:600px) { .ai-answer { padding:14px; } .answer-header .el-select { width:100%; } }
</style>
