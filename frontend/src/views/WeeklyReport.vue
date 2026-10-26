<template>
  <div class="report-page">
    <div class="page-head">
      <div class="head-main">
        <h2>备考周报</h2>
        <span class="head-sub">近 7 天学习小结 · 大模型各科掌握度评测（内容仅供复习参考）</span>
      </div>
      <div class="head-actions">
        <el-button-group class="week-switch">
          <el-button @click="shiftWeek(-1)">
            <el-icon><ArrowLeft /></el-icon>
            上一周
          </el-button>
          <el-button :disabled="weekOffset >= 0" @click="shiftWeek(1)">
            下一周
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </el-button-group>
        <el-button v-if="weekOffset !== 0" text type="primary" @click="resetWeek">回到最近 7 天</el-button>
        <el-button type="primary" :loading="loading" @click="load">
          <el-icon v-if="!loading"><MagicStick /></el-icon>
          {{ loading ? 'AI 正在评测…' : data ? '重新生成' : '生成周报' }}
        </el-button>
        <el-button :disabled="loading || !data || !data.subjects.length" @click="onExportMarkdown">
          <el-icon><Download /></el-icon>
          导出 Markdown
        </el-button>
      </div>
    </div>

    <div v-if="data" class="range-line">
      <span class="range-chip">
        <el-icon><Calendar /></el-icon>
        {{ data.week_start }} ~ {{ data.week_end }}
      </span>
      <span>生成时间 {{ formatTime(data.generated_at) }}</span>
    </div>

    <!-- ===== 首次加载骨架 ===== -->
    <template v-if="loading && !data">
      <div class="sk-tiles">
        <div v-for="i in 4" :key="i" class="sk-tile"><el-skeleton animated :rows="2" /></div>
      </div>
      <div class="sk-box"><el-skeleton animated :rows="6" /></div>
      <div class="sk-grid">
        <div class="sk-box"><el-skeleton animated :rows="5" /></div>
        <div class="sk-box"><el-skeleton animated :rows="5" /></div>
      </div>
    </template>

    <!-- ===== 错误状态 ===== -->
    <div v-else-if="error" class="panel error-box">
      <el-result icon="warning" title="周报生成失败" :sub-title="error">
        <template #extra>
          <el-button type="primary" round @click="load">重新生成</el-button>
        </template>
      </el-result>
    </div>

    <div v-else-if="data" v-loading="loading" element-loading-text="AI 正在评测各科掌握度…">
      <!-- ===== 数据总览 ===== -->
      <section class="stats">
        <div v-for="s in kpiTiles" :key="s.label" class="stat-tile">
          <span class="stat-icon" :style="{ background: s.soft, color: s.color }">
            <el-icon :size="20"><component :is="s.icon" /></el-icon>
          </span>
          <div class="stat-info">
            <div class="stat-value">{{ s.value }}</div>
            <div class="stat-label">{{ s.label }}</div>
            <div class="stat-sub">{{ s.sub }}</div>
          </div>
        </div>
      </section>

      <div v-if="data.note" class="panel note-panel">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ data.note }}</span>
      </div>

      <!-- ===== AI 总评 ===== -->
      <section v-if="hasScored" class="panel ai-panel">
        <div class="panel-head">
          <h2>AI 周报总评</h2>
          <span class="panel-sub">综合任务完成率与专注时长评测</span>
        </div>
        <p class="summary-text">{{ data.summary }}</p>
        <div class="ai-cols">
          <div v-if="data.highlights.length" class="ai-col">
            <h3><el-icon><Trophy /></el-icon>本周亮点</h3>
            <ul>
              <li v-for="(item, i) in data.highlights" :key="i">{{ item }}</li>
            </ul>
          </div>
          <div v-if="data.next_week_advice.length" class="ai-col">
            <h3><el-icon><Aim /></el-icon>下周建议</h3>
            <ul>
              <li v-for="(item, i) in data.next_week_advice" :key="i">{{ item }}</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- ===== 各科掌握程度 ===== -->
      <section v-if="data.subjects.length" class="panel">
        <div class="panel-head">
          <h2>各科掌握程度</h2>
          <span class="panel-sub">评分范围 0~100，由大模型结合本周数据评测</span>
        </div>
        <div class="subject-grid">
          <article v-for="s in subjectCards" :key="s.subject" class="subject-card">
            <div class="subject-top">
              <div>
                <div class="subject-name">{{ s.subject }}</div>
                <div class="subject-meta">
                  <span v-if="s.exam_date">{{ s.exam_date }}</span>
                  <span v-if="s.days_left != null">距考试 <b class="num">{{ s.days_left }}</b> 天</span>
                </div>
              </div>
              <el-tag :type="tagType(s.level)" effect="light" round>{{ s.level }}</el-tag>
            </div>

            <div class="subject-body">
              <el-progress
                type="dashboard"
                :percentage="s.mastery ?? 0"
                :width="104"
                :stroke-width="7"
                :color="masteryColor(s.mastery)"
              >
                <template #default>
                  <div class="mastery-num num">{{ s.mastery ?? '—' }}</div>
                  <div class="mastery-label">掌握度</div>
                </template>
              </el-progress>
              <div class="metric-list">
                <div><span>学习时长</span><b class="num">{{ s.minutes }}</b><em>分钟</em></div>
                <div><span>任务完成</span><b class="num">{{ s.done_tasks }} / {{ s.total_tasks }}</b></div>
                <div><span>完成率</span><b class="num">{{ Math.round(s.rate * 100) }}%</b></div>
              </div>
            </div>

            <p class="subject-comment">{{ s.comment }}</p>
            <div v-if="s.suggestions.length" class="suggestions">
              <span v-for="(tip, i) in s.suggestions" :key="i" class="suggestion">{{ tip }}</span>
            </div>
          </article>
        </div>

        <div v-if="freeSubject" class="free-note">
          <el-icon><Timer /></el-icon>
          「未指定科目」的自由专注共 <b class="num">{{ freeSubject.minutes }}</b> 分钟，绑定科目后可获得掌握度评测。
        </div>
        <div v-for="s in archivedSubjects" :key="s.subject" class="free-note">
          {{ s.subject }}：<b class="num">{{ s.minutes }}</b> 分钟，已计入学习总时长。
        </div>
      </section>

      <!-- ===== 空状态 ===== -->
      <section v-if="!data.subjects.length" class="panel empty-box">
        <span class="empty-icon"><el-icon :size="26"><Document /></el-icon></span>
        <div class="empty-title">这个区间还没有学习记录</div>
        <div class="empty-sub">去首页完成一个任务，或用番茄钟专注一次，再回来生成周报</div>
        <el-button type="primary" round class="empty-action" @click="$router.push('/')">去首页开始学习</el-button>
      </section>

      <!-- ===== 每日学习记录 ===== -->
      <section v-if="data.subjects.length" class="panel">
        <div class="panel-head">
          <h2>每日学习记录</h2>
          <span class="panel-sub">最近在前</span>
        </div>
        <el-table :data="dailyRows" empty-text="该区间暂无学习记录" style="width: 100%">
          <el-table-column prop="date" label="日期" min-width="130" />
          <el-table-column label="学习时长" min-width="130">
            <template #default="{ row }"><span class="num">{{ row.minutes }}</span> 分钟</template>
          </el-table-column>
          <el-table-column label="任务（完成 / 计划）" min-width="150">
            <template #default="{ row }">{{ row.done }} / {{ row.total }}</template>
          </el-table-column>
          <el-table-column label="完成率" min-width="190">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.rate * 100)" :stroke-width="10" color="#e66348" />
            </template>
          </el-table-column>
        </el-table>
      </section>

      <p class="disclaimer">大模型生成内容仅供复习参考，请结合教材与课堂要求判断。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dashboardApi } from '../api'
import { USE_MOCK, getToday } from '../mock/dashboard'
import { mockWeeklyReport } from '../mock/pages'

const pad2 = (n) => String(n).padStart(2, '0')
const asDate = (s) => new Date(`${s}T00:00:00`)
const fmtDate = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
const addDays = (s, n) => {
  const d = asDate(s)
  d.setDate(d.getDate() + n)
  return fmtDate(d)
}

const todayStr = getToday()
const loading = ref(true)
const error = ref('')
const data = ref(null)
const weekOffset = ref(0)

const weekStart = computed(() => addDays(todayStr, -6 + weekOffset.value * 7))

const formatTime = (value) => (value ? String(value).replace('T', ' ').slice(0, 16) : '')
const levelOf = (score) =>
  score == null ? '暂无评测' : score >= 85 ? '优秀' : score >= 70 ? '良好' : score >= 55 ? '一般' : '薄弱'
const tagType = (level) =>
  ({ 优秀: 'success', 良好: 'success', 一般: 'warning', 薄弱: 'danger' })[level] || 'info'
const masteryColor = (score) =>
  score == null ? '#8b9084' : score >= 70 ? '#35554c' : score >= 55 ? '#a06a22' : '#b63a2e'

const kpiTiles = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    {
      label: '学习时长',
      value: `${d.total_minutes} 分`,
      sub: `活跃 ${d.active_days} 天`,
      icon: 'Timer',
      color: 'var(--coral-deep)',
      soft: 'var(--coral-soft)',
    },
    {
      label: '任务完成',
      value: `${d.done_tasks} / ${d.total_tasks}`,
      sub: '本周计划任务',
      icon: 'CircleCheck',
      color: 'var(--green)',
      soft: 'var(--green-soft)',
    },
    {
      label: '完成率',
      value: `${Math.round(d.rate * 100)}%`,
      sub: '本周任务口径',
      icon: 'TrendCharts',
      color: 'var(--teal)',
      soft: 'var(--teal-soft)',
    },
    {
      label: '综合掌握度',
      value: d.overall_mastery == null ? '—' : `${d.overall_mastery} 分`,
      sub: levelOf(d.overall_mastery),
      icon: 'Trophy',
      color: 'var(--amber)',
      soft: 'var(--amber-soft)',
    },
  ]
})

const hasScored = computed(() => !!data.value?.subjects.some((s) => s.exam_id !== null))
const subjectCards = computed(() => data.value?.subjects.filter((s) => s.exam_id !== null) ?? [])
const freeSubject = computed(() => data.value?.subjects.find((s) => s.exam_id === null && !s.archived) || null)
const archivedSubjects = computed(() => data.value?.subjects.filter((s) => s.archived) ?? [])
const dailyRows = computed(() => [...(data.value?.days ?? [])].reverse())

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    data.value = USE_MOCK
      ? await mockWeeklyReport(weekStart.value)
      : await dashboardApi.weeklyReport(weekStart.value)
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '网络异常，请稍后重试'
  } finally {
    loading.value = false
  }
}

const shiftWeek = (delta) => {
  const next = weekOffset.value + delta
  if (next > 0 || loading.value) return
  weekOffset.value = next
  load()
}

const resetWeek = () => {
  if (weekOffset.value === 0 || loading.value) return
  weekOffset.value = 0
  load()
}

const onExportMarkdown = () => {
  const d = data.value
  if (!d) return
  const lines = [
    `# 备考周报（${d.week_start} ~ ${d.week_end}）`,
    '',
    `> 生成时间：${formatTime(d.generated_at)}`,
    '',
    '## 学习总览',
    '',
    `- 学习时长：${d.total_minutes} 分钟（活跃 ${d.active_days} 天）`,
    `- 任务完成：${d.done_tasks} / ${d.total_tasks}（完成率 ${Math.round(d.rate * 100)}%）`,
    `- 综合掌握度：${d.overall_mastery ?? '—'} 分`,
    '',
    '## AI 周报总评',
    '',
    d.summary,
    '',
  ]
  if (d.highlights.length) lines.push('### 本周亮点', '', ...d.highlights.map((x) => `- ${x}`), '')
  if (d.next_week_advice.length) lines.push('### 下周建议', '', ...d.next_week_advice.map((x) => `- ${x}`), '')
  lines.push(
    '## 各科掌握程度',
    '',
    '| 科目 | 学习时长 | 任务完成 | 完成率 | 掌握度 | 评级 |',
    '|---|---|---|---|---|---|',
    ...d.subjects.map(
      (s) =>
        `| ${s.subject} | ${s.minutes} 分钟 | ${s.done_tasks}/${s.total_tasks} | ${Math.round(s.rate * 100)}% | ${s.mastery ?? '—'} | ${s.level || '—'} |`,
    ),
    '',
  )
  for (const s of d.subjects.filter((x) => x.exam_id !== null)) {
    if (!s.comment && !s.suggestions.length) continue
    lines.push(`### ${s.subject}`, '')
    if (s.comment) lines.push(s.comment, '')
    for (const tip of s.suggestions) lines.push(`- ${tip}`)
    lines.push('')
  }
  lines.push(
    '## 每日学习记录',
    '',
    '| 日期 | 学习时长 | 任务（完成/计划） | 完成率 |',
    '|---|---|---|---|',
    ...d.days
      .slice()
      .reverse()
      .map((day) => `| ${day.date} | ${day.minutes} 分钟 | ${day.done}/${day.total} | ${Math.round(day.rate * 100)}% |`),
    '',
    '---',
    '',
    '大模型生成内容仅供复习参考，请结合教材与课堂要求判断。',
  )

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `备考周报_${d.week_start}_${d.week_end}.md`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已下载 Markdown 周报')
}

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.head-main h2 {
  margin: 0;
}
.head-sub {
  display: block;
  margin-top: 4px;
  font-size: 13px;
  color: var(--ink-3);
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.week-switch :deep(.el-button) {
  padding-inline: 12px;
}
.range-line {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--ink-3);
}
.range-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--ink-2);
  font-family: var(--font-num);
}

/* —— 通用面板 —— */
.panel {
  background: var(--bg-card);
  border: 2px solid var(--ink-1);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-ink-xs);
  padding: 22px 24px;
  margin-bottom: 16px;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.panel-head h2 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 900;
  letter-spacing: 0.05em;
  color: var(--ink-1);
  border-left: 4px solid var(--coral);
  padding-left: 10px;
  line-height: 1.3;
}
.panel-sub {
  font-size: 12px;
  color: var(--ink-3);
}

/* —— 数据总览 —— */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.stat-tile {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-card);
  border: 2px solid var(--ink-1);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-ink-xs);
  padding: 17px 19px;
  transition: all 0.18s;
}
.stat-tile:hover {
  box-shadow: var(--shadow-ink-sm);
  transform: translate(-1px, -1px);
}
.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  border: 1.5px solid var(--ink-1);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.stat-value {
  font-size: 23px;
  font-weight: 700;
  color: var(--ink-1);
  line-height: 1.2;
}
.stat-label {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
}
.stat-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--ink-3);
}

/* —— 提示与总评 —— */
.note-panel {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  color: var(--ink-2);
  font-size: 13px;
  background: var(--amber-soft);
}
.summary-text {
  margin: 0 0 18px;
  font-size: 14.5px;
  line-height: 1.85;
  color: var(--ink-1);
}
.ai-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.ai-col {
  background: var(--bg-soft);
  border: 1.5px solid var(--line);
  border-radius: var(--radius-md);
  padding: 14px 18px;
}
.ai-col h3 {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--ink-1);
}
.ai-col ul {
  margin: 0;
  padding-left: 18px;
  color: var(--ink-2);
  font-size: 13px;
  line-height: 1.8;
}

/* —— 科目卡片 —— */
.subject-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.subject-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 20px;
  background: var(--bg-page);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-ink-xs);
}
.subject-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.subject-name {
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 900;
  color: var(--ink-1);
}
.subject-meta {
  display: flex;
  gap: 10px;
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--ink-3);
}
.subject-body {
  display: flex;
  align-items: center;
  gap: 20px;
}
.mastery-num {
  font-size: 24px;
  font-weight: 700;
  color: var(--ink-1);
  line-height: 1.1;
}
.mastery-label {
  font-size: 10px;
  color: var(--ink-3);
}
.metric-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-3);
}
.metric-list > div {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.metric-list span {
  min-width: 56px;
}
.metric-list b {
  font-size: 14px;
  color: var(--ink-1);
}
.metric-list em {
  font-style: normal;
  font-size: 11px;
}
.subject-comment {
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2);
}
.suggestions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.suggestion {
  padding: 7px 10px;
  border-left: 3px solid var(--coral);
  background: var(--coral-soft);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-2);
}
.free-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
  font-size: 12.5px;
  color: var(--ink-3);
}
.free-note b {
  color: var(--ink-1);
}

/* —— 空状态 / 免责 —— */
.empty-box {
  text-align: center;
  padding: 42px 24px;
}
.empty-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: var(--coral-soft);
  color: var(--coral-deep);
  border: 1.5px solid var(--ink-1);
  display: inline-grid;
  place-items: center;
}
.empty-title {
  margin-top: 14px;
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 900;
  color: var(--ink-1);
}
.empty-sub {
  margin-top: 6px;
  font-size: 13px;
  color: var(--ink-3);
}
.empty-action {
  margin-top: 16px;
}
.disclaimer {
  margin: 4px 0 0;
  text-align: center;
  font-size: 11.5px;
  color: var(--ink-3);
}

/* —— 骨架屏 —— */
.sk-tile,
.sk-box {
  background: var(--bg-card);
  border: 2px solid var(--line-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-ink-xs);
}
.sk-tiles {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.sk-tile {
  padding: 20px;
}
.sk-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.sk-box {
  padding: 22px 24px;
  margin-bottom: 16px;
}

@media (max-width: 900px) {
  .stats,
  .sk-tiles {
    grid-template-columns: repeat(2, 1fr);
  }
  .subject-grid,
  .ai-cols,
  .sk-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 560px) {
  .stats,
  .sk-tiles {
    grid-template-columns: 1fr;
  }
  .panel {
    padding: 18px;
  }
  .subject-body {
    gap: 14px;
  }
}
</style>
