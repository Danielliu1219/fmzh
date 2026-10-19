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

        <!-- 思维导图与记忆卡片（用例 4.4） -->
        <el-card v-if="study" shadow="never" class="result-card">
          <template #header>
            <b>思维导图与记忆卡片</b>
            <span class="hint">提纲可视化 · 点击卡片翻面背诵</span>
          </template>
          <div ref="mindmapRef" class="mindmap-chart"></div>
          <el-divider />
          <div v-if="cards.length" class="flash-area">
            <div
              class="flash-card"
              :class="{ flipped: cardFlipped }"
              @click="cardFlipped = !cardFlipped"
            >
              <div class="flash-inner">
                <div class="flash-face flash-front">
                  <span class="flash-label">正面 · 背诵要点</span>
                  <p class="flash-text">{{ currentCard?.front }}</p>
                  <span class="flash-hint">{{ currentCard?.hint }}</span>
                </div>
                <div class="flash-face flash-back">
                  <span class="flash-label">背面 · 资料依据</span>
                  <p class="flash-text">{{ currentCard?.back }}</p>
                </div>
              </div>
            </div>
            <div class="flash-controls">
              <el-button size="small" @click="prevCard">上一张</el-button>
              <span class="flash-count">{{ cardIndex + 1 }} / {{ cards.length }}</span>
              <el-button size="small" @click="nextCard">下一张</el-button>
              <el-button size="small" @click="shuffleCards">打乱顺序</el-button>
              <el-button link type="primary" @click="cardFlipped = !cardFlipped">
                翻面
              </el-button>
            </div>
          </div>
          <el-empty v-else description="暂无可背诵的卡片" :image-size="60" />
        </el-card>

        <!-- 资料问答（用例 4.5） -->
        <el-card shadow="never" class="result-card">
          <template #header>
            <b>资料问答</b>
            <span class="hint">就当前科目的复习资料提问，支持多轮追问与历史保存</span>
          </template>
          <div ref="qaListRef" class="qa-list">
            <el-empty
              v-if="!qaMessages.length"
              description="试着问：这份资料的重点是什么？"
              :image-size="60"
            />
            <div v-for="m in qaMessages" :key="m.id" class="qa-row" :class="m.role">
              <div class="qa-bubble">
                <div class="qa-role">{{ m.role === 'user' ? '我' : 'AI 助手' }}</div>
                <div class="qa-content">{{ m.content }}</div>
              </div>
            </div>
          </div>
          <div class="qa-input-row">
            <div class="qa-input-box">
              <el-input
                v-model="qaInput"
                type="textarea"
                :rows="2"
                maxlength="2000"
                show-word-limit
                placeholder="针对资料提问，例如：极限这一章有哪些必考内容？"
                @keydown.enter.exact.prevent="onAsk"
              />
            </div>
            <el-button
              type="primary"
              :loading="qaLoading"
              :disabled="!qaInput.trim()"
              @click="onAsk"
            >
              发送
            </el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header>
            <b>常考题型与高频考点</b>
            <span class="hint">基于历年题与多来源资料统计</span>
          </template>
          <div v-if="result.question_types?.length" class="type-block">
            <div ref="typeChartRef" class="type-chart"></div>
            <el-table :data="result.question_types" size="small" class="type-table">
              <el-table-column prop="type" label="题型" width="100" />
              <el-table-column prop="count" label="出现次数" width="90" />
              <el-table-column label="占比" width="90">
                <template #default="{ row }">{{ Math.round(row.frequency * 100) }}%</template>
              </el-table-column>
              <el-table-column prop="basis" label="统计依据" min-width="180" />
              <el-table-column prop="source" label="来源" width="100" />
            </el-table>
          </div>
          <el-divider v-if="result.question_types?.length" />
          <el-timeline>
            <el-timeline-item
              v-for="(f, i) in sortedFocus"
              :key="i"
              :type="f.level === 'must' ? 'danger' : 'primary'"
              :hollow="f.level !== 'must'"
            >
              <el-tag size="small" :type="f.level === 'must' ? 'danger' : 'primary'" class="focus-tag">
                {{ f.level === 'must' ? '必考' : '常考' }}
              </el-tag>
              <el-tag v-if="f.frequency" size="small" type="info" effect="plain" class="focus-tag">
                出现 {{ f.frequency }} 次
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

        <!-- 动态调整计划与权重（用例 4.12） -->
        <el-card shadow="never" class="result-card">
          <template #header>
            <b>动态调整计划与权重</b>
            <span class="hint">根据打卡、自测错题与剩余天数重新排序</span>
          </template>
          <div class="replan-actions">
            <el-button type="primary" plain :loading="replanLoading" @click="onReplanPreview">
              预览调整
            </el-button>
            <span class="replan-tip">
              已完成的打卡记录会保留；应用后仅重建未完成的 AI 任务。
            </span>
          </div>
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

      <!-- 动态调整预览 -->
      <el-dialog v-model="replanVisible" title="动态调整预览" width="760px">
        <el-alert
          v-if="replanPreview"
          :title="replanPreview.note"
          type="info"
          :closable="false"
          class="replan-note"
        />
        <h4 class="replan-title">知识点权重调整</h4>
        <el-table :data="replanPreview?.weights || []" size="small" max-height="260">
          <el-table-column prop="name" label="知识点" min-width="140" />
          <el-table-column label="权重变化" width="150">
            <template #default="{ row }">
              <span
                :class="{
                  'weight-up': row.new_weight > row.old_weight,
                  'weight-down': row.new_weight < row.old_weight,
                }"
              >
                {{ Math.round(row.old_weight * 100) }}% → {{ Math.round(row.new_weight * 100) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="调整依据" min-width="240" />
        </el-table>
        <el-divider />
        <h4 class="replan-title">调整后的复习计划</h4>
        <el-table :data="replanPreview?.plan || []" size="small" max-height="240">
          <el-table-column prop="day" label="第几天" width="80">
            <template #default="{ row }">第 {{ row.day }} 天</template>
          </el-table-column>
          <el-table-column prop="date" label="日期" width="110" />
          <el-table-column prop="title" label="任务" min-width="180" />
          <el-table-column prop="estimated_minutes" label="时长" width="90">
            <template #default="{ row }">{{ row.estimated_minutes }} 分钟</template>
          </el-table-column>
        </el-table>
        <template #footer>
          <el-button @click="replanVisible = false">取消</el-button>
          <el-button type="primary" :loading="replanApplying" @click="onReplanApply">
            应用调整
          </el-button>
        </template>
      </el-dialog>

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
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { aiApi, examApi } from '../api'
import { USE_MOCK } from '../mock/dashboard'
import { mockExams, mockProfile, mockAnalysis } from '../mock/pages'

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

// 思维导图与记忆卡片（用例 4.4）
const study = ref(null)
const cardIndex = ref(0)
const cardFlipped = ref(false)
const mindmapRef = ref(null)
let mindmapChart = null
const cards = computed(() => study.value?.cards || [])
const currentCard = computed(() => cards.value[cardIndex.value] || null)

// 常考题型与高频考点（用例 4.7）
const typeChartRef = ref(null)
let typeChart = null
const sortedFocus = computed(() =>
  [...(result.value?.exam_focus || [])].sort(
    (a, b) => (b.frequency || 0) - (a.frequency || 0),
  ),
)

// 资料问答（用例 4.5）
const qaConversationId = ref(null)
const qaMessages = ref([])
const qaInput = ref('')
const qaLoading = ref(false)
const qaListRef = ref(null)

// 动态调整计划与权重（用例 4.12）
const replanVisible = ref(false)
const replanLoading = ref(false)
const replanApplying = ref(false)
const replanPreview = ref(null)

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
    if (USE_MOCK) {
      // mock 模式下返回本地演示画像
      await new Promise((r) => setTimeout(r, 600))
      profile.value = structuredClone(mockProfile)
    } else {
      profile.value = await aiApi.profile({ exam_id: examId.value, raw_text: rawText.value })
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

// 静态演示模式：从 mockAnalysis 直接构建导图与卡片
const buildMockStudy = () => {
  const course = mockAnalysis.course
  const kpNodes = mockAnalysis.knowledge_points.map((kp) => ({
    name: `${kp.name}（${Math.round(kp.weight * 100)}%）`,
    value: kp.weight,
    level: kp.importance,
    source: kp.source,
    children: [
      { name: `依据：${kp.recommend_reason}` },
      { name: `建议投入：${kp.suggest_hours} 小时` },
    ],
  }))
  const focusNodes = mockAnalysis.exam_focus.map((f) => ({
    name: `${f.level === 'must' ? '必考' : '常考'}：${f.content}`,
    level: f.level,
    source: f.source,
    children: [{ name: `依据：${f.basis}` }],
  }))
  return {
    exam_id: examId.value,
    course,
    mindmap: {
      name: course,
      children: [
        { name: '知识点', children: kpNodes },
        { name: '考点', children: focusNodes },
      ],
    },
    cards: [
      ...mockAnalysis.knowledge_points.map((kp, i) => ({
        id: i + 1,
        front: kp.name,
        back: kp.recommend_reason,
        hint: `依据来源：${kp.source} · 建议投入 ${kp.suggest_hours} 小时`,
        knowledge_point: kp.name,
        source: kp.source,
      })),
      ...mockAnalysis.exam_focus.map((f, i) => ({
        id: 100 + i,
        front: f.content,
        back: f.basis,
        hint: `来源：${f.source} · ${f.level === 'must' ? '必考' : '常考'}`,
        knowledge_point: '',
        source: f.source,
      })),
    ],
  }
}

const renderMindmap = async () => {
  await nextTick()
  if (!mindmapRef.value || !study.value) return
  if (!mindmapChart) mindmapChart = echarts.init(mindmapRef.value)
  mindmapChart.setOption(
    {
      tooltip: { trigger: 'item', triggerOn: 'mousemove' },
      series: [
        {
          type: 'tree',
          orient: 'LR',
          data: [study.value.mindmap],
          top: '3%',
          left: '8%',
          bottom: '3%',
          right: '18%',
          symbol: 'circle',
          symbolSize: 9,
          initialTreeDepth: 3,
          expandAndCollapse: true,
          label: {
            position: 'left',
            verticalAlign: 'middle',
            align: 'right',
            fontSize: 12,
            color: '#0c1614',
            width: 200,
            overflow: 'break',
          },
          leaves: {
            label: { position: 'right', align: 'left', width: 220, overflow: 'break' },
          },
          lineStyle: { color: '#d9d4c3', width: 1.2, curveness: 0.5 },
          itemStyle: { color: '#e66348', borderColor: '#e66348' },
          emphasis: { focus: 'descendant' },
          animationDuration: 400,
        },
      ],
    },
    true,
  )
  mindmapChart.resize()
}

const loadStudy = async () => {
  // 重建图表，避免 v-if 切换后复用已脱离 DOM 的旧实例
  if (mindmapChart) {
    mindmapChart.dispose()
    mindmapChart = null
  }
  if (!examId.value) {
    study.value = null
    return
  }
  if (USE_MOCK) {
    study.value = buildMockStudy()
  } else {
    try {
      study.value = await aiApi.mindmap(examId.value)
    } catch {
      study.value = null // 没有分析结果或接口失败时不展示该卡片
    }
  }
  cardIndex.value = 0
  cardFlipped.value = false
  await renderMindmap()
}

const prevCard = () => {
  if (!cards.value.length) return
  cardIndex.value = (cardIndex.value - 1 + cards.value.length) % cards.value.length
  cardFlipped.value = false
}

const nextCard = () => {
  if (!cards.value.length) return
  cardIndex.value = (cardIndex.value + 1) % cards.value.length
  cardFlipped.value = false
}

const shuffleCards = () => {
  if (!study.value?.cards?.length) return
  const shuffled = [...study.value.cards]
  for (let i = shuffled.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  study.value.cards = shuffled
  cardIndex.value = 0
  cardFlipped.value = false
}

const renderTypeChart = async () => {
  if (typeChart) {
    typeChart.dispose()
    typeChart = null
  }
  await nextTick()
  const types = result.value?.question_types || []
  if (!typeChartRef.value || !types.length) return
  typeChart = echarts.init(typeChartRef.value)
  typeChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => `${params[0].name}<br/>占比 ${params[0].value}%`,
    },
    grid: { left: 48, right: 20, top: 30, bottom: 36 },
    xAxis: {
      type: 'category',
      data: types.map((item) => item.type),
      axisLabel: { color: '#454e48' },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { formatter: '{value}%', color: '#8b9084' },
      splitLine: { lineStyle: { color: '#e9e5d7' } },
    },
    series: [
      {
        type: 'bar',
        data: types.map((item) => Math.round(item.frequency * 100)),
        barWidth: '46%',
        itemStyle: { color: '#e66348', borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c}%', color: '#0c1614' },
      },
    ],
  })
  typeChart.resize()
}

const resizeMindmap = () => {
  mindmapChart?.resize()
  typeChart?.resize()
}

// 静态演示模式的本地问答：优先匹配知识点/考点
const mockQaAnswer = (question) => {
  const kp = mockAnalysis.knowledge_points.find((item) => question.includes(item.name))
  if (kp) {
    return (
      `（Mock）「${kp.name}」权重 ${Math.round(kp.weight * 100)}%，` +
      `推荐依据：${kp.recommend_reason}（${kp.source}），建议投入 ${kp.suggest_hours} 小时。`
    )
  }
  const focus = mockAnalysis.exam_focus.find((item) => question.includes(item.content.slice(0, 4)))
  if (focus) {
    return `（Mock）${focus.content}：${focus.basis}（${focus.source}）。`
  }
  const top = mockAnalysis.knowledge_points.slice(0, 3).map((item) => item.name).join('、')
  return `（Mock）根据当前资料，建议优先复习：${top}。以上内容仅供复习参考，请结合教材与老师要求判断。`
}

const scrollQaToBottom = async () => {
  await nextTick()
  if (qaListRef.value) qaListRef.value.scrollTop = qaListRef.value.scrollHeight
}

const loadQa = async () => {
  qaConversationId.value = null
  qaMessages.value = []
  if (!examId.value || USE_MOCK) return
  try {
    const conversations = await aiApi.qaConversations(examId.value)
    if (!conversations.length) return
    const detail = await aiApi.qaConversation(conversations[0].id)
    qaConversationId.value = detail.id
    qaMessages.value = detail.messages || []
    await scrollQaToBottom()
  } catch {
    /* 没有历史会话时保持空状态 */
  }
}

const onAsk = async () => {
  const content = qaInput.value.trim()
  if (!content || qaLoading.value) return
  qaLoading.value = true
  qaInput.value = ''
  const optimistic = {
    id: `tmp-${Date.now()}`,
    role: 'user',
    content,
    created_at: new Date().toISOString(),
  }
  qaMessages.value = [...qaMessages.value, optimistic]
  await scrollQaToBottom()
  try {
    if (USE_MOCK) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      qaMessages.value = [
        ...qaMessages.value,
        {
          id: `tmp-a-${Date.now()}`,
          role: 'assistant',
          content: mockQaAnswer(content),
          created_at: new Date().toISOString(),
        },
      ]
    } else {
      if (!qaConversationId.value) {
        const conversation = await aiApi.createQaConversation(examId.value)
        qaConversationId.value = conversation.id
      }
      const conversation = await aiApi.askQa(qaConversationId.value, content)
      qaConversationId.value = conversation.id
      qaMessages.value = conversation.messages || []
    }
  } catch (e) {
    // 失败时撤回乐观展示的提问
    qaMessages.value = qaMessages.value.filter((item) => item.id !== optimistic.id)
    ElMessage.error(e?.response?.data?.detail || '提问失败，请稍后重试')
  } finally {
    qaLoading.value = false
    await scrollQaToBottom()
  }
}

// 静态演示模式：构造一份调整预览
const buildMockReplan = () => {
  const weights = mockAnalysis.knowledge_points
    .map((kp, index) => {
      const wrong = index === 0 ? 2 : index === 2 ? 1 : 0
      let next = kp.weight
      const reasons = []
      if (wrong) {
        const boost = Math.min(0.3, 0.08 * wrong)
        next += boost
        reasons.push(`错题 ${wrong} 道，权重 +${boost.toFixed(2)}`)
      }
      if (kp.weight < 0.6) {
        next -= 0.08
        reasons.push('剩余 5 天，低权重后置')
      }
      next = Math.min(1, Math.max(0.05, Math.round(next * 100) / 100))
      return {
        name: kp.name,
        old_weight: kp.weight,
        new_weight: next,
        reason: reasons.join('；') || '保持原权重',
      }
    })
    .sort((a, b) => b.new_weight - a.new_weight)
  return {
    exam_id: examId.value,
    days_left: 5,
    done_tasks: 3,
    total_tasks: 5,
    completion_rate: 0.6,
    wrong_questions: 3,
    weights,
    plan: mockAnalysis.review_plan.map((item, i) => ({ ...item, day: i + 1 })),
    applied: false,
    task_count: 0,
    note: '演示数据：剩余 5 天，打卡完成率 60%，自测错题 3 道。',
  }
}

const applyMockReplan = () => {
  const preview = replanPreview.value
  if (!preview || !result.value) return
  const weightMap = Object.fromEntries(
    preview.weights.map((item) => [item.name, item.new_weight]),
  )
  result.value.knowledge_points = result.value.knowledge_points
    .map((kp) => ({ ...kp, weight: weightMap[kp.name] ?? kp.weight }))
    .sort((a, b) => b.weight - a.weight)
  result.value.review_plan = preview.plan
}

const onReplanPreview = async () => {
  if (!examId.value) return
  replanLoading.value = true
  try {
    replanPreview.value = USE_MOCK
      ? buildMockReplan()
      : await aiApi.replan(examId.value, false)
    replanVisible.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '预览失败，请稍后重试')
  } finally {
    replanLoading.value = false
  }
}

const onReplanApply = async () => {
  if (!replanPreview.value) return
  replanApplying.value = true
  try {
    if (USE_MOCK) {
      applyMockReplan()
    } else {
      replanPreview.value = await aiApi.replan(examId.value, true)
      try {
        const latest = await aiApi.latestAnalysis(examId.value)
        result.value = latest.result
      } catch {
        /* 保留当前展示 */
      }
      await loadStudy()
      await renderTypeChart()
    }
    replanVisible.value = false
    ElMessage.success('已按当前进度调整计划与权重')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '应用失败，请稍后重试')
  } finally {
    replanApplying.value = false
  }
}

const onAnalyze = async () => {
  analyzing.value = true
  analyzeError.value = ''
  step.value = 2
  try {
    if (USE_MOCK) {
      // mock 模式下返回本地演示分析结果（模拟分析耗时）
      await new Promise((r) => setTimeout(r, 1500))
      result.value = structuredClone(mockAnalysis)
    } else {
      const resp = await aiApi.analyze(examId.value)
      result.value = resp.result
    }
    await loadStudy()
    await renderTypeChart()
    await loadQa()
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
  study.value = null
  cardIndex.value = 0
  cardFlipped.value = false
  qaConversationId.value = null
  qaMessages.value = []
  qaInput.value = ''
  replanPreview.value = null
  replanVisible.value = false
  if (USE_MOCK) return // 预览模式下每次都从第一步开始演示
  // 已有分析结果的科目直接展示
  try {
    const resp = await aiApi.latestAnalysis(examId.value)
    result.value = resp.result
    step.value = 2
    await loadStudy()
    await renderTypeChart()
    await loadQa()
  } catch {
    /* 没有历史分析，从第一步开始 */
  }
}

onMounted(async () => {
  window.addEventListener('resize', resizeMindmap)
  if (USE_MOCK) {
    exams.value = mockExams
    return
  }
  exams.value = await examApi.list()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeMindmap)
  mindmapChart?.dispose()
  mindmapChart = null
  typeChart?.dispose()
  typeChart = null
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
.mindmap-chart {
  width: 100%;
  height: 460px;
}
.type-block {
  margin-bottom: 8px;
}
.type-chart {
  width: 100%;
  height: 260px;
}
.type-table {
  margin-top: 4px;
}
.flash-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 8px 0 4px;
}
.flash-card {
  width: min(580px, 100%);
  height: 230px;
  perspective: 1200px;
  cursor: pointer;
}
.flash-inner {
  position: relative;
  width: 100%;
  height: 100%;
  transition: transform 0.5s;
  transform-style: preserve-3d;
}
.flash-card.flipped .flash-inner {
  transform: rotateY(180deg);
}
.flash-face {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
  backface-visibility: hidden;
  background: var(--bg-card);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}
.flash-back {
  transform: rotateY(180deg);
  background: var(--coral-soft);
}
.flash-label {
  font-size: 12px;
  color: var(--text-low);
}
.flash-text {
  margin: 0;
  font-size: 16px;
  line-height: 1.75;
  color: var(--text-hi);
  white-space: pre-wrap;
}
.flash-hint {
  font-size: 12px;
  color: var(--text-low);
}
.flash-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.flash-count {
  font-size: 13px;
  color: var(--text-mid);
  min-width: 64px;
  text-align: center;
}
.qa-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 340px;
  overflow-y: auto;
  padding: 4px 2px 8px;
}
.qa-row {
  display: flex;
  justify-content: flex-start;
}
.qa-row.user {
  justify-content: flex-end;
}
.qa-bubble {
  max-width: 78%;
  padding: 10px 12px;
  background: var(--bg-soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
}
.qa-row.user .qa-bubble {
  background: var(--coral-soft);
  border-color: var(--coral);
}
.qa-role {
  margin-bottom: 4px;
  font-size: 11px;
  color: var(--text-low);
}
.qa-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-hi);
  white-space: pre-wrap;
}
.qa-input-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-top: 12px;
}
.qa-input-box {
  flex: 1;
}
.replan-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}
.replan-tip {
  font-size: 12px;
  color: var(--text-low);
}
.replan-note {
  margin-bottom: 14px;
}
.replan-title {
  margin: 4px 0 10px;
  font-size: 14px;
  color: var(--text-hi);
}
.weight-up {
  color: var(--red);
  font-weight: 600;
}
.weight-down {
  color: var(--green);
  font-weight: 600;
}
</style>
