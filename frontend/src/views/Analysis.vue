<template>
  <div>
    <div class="page-head">
      <div>
        <p class="analysis-kicker">从零散资料，到有据可循的复习</p>
        <h2>AI 复习分析</h2>
      </div>
      <el-select
        v-model="examId"
        :disabled="profileLoading || analyzing"
        aria-label="选择要分析的科目"
        placeholder="选择要分析的科目"
        class="subject-picker"
        @change="onExamChange"
      >
        <el-option
          v-for="e in exams"
          :key="e.id"
          :label="`${e.subject}（${e.exam_date}）`"
          :value="e.id"
        />
      </el-select>
    </div>

    <el-empty v-if="!examId" description="请先选择科目（在考试管理里录入考试）">
      <el-button type="primary" @click="$router.push('/exams')"
        >去录入考试</el-button
      >
    </el-empty>

    <template v-else>
      <el-steps
        :active="step"
        align-center
        finish-status="success"
        class="steps"
      >
        <el-step title="说说你的情况" description="目标与可用时间" />
        <el-step title="确认学习画像" description="核对并补全信息" />
        <el-step title="拿到复习方案" description="重点、计划与自测" />
      </el-steps>

      <!-- 第一步：自然语言描述 -->
      <el-card v-if="step === 0" shadow="never" class="step-card">
        <div class="brief-intro">
          <span class="brief-index">01</span>
          <div>
            <h3>这一次，你想复习到什么程度？</h3>
            <p>先选目标和学习节奏，也可以补充薄弱章节与特别要求。</p>
          </div>
        </div>
        <el-form label-position="top" class="brief-form">
          <el-form-item label="我的备考目标" class="brief-wide"
            ><el-radio-group v-model="brief.target" class="goal-choices"
              ><el-radio-button value="pass">保及格</el-radio-button
              ><el-radio-button value="medium">稳中等</el-radio-button
              ><el-radio-button value="high"
                >冲高分</el-radio-button
              ></el-radio-group
            >
            <p class="choice-hint">{{ goalHint }}</p></el-form-item
          >
          <el-form-item label="当前基础"
            ><el-select
              v-model="brief.learning_status"
              aria-label="当前学习基础"
              ><el-option
                label="基础薄弱，先补核心概念"
                value="weak" /><el-option
                label="基础一般，需要梳理重点"
                value="medium" /><el-option
                label="基础良好，想练综合难题"
                value="good" /></el-select
          ></el-form-item>
          <el-form-item label="距离考试还有"
            ><el-input-number
              v-model="brief.available_days"
              :min="1"
              :max="60"
              aria-label="可用复习天数"
            /><span class="unit">天</span></el-form-item
          >
          <el-form-item label="每天可用总时间（所有科目合计）"
            ><el-input-number
              v-model="brief.daily_hours"
              :min="0.5"
              :max="16"
              :step="0.5"
              aria-label="每日可用小时数"
            /><span class="unit">小时</span></el-form-item
          >
          <el-form-item label="薄弱章节（可选）"
            ><el-input
              v-model="brief.weak_chapters"
              placeholder="例如：极限、积分"
              maxlength="300"
          /></el-form-item>
        </el-form>
        <p class="choice-hint">
          各科保留各自的目标与基础，共享这份每日时间预算。生成后会统筹所有考试的未完成
          AI 任务，任务日期以首页与课程管理为准。
        </p>
        <label for="study-notes" class="notes-label">再补充一点（可选）</label>
        <el-input
          id="study-notes"
          v-model="rawText"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="例如：选择题经常失分，希望多安排基础题；晚上更方便学习。"
        />
        <div class="actions">
          <router-link to="/materials" class="material-link"
            >还没有资料？先去上传 ↗</router-link
          >
          <el-button
            type="primary"
            :loading="profileLoading"
            @click="onExtractProfile"
          >
            确认目标，生成学习画像 →
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
          <el-descriptions-item label="全科每日总预算">
            {{ brief.daily_hours }} 小时
          </el-descriptions-item>
          <el-descriptions-item label="薄弱章节" :span="2">
            {{
              profile.weak_chapters?.length
                ? profile.weak_chapters.join('、')
                : '（未提到）'
            }}
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
            <el-form-item
              v-if="missing.includes('learning_status')"
              label="基础水平"
            >
              <el-radio-group v-model="completeForm.learning_status">
                <el-radio-button value="weak">基础薄弱</el-radio-button>
                <el-radio-button value="medium">基础一般</el-radio-button>
                <el-radio-button value="good">基础良好</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item
              v-if="missing.includes('available_days')"
              label="剩余天数"
            >
              <el-input-number
                v-model="completeForm.available_days"
                :min="1"
                :max="60"
              />
              <span class="unit">天</span>
            </el-form-item>
            <el-form-item
              v-if="missing.includes('daily_hours')"
              label="每天可投入"
            >
              <el-input-number
                v-model="completeForm.daily_hours"
                :min="0.5"
                :max="16"
                :step="0.5"
              />
              <span class="unit">小时</span>
            </el-form-item>
          </el-form>
          <div class="actions">
            <el-button @click="onBackToDescribe">重新描述</el-button>
            <el-button
              type="primary"
              :loading="profileLoading"
              :disabled="!completeFormValid"
              @click="onCompleteProfile"
            >
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
        <el-card shadow="never" class="result-card result-overview">
          <div class="result-head">
            <h3>{{ result.course }} · 复习分析</h3>
            <el-button :loading="analyzing" @click="onAnalyze"
              >重新生成</el-button
            >
          </div>
          <el-alert type="info" :closable="false" :title="result.summary" />
          <div class="result-metrics">
            <div>
              <strong>{{ result.knowledge_points?.length || 0 }}</strong
              ><span>个知识点</span>
            </div>
            <div>
              <strong>{{ result.review_plan?.length || 0 }}</strong
              ><span>天复习安排</span>
            </div>
            <div>
              <strong>{{ result.quiz?.length || 0 }}</strong
              ><span>道自测题</span>
            </div>
            <router-link to="/#board"
              >去首页执行计划 <el-icon><Right /></el-icon
            ></router-link>
          </div>
          <p class="ai-reference">
            <el-icon><InfoFilled /></el-icon>AI
            生成内容仅供复习参考，请结合原始资料与课程要求核对。知识点权重表示复习优先级。
          </p>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header
            ><div class="knowledge-head">
              <div>
                <b>知识点优先级</b><span class="hint">先抓重点，再补薄弱</span>
              </div>
              <el-radio-group
                v-model="knowledgeView"
                size="small"
                aria-label="知识点展示方式"
                ><el-radio-button value="visual">重点视图</el-radio-button
                ><el-radio-button value="table"
                  >详细表格</el-radio-button
                ></el-radio-group
              >
            </div></template
          >
          <div v-if="knowledgeView === 'visual'" class="knowledge-list">
            <article v-for="(kp, i) in sortedKnowledge" :key="kp.name">
              <span class="knowledge-order">{{
                String(i + 1).padStart(2, '0')
              }}</span>
              <div class="knowledge-body">
                <div class="knowledge-title">
                  <b>{{ kp.name }}</b
                  ><span>{{
                    { high: '优先攻克', medium: '重点巩固', low: '有余力再看' }[
                      kp.importance
                    ] || '按计划复习'
                  }}</span>
                </div>
                <div class="weight-track">
                  <i
                    :style="{
                      width:
                        Math.round(Math.min(1, Math.max(0, kp.weight)) * 100) +
                        '%',
                    }"
                  ></i>
                </div>
                <p>{{ kp.recommend_reason }}</p>
                <div class="knowledge-source">
                  <span v-if="kp.source">依据 · {{ kp.source }}</span
                  ><span v-if="kp.suggest_hours"
                    >建议 {{ kp.suggest_hours }} 小时</span
                  >
                </div>
              </div>
              <strong class="knowledge-weight"
                >{{ Math.round(kp.weight * 100) }}<small>%</small></strong
              >
            </article>
          </div>
          <el-table v-else :data="result.knowledge_points" size="large">
            <el-table-column prop="name" label="知识点" min-width="140">
              <template #default="{ row }"
                ><b>{{ row.name }}</b></template
              >
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
                <el-tag
                  :type="
                    { high: 'danger', medium: 'warning', low: 'info' }[
                      row.importance
                    ]
                  "
                >
                  {{ { high: '高', medium: '中', low: '低' }[row.importance] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="suggest_hours" label="建议投入" width="90">
              <template #default="{ row }"
                >{{ row.suggest_hours }} 小时</template
              >
            </el-table-column>
            <el-table-column
              prop="recommend_reason"
              label="推荐理由"
              min-width="160"
            />
            <el-table-column prop="source" label="依据来源" width="100">
              <template #default="{ row }">
                <el-tag
                  v-if="row.source"
                  size="small"
                  type="success"
                  effect="plain"
                  >{{ row.source }}</el-tag
                >
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
              <el-tag
                size="small"
                :type="f.level === 'must' ? 'danger' : 'primary'"
                class="focus-tag"
              >
                {{ f.level === 'must' ? '必考' : '常考' }}
              </el-tag>
              {{ f.content }}
              <div class="focus-basis">
                依据：{{ f.basis }}（{{ f.source }}）
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header
            ><b>复习计划</b
            ><span class="hint">{{
              USE_MOCK
                ? '以下为示例计划，演示操作不保存'
                : '本科内容建议；全科统筹后的实际日期见首页与课程管理'
            }}</span></template
          >
          <el-alert
            v-if="schedulingNote"
            :title="schedulingNote"
            type="warning"
            :closable="false"
            show-icon
          />
          <el-table :data="result.review_plan">
            <el-table-column prop="day" label="第几天" width="80">
              <template #default="{ row }">第 {{ row.day }} 天</template>
            </el-table-column>
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="title" label="复习主题" min-width="180" />
            <el-table-column
              prop="estimated_minutes"
              label="预计时长"
              width="100"
            >
              <template #default="{ row }"
                >{{ row.estimated_minutes }} 分钟</template
              >
            </el-table-column>
            <el-table-column label="优先级" width="90">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="['', 'danger', 'warning', 'info'][row.priority]"
                >
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
            <el-collapse-item
              v-for="(q, i) in result.quiz"
              :key="i"
              :title="`${i + 1}. ${q.question}`"
            >
              <div class="quiz-options">
                <div v-for="opt in q.options" :key="opt">{{ opt }}</div>
              </div>
              <el-divider />
              <div class="quiz-answer">
                <el-tag type="success" size="small"
                  >答案：{{ q.answer }}</el-tag
                >
                <span v-if="q.knowledge_point" class="kp"
                  >知识点：{{ q.knowledge_point }}</span
                >
              </div>
              <p v-if="q.analysis" class="quiz-analysis">{{ q.analysis }}</p>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </template>

      <!-- 分析中提示 -->
      <el-card v-if="step === 2 && analyzing" shadow="never" class="step-card">
        <el-result
          icon="info"
          title="AI 正在分析你的资料…"
          sub-title="通常需要几十秒，请稍候"
        >
          <template #extra
            ><el-progress :percentage="100" :indeterminate="true" :duration="2"
          /></template>
        </el-result>
      </el-card>

      <!-- 分析失败：给出原因与出口，不留空白页 -->
      <el-card
        v-if="step === 2 && analyzeError"
        shadow="never"
        class="step-card"
      >
        <el-result icon="error" title="分析没有成功" :sub-title="analyzeError">
          <template #extra>
            <el-button
              v-if="analyzeError.includes('资料')"
              type="primary"
              @click="$router.push('/materials')"
            >
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
import { useRoute } from 'vue-router'
import { aiApi, examApi, studyApi } from '../api'
import { USE_MOCK, getToday, mockStudySession } from '../mock/dashboard'
import { buildStudyPlan, applyStudyPlan } from '../utils/studyPlan'
import { daysUntil } from '../utils/studyProgress'
import { mockExams, mockProfile, mockAnalysis } from '../mock/pages'

const FIELD_LABELS = {
  target: '备考目标',
  learning_status: '基础水平',
  available_days: '剩余天数',
  daily_hours: '每天可投入时间',
}

const exams = ref([])
const route = useRoute()
const knowledgeView = ref('visual')
const brief = reactive({
  target: 'pass',
  learning_status: 'weak',
  available_days: 5,
  daily_hours: 3,
  weak_chapters: '',
})
const goalHint = computed(
  () =>
    ({
      pass: '优先高频基础题、必考概念和短期提分内容。',
      medium: '覆盖核心考点，巩固常考题型，兼顾薄弱章节。',
      high: '在核心考点之外，增加综合题、难题与易失分点。',
    })[brief.target],
)
const sortedKnowledge = computed(() =>
  [...(result.value?.knowledge_points || [])].sort(
    (a, b) => b.weight - a.weight,
  ),
)
const examId = ref(null)
const step = ref(0)
const rawText = ref('')
const profile = ref(null)
const result = ref(null)
const profileLoading = ref(false)
const analyzing = ref(false)
const analyzeError = ref('')
const schedulingNote = ref('')

const completeForm = reactive({
  target: 'pass',
  learning_status: 'weak',
  available_days: 5,
  daily_hours: 3,
})

const missing = computed(() => profile.value?.missing_fields || [])
const missingFieldLabels = computed(() =>
  missing.value.map((f) => FIELD_LABELS[f] || f),
)
const completeFormValid = computed(() =>
  missing.value.every((f) => {
    if (f === 'target')
      return ['pass', 'medium', 'high'].includes(completeForm.target)
    if (f === 'learning_status')
      return ['weak', 'medium', 'good'].includes(completeForm.learning_status)
    if (f === 'available_days') return completeForm.available_days > 0
    if (f === 'daily_hours') return completeForm.daily_hours > 0
    return true
  }),
)

const targetText = (t) =>
  ({ pass: '保及格', medium: '稳中等', high: '冲高分' })[t]
const statusText = (s) =>
  ({ weak: '基础薄弱', medium: '基础一般', good: '基础良好' })[s]
const weightColor = (w) =>
  w >= 0.8 ? '#c2472f' : w >= 0.6 ? '#a06a22' : '#35554c'

const buildSupplement = () => {
  const parts = []
  if (missing.value.includes('target'))
    parts.push(`我的目标是${targetText(completeForm.target)}`)
  if (missing.value.includes('learning_status'))
    parts.push(`我基础${statusText(completeForm.learning_status)}`)
  if (missing.value.includes('available_days'))
    parts.push(`还有${completeForm.available_days}天考试`)
  if (missing.value.includes('daily_hours'))
    parts.push(`每天能学${completeForm.daily_hours}小时`)
  return parts.join('，')
}

const onExtractProfile = async () => {
  profileLoading.value = true
  try {
    if (USE_MOCK) {
      mockStudySession.daily_minutes = Math.round(brief.daily_hours * 60)
      mockStudySession.focus.goal_minutes = mockStudySession.daily_minutes
      // mock 模式下返回本地演示画像
      await new Promise((r) => setTimeout(r, 600))
      profile.value = {
        ...structuredClone(mockProfile),
        target: brief.target,
        learning_status: brief.learning_status,
        available_days: brief.available_days,
        daily_hours: brief.daily_hours,
        weak_chapters: brief.weak_chapters
          .split(/[、，,]/)
          .map((s) => s.trim())
          .filter(Boolean),
      }
    } else {
      await studyApi.saveSettings({
        daily_minutes: Math.round(brief.daily_hours * 60),
      })
      const basis = {
        weak: '我基础差',
        medium: '我的基础一般',
        good: '我的基础很好',
      }[brief.learning_status]
      const description = `我的目标是${targetText(brief.target)}，${basis}，还有${brief.available_days}天考试，每天能学${brief.daily_hours}小时。${brief.weak_chapters.trim() ? '薄弱的是' + brief.weak_chapters + '。' : ''}${rawText.value}`
      profile.value = await aiApi.profile({
        exam_id: examId.value,
        raw_text: description,
      })
    }
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

const previewAnalysis = () => {
  const subject =
    exams.value.find((e) => e.id === examId.value)?.subject || '当前科目'
  const names = subject.includes('英语')
    ? ['核心词汇', '长难句与语法', '阅读理解', '听力与精听', '写作与翻译']
    : subject.includes('数据')
      ? ['线性表', '树与二叉树', '图的遍历', '查找与排序', '算法复杂度']
      : subject.includes('数学')
        ? mockAnalysis.knowledge_points.map((p) => p.name)
        : ['核心概念', '重点原理', '典型题型', '综合练习', '错题复盘']
  const copy = structuredClone(mockAnalysis)
  copy.course = subject
  copy.summary = `${subject}的示例复习方案。全科每日共享 ${brief.daily_hours} 小时，实际日期与各科分配统一在首页确认；以下考点权重用于演示。`
  copy.knowledge_points = copy.knowledge_points.map((p, i) => ({
    ...p,
    name: names[i],
    source: '示例资料',
    recommend_reason: '演示建议：结合本课程资料与当前基础安排优先级',
  }))
  copy.exam_focus = copy.exam_focus.map((p, i) => ({
    ...p,
    content: `${names[i]}的基础题与常见考法`,
    basis: '演示内容，请以实际课程要求为准',
    source: '示例资料',
  }))
  copy.review_plan = copy.review_plan.map((p, i) => ({
    ...p,
    title: names[i],
    detail: `复习${names[i]}并整理练习中的易错点`,
    estimated_minutes: Math.max(
      15,
      Math.round(
        (brief.daily_hours * 60) / Math.max(1, exams.value.length) / 5,
      ) * 5,
    ),
  }))
  if (subject.includes('英语'))
    copy.quiz = [
      {
        question: '请选择正确的词形：She ___ to the library every day.',
        options: ['go', 'goes', 'going', 'gone'],
        answer: 'B',
        analysis: '一般现在时的主语为第三人称单数，动词用 goes。',
        knowledge_point: '长难句与语法',
      },
    ]
  else if (subject.includes('数据'))
    copy.quiz = [
      {
        question: '采用先进先出规则的数据结构是？',
        options: ['栈', '队列', '二叉搜索树', '堆'],
        answer: 'B',
        analysis: '队列遵循先进先出，栈遵循后进先出。',
        knowledge_point: '线性表',
      },
    ]
  else if (!subject.includes('数学'))
    copy.quiz = [
      {
        question: '复习后发现某类题反复出错，下一步更合适的做法是？',
        options: [
          '跳过这个知识点',
          '整理错因并补充针对性练习',
          '只增加背诵时间',
          '等到考前再看',
        ],
        answer: 'B',
        analysis: '先识别错因，再通过针对性练习检查是否掌握。',
        knowledge_point: '错题复盘',
      },
    ]
  return copy
}

const onAnalyze = async () => {
  analyzing.value = true
  analyzeError.value = ''
  schedulingNote.value = ''
  result.value = null
  step.value = 2
  try {
    if (USE_MOCK) {
      // mock 模式下返回本地演示分析结果（模拟分析耗时）
      await new Promise((r) => setTimeout(r, 1500))
      result.value = previewAnalysis()
      const retained = mockStudySession.tasks.filter(
        (t) => t.exam_id !== examId.value || t.is_done || t.source !== 'ai',
      )
      const completed = new Map()
      retained
        .filter(
          (t) => t.exam_id === examId.value && t.is_done && t.source === 'ai',
        )
        .forEach((t) => {
          const name = t.title.replace(/（分段 \d+\/\d+）$/, '')
          completed.set(name, (completed.get(name) || 0) + t.estimated_minutes)
        })
      let nextId = Math.max(0, ...mockStudySession.tasks.map((t) => t.id)) + 1
      const generated = result.value.review_plan
        .map((p) => ({
          id: nextId++,
          exam_id: examId.value,
          exam: result.value.course,
          title: `${result.value.course} · ${p.title}`,
          plan_date: p.date,
          estimated_minutes: p.estimated_minutes,
          priority: p.priority,
          is_done: false,
          done_at: null,
          source: 'ai',
        }))
        .map((t) => ({
          ...t,
          estimated_minutes: Math.max(
            0,
            t.estimated_minutes - (completed.get(t.title) || 0),
          ),
        }))
        .filter((t) => t.estimated_minutes > 0)
      const candidate = [...retained, ...generated]
      const plan = buildStudyPlan(
        candidate,
        mockStudySession.exams,
        mockStudySession.daily_minutes,
        getToday(),
      )
      if (plan.conflicts.length)
        schedulingNote.value =
          '示例分析已完成，但全科容量不足，新任务未覆盖原计划。请先调整时间或任务。'
      else mockStudySession.tasks = applyStudyPlan(candidate, plan)
    } else {
      const resp = await aiApi.analyze(examId.value)
      result.value = resp.result
      if (resp.scheduling && !resp.scheduling.applied)
        schedulingNote.value =
          '分析已完成，但新任务无法在全科预算内排完，因此没有写入或覆盖现有任务。请调整预算、复习范围或目标后重新生成。'
    }
    if (schedulingNote.value) ElMessage.warning(schedulingNote.value)
    else
      ElMessage.success(
        USE_MOCK
          ? '示例分析与全科计划已更新，本次演示内有效'
          : '分析完成，复习计划已生成每日任务',
      )
  } catch (e) {
    // 失败时展示原因和出口，避免页面空白
    analyzeError.value =
      e?.response?.data?.detail || e?.message || '网络异常，请稍后重试'
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
  const selected = exams.value.find((e) => e.id === examId.value)
  brief.available_days = Math.max(
    1,
    Math.min(60, selected ? daysUntil(selected.exam_date, getToday()) : 5),
  )
  if (USE_MOCK) return // 预览模式下每次都从第一步开始演示
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
  if (USE_MOCK) {
    exams.value = structuredClone(mockStudySession.exams)
    brief.daily_hours = mockStudySession.daily_minutes / 60
  } else {
    exams.value = await examApi.list()
    brief.daily_hours = (await studyApi.settings()).daily_minutes / 60
  }
  const requested = Number(route.query.exam)
  if (exams.value.some((e) => e.id === requested)) {
    examId.value = requested
    await onExamChange()
  }
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
  margin: 0;
  font-size: 28px;
}
.analysis-kicker {
  margin: 0 0 10px;
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.06em;
}
.subject-picker {
  width: 260px;
}
.brief-intro {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  margin: 8px 0 28px;
}
.brief-index {
  font: 500 36px/1 var(--font-num);
  color: var(--coral-deep);
}
.brief-intro h3 {
  font-size: 19px;
  margin: 0 0 10px;
}
.brief-intro p {
  font-size: 12px;
  line-height: 1.8;
  color: var(--ink-3);
  margin: 0;
}
.brief-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.brief-wide {
  grid-column: 1 / -1;
}
.goal-choices {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
}
.goal-choices :deep(.el-radio-button__inner) {
  width: 100%;
  padding-block: 14px;
  font-weight: 700;
}
.choice-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--ink-3);
  line-height: 1.8;
}
.notes-label {
  display: block;
  font-size: 13px;
  margin: 5px 0 12px;
  color: var(--ink-2);
}
.material-link {
  align-self: center;
  margin-right: auto;
  color: var(--ink-3);
  font-size: 12px;
  text-decoration: none;
}
.result-overview {
  border-color: var(--ink-1);
}
.result-head h3 {
  font-size: 23px;
  margin: 6px 0 20px;
}
.result-metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 30px;
  margin-top: 24px;
}
.result-metrics > div {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.result-metrics strong {
  font: 500 32px var(--font-num);
}
.result-metrics span {
  font-size: 12px;
  color: var(--ink-3);
}
.result-metrics a {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
  color: var(--coral-deep);
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}
.ai-reference {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: var(--ink-3);
  font-size: 11px;
  line-height: 1.8;
  margin: 22px 0 0;
  padding-top: 15px;
  border-top: 1px solid var(--line);
}
.ai-reference .el-icon {
  flex-shrink: 0;
  margin-top: 4px;
}
.knowledge-head {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
  align-items: center;
  justify-content: space-between;
}
.knowledge-list article {
  display: flex;
  gap: 24px;
  padding: 24px 0;
  border-bottom: 1px solid var(--line);
}
.knowledge-list article:first-child {
  padding-top: 5px;
}
.knowledge-list article:last-child {
  border: 0;
  padding-bottom: 5px;
}
.knowledge-order {
  font: 500 17px var(--font-num);
  color: var(--ink-3);
}
.knowledge-body {
  flex: 1;
  min-width: 0;
}
.knowledge-title {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.knowledge-title b {
  font-size: 15px;
}
.knowledge-title span {
  color: var(--coral-deep);
  font-size: 11px;
  background: var(--coral-soft);
  padding: 3px 6px;
  border-radius: 3px;
}
.weight-track {
  height: 6px;
  background: var(--bg-soft);
  border-radius: 3px;
  overflow: hidden;
  margin: 15px 0 10px;
}
.weight-track i {
  display: block;
  height: 100%;
  background: var(--coral);
  border-radius: 3px;
}
.knowledge-body p {
  color: var(--ink-2);
  font-size: 12px;
  line-height: 1.9;
  margin: 0;
}
.knowledge-source {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 10px;
  color: var(--ink-3);
  font-size: 11px;
}
.knowledge-weight {
  font: 500 30px var(--font-num);
}
.knowledge-weight small {
  font-size: 12px;
  margin-left: 3px;
}
@media (max-width: 680px) {
  .subject-picker {
    width: 100%;
  }
  .brief-form {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .brief-wide {
    grid-column: auto;
  }
  .brief-intro {
    gap: 12px;
  }
  .brief-intro h3 {
    font-size: 16px;
  }
  .brief-index {
    font-size: 28px;
  }
  .steps :deep(.el-step__description) {
    display: none;
  }
  .steps :deep(.el-step__title) {
    font-size: 12px;
  }
  .actions {
    flex-wrap: wrap;
    gap: 12px;
  }
  .material-link {
    width: 100%;
  }
  .result-head {
    flex-wrap: wrap;
    gap: 12px;
  }
  .result-head h3 {
    font-size: 19px;
  }
  .result-metrics {
    gap: 16px;
  }
  .result-metrics strong {
    font-size: 26px;
  }
  .result-metrics span {
    font-size: 10px;
  }
  .result-metrics a {
    width: 100%;
    margin-left: 0;
  }
  .knowledge-list article {
    gap: 12px;
    padding: 20px 0;
  }
  .knowledge-order {
    font-size: 13px;
  }
  .knowledge-title b {
    font-size: 13px;
  }
  .knowledge-title span {
    font-size: 10px;
  }
  .knowledge-weight {
    font-size: 24px;
  }
  .knowledge-source {
    font-size: 10px;
  }
  .hint {
    display: block;
    margin: 6px 0 0 !important;
  }
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
