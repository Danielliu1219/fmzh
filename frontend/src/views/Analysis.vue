<template>
  <div>
    <div class="page-head">
      <h2>AI 复习分析</h2>
      <el-select v-model="examId" placeholder="选择要分析的科目" style="width: 240px" @change="onExamChange">
        <el-option v-for="e in exams" :key="e.id" :label="`${e.subject}（${e.exam_date}）`" :value="e.id" />
      </el-select>
    </div>

    <el-empty v-if="!examId" description="请先选择科目（在考试管理里录入考试）">
      <el-button type="primary" @click="$router.push('/exams')">去录入考试</el-button>
    </el-empty>

    <template v-else>
      <el-steps :active="step" align-center finish-status="success" class="steps">
        <el-step title="描述学习状态" description="自然语言一句话" />
        <el-step title="确认画像" description="系统提取的 JSON" />
        <el-step title="查看分析" description="权重 / 计划 / 自测题" />
      </el-steps>

      <!-- 第一步：自然语言描述 -->
      <el-card v-if="step === 0" shadow="never" class="step-card">
        <el-input
          v-model="rawText"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="用一句话描述你的情况，例如：&#10;我这门课基本没学，只想及格，极限和积分不太会，还有五天考试，每天能学三小时"
        />
        <div class="actions">
          <el-button type="primary" :loading="profileLoading" :disabled="!rawText.trim()" @click="onExtractProfile">
            生成学习画像
          </el-button>
        </div>
      </el-card>

      <!-- 第二步：画像确认 / 补全 -->
      <el-card v-if="step === 1" shadow="never" class="step-card">
        <el-descriptions :column="2" border title="系统提取的学习画像">
          <el-descriptions-item label="备考目标">
            {{ targetText(profile.target) || '（未提取到）' }}
          </el-descriptions-item>
          <el-descriptions-item label="基础水平">
            {{ statusText(profile.learning_status) || '（未提取到）' }}
          </el-descriptions-item>
          <el-descriptions-item label="剩余天数">
            {{ profile.available_days ?? '（未提取到）' }} 天
          </el-descriptions-item>
          <el-descriptions-item label="每天可投入">
            {{ profile.daily_hours ?? '（未提取到）' }} 小时
          </el-descriptions-item>
          <el-descriptions-item label="薄弱章节" :span="2">
            {{ profile.weak_chapters?.length ? profile.weak_chapters.join('、') : '（未提到）' }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 画像不完整：展示补全表单 -->
        <el-alert
          v-if="!profile.is_complete"
          type="warning"
          :closable="false"
          show-icon
          class="complete-alert"
          :title="`画像还缺少：${missingFieldLabels.join('、')}，请补全后继续`"
        />
        <div v-if="!profile.is_complete" class="complete-form">
          <el-form label-width="100px">
            <el-form-item v-if="missing.includes('target')" label="备考目标">
              <el-radio-group v-model="completeForm.target">
                <el-radio-button value="pass">保及格</el-radio-button>
                <el-radio-button value="medium">稳中等</el-radio-button>
                <el-radio-button value="high">冲高分</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="missing.includes('learning_status')" label="基础水平">
              <el-radio-group v-model="completeForm.learning_status">
                <el-radio-button value="weak">基础薄弱</el-radio-button>
                <el-radio-button value="medium">基础一般</el-radio-button>
                <el-radio-button value="good">基础良好</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="missing.includes('available_days')" label="剩余天数">
              <el-input-number v-model="completeForm.available_days" :min="1" :max="60" />
              <span class="unit">天</span>
            </el-form-item>
            <el-form-item v-if="missing.includes('daily_hours')" label="每天可投入">
              <el-input-number v-model="completeForm.daily_hours" :min="0.5" :max="16" :step="0.5" />
              <span class="unit">小时</span>
            </el-form-item>
          </el-form>
          <div class="actions">
            <el-button @click="onBackToDescribe">重新描述</el-button>
            <el-button type="primary" :loading="profileLoading" :disabled="!completeFormValid" @click="onCompleteProfile">
              提交补全
            </el-button>
          </div>
        </div>

        <!-- 画像完整：进入分析 -->
        <div v-else class="actions">
          <el-button @click="onBackToDescribe">重新描述</el-button>
          <el-button type="primary" :loading="analyzing" @click="onAnalyze">
            <el-icon><MagicStick /></el-icon>&nbsp;生成复习分析
          </el-button>
        </div>
      </el-card>

      <!-- 第三步：分析结果 -->
      <template v-if="step === 2 && result">
        <el-card shadow="never" class="result-card">
          <div class="result-head">
            <h3>{{ result.course }} · 复习分析</h3>
            <el-button :loading="analyzing" @click="onAnalyze">重新生成</el-button>
          </div>
          <el-alert type="info" :closable="false" :title="result.summary" />
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header><b>知识点权重</b><span class="hint">权重越高越优先复习</span></template>
          <el-table :data="result.knowledge_points" size="large">
            <el-table-column prop="name" label="知识点" min-width="140">
              <template #default="{ row }"><b>{{ row.name }}</b></template>
            </el-table-column>
            <el-table-column label="权重" min-width="180">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round(row.weight * 100)"
                  :stroke-width="12"
                  :color="weightColor(row.weight)"
                />
              </template>
            </el-table-column>
            <el-table-column label="重要程度" width="100">
              <template #default="{ row }">
                <el-tag :type="{ high: 'danger', medium: 'warning', low: 'info' }[row.importance]">
                  {{ { high: '高', medium: '中', low: '低' }[row.importance] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="suggest_hours" label="建议投入" width="90">
              <template #default="{ row }">{{ row.suggest_hours }} 小时</template>
            </el-table-column>
            <el-table-column prop="recommend_reason" label="推荐理由" min-width="160" />
            <el-table-column prop="source" label="依据来源" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.source" size="small" type="success" effect="plain">{{ row.source }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header><b>常考点 / 必考点</b></template>
          <el-timeline>
            <el-timeline-item
              v-for="(f, i) in result.exam_focus"
              :key="i"
              :type="f.level === 'must' ? 'danger' : 'primary'"
              :hollow="f.level !== 'must'"
            >
              <el-tag size="small" :type="f.level === 'must' ? 'danger' : 'primary'" class="focus-tag">
                {{ f.level === 'must' ? '必考' : '常考' }}
              </el-tag>
              {{ f.content }}
              <div class="focus-basis">依据：{{ f.basis }}（{{ f.source }}）</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header><b>复习计划</b><span class="hint">已自动生成每日任务，去首页打卡吧</span></template>
          <el-table :data="result.review_plan">
            <el-table-column prop="day" label="第几天" width="80">
              <template #default="{ row }">第 {{ row.day }} 天</template>
            </el-table-column>
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="title" label="复习主题" min-width="180" />
            <el-table-column prop="estimated_minutes" label="预计时长" width="100">
              <template #default="{ row }">{{ row.estimated_minutes }} 分钟</template>
            </el-table-column>
            <el-table-column label="优先级" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="['', 'danger', 'warning', 'info'][row.priority]">
                  {{ ['', '高', '中', '低'][row.priority] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="具体内容" min-width="200" />
          </el-table>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header><b>自测题</b></template>
          <el-collapse>
            <el-collapse-item v-for="(q, i) in result.quiz" :key="i" :title="`${i + 1}. ${q.question}`">
              <div class="quiz-options">
                <div v-for="opt in q.options" :key="opt">{{ opt }}</div>
              </div>
              <el-divider />
              <div class="quiz-answer">
                <el-tag type="success" size="small">答案：{{ q.answer }}</el-tag>
                <span v-if="q.knowledge_point" class="kp">知识点：{{ q.knowledge_point }}</span>
              </div>
              <p v-if="q.analysis" class="quiz-analysis">{{ q.analysis }}</p>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </template>

      <!-- 分析中提示 -->
      <el-card v-if="step === 2 && analyzing" shadow="never" class="step-card">
        <el-result icon="info" title="AI 正在分析你的资料…" sub-title="通常需要几十秒，请稍候">
          <template #extra><el-progress :percentage="100" :indeterminate="true" :duration="2" /></template>
        </el-result>
      </el-card>

      <!-- 分析失败：给出原因与出口，不留空白页 -->
      <el-card v-if="step === 2 && analyzeError" shadow="never" class="step-card">
        <el-result icon="error" title="分析没有成功" :sub-title="analyzeError">
          <template #extra>
            <el-button v-if="analyzeError.includes('资料')" type="primary" @click="$router.push('/materials')">
              去上传资料
            </el-button>
            <el-button @click="backToProfile">返回上一步</el-button>
            <el-button type="primary" @click="onAnalyze">重试</el-button>
          </template>
        </el-result>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi, examApi } from '../api'

const FIELD_LABELS = {
  target: '备考目标',
  learning_status: '基础水平',
  available_days: '剩余天数',
  daily_hours: '每天可投入时间',
}

const exams = ref([])
const examId = ref(null)
const step = ref(0)
const rawText = ref('')
const profile = ref(null)
const result = ref(null)
const profileLoading = ref(false)
const analyzing = ref(false)
const analyzeError = ref('')

const completeForm = reactive({ target: 'pass', learning_status: 'weak', available_days: 5, daily_hours: 3 })

const missing = computed(() => profile.value?.missing_fields || [])
const missingFieldLabels = computed(() => missing.value.map((f) => FIELD_LABELS[f] || f))
const completeFormValid = computed(() =>
  missing.value.every((f) => {
    if (f === 'target') return ['pass', 'medium', 'high'].includes(completeForm.target)
    if (f === 'learning_status') return ['weak', 'medium', 'good'].includes(completeForm.learning_status)
    if (f === 'available_days') return completeForm.available_days > 0
    if (f === 'daily_hours') return completeForm.daily_hours > 0
    return true
  }),
)

const targetText = (t) => ({ pass: '保及格', medium: '稳中等', high: '冲高分' }[t])
const statusText = (s) => ({ weak: '基础薄弱', medium: '基础一般', good: '基础良好' }[s])
const weightColor = (w) => (w >= 0.8 ? '#e05d5d' : w >= 0.6 ? '#e6a23c' : '#3fa97a')

const buildSupplement = () => {
  const parts = []
  if (missing.value.includes('target')) parts.push(`我的目标是${targetText(completeForm.target)}`)
  if (missing.value.includes('learning_status')) parts.push(`我基础${statusText(completeForm.learning_status)}`)
  if (missing.value.includes('available_days')) parts.push(`还有${completeForm.available_days}天考试`)
  if (missing.value.includes('daily_hours')) parts.push(`每天能学${completeForm.daily_hours}小时`)
  return parts.join('，')
}

const onExtractProfile = async () => {
  profileLoading.value = true
  try {
    profile.value = await aiApi.profile({ exam_id: examId.value, raw_text: rawText.value })
    step.value = 1
    if (profile.value.is_complete) ElMessage.success('画像提取完成')
    else ElMessage.warning('画像缺少部分信息，请补全')
  } catch {
    /* 错误提示已由拦截器弹出，留在当前步骤 */
  } finally {
    profileLoading.value = false
  }
}

const onCompleteProfile = async () => {
  profileLoading.value = true
  try {
    profile.value = await aiApi.profile({
      exam_id: examId.value,
      raw_text: '',
      supplement: buildSupplement(),
    })
    if (profile.value.is_complete) ElMessage.success('画像已补全')
  } catch {
    /* 错误提示已由拦截器弹出，留在补全表单 */
  } finally {
    profileLoading.value = false
  }
}

const onAnalyze = async () => {
  analyzing.value = true
  analyzeError.value = ''
  step.value = 2
  try {
    const resp = await aiApi.analyze(examId.value)
    result.value = resp.result
    ElMessage.success('分析完成，复习计划已生成每日任务')
  } catch (e) {
    // 失败时展示原因和出口，避免页面空白
    analyzeError.value = e?.response?.data?.detail || e?.message || '网络异常，请稍后重试'
  } finally {
    analyzing.value = false
  }
}

const onBackToDescribe = () => {
  step.value = 0
  analyzeError.value = ''
}

const backToProfile = () => {
  analyzeError.value = ''
  step.value = 1
}

const onExamChange = async () => {
  step.value = 0
  analyzeError.value = ''
  rawText.value = ''
  profile.value = null
  result.value = null
  // 已有分析结果的科目直接展示
  try {
    const resp = await aiApi.latestAnalysis(examId.value)
    result.value = resp.result
    step.value = 2
  } catch {
    /* 没有历史分析，从第一步开始 */
  }
}

onMounted(async () => {
  exams.value = await examApi.list()
})
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-head h2 {
  color: var(--text-hi);
}
.steps {
  margin: 24px 0;
}
.step-card {
  max-width: 860px;
  margin: 0 auto;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}
.complete-alert {
  margin: 16px 0;
}
.complete-form {
  margin-top: 8px;
}
.unit {
  margin-left: 8px;
  color: var(--text-low);
}
.result-card {
  margin-bottom: 16px;
}
.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.result-head h3 {
  color: var(--text-hi);
}
.hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--text-low);
  font-weight: normal;
}
.focus-tag {
  margin-right: 8px;
}
.focus-basis {
  margin-top: 4px;
  color: var(--text-low);
  font-size: 13px;
}
.quiz-options {
  color: var(--text-mid);
  font-size: 14px;
  line-height: 2;
}
.quiz-answer {
  display: flex;
  align-items: center;
  gap: 12px;
}
.kp {
  color: var(--text-low);
  font-size: 13px;
}
.quiz-analysis {
  margin-top: 8px;
  color: var(--text-mid);
  font-size: 13px;
}
</style>
