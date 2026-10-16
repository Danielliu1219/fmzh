<template>
  <div class="dash">
    <!-- ===== 加载骨架（首屏演示加载状态） ===== -->
    <template v-if="loading">
      <div class="sk-hero">
        <el-skeleton animated>
          <template #template>
            <div class="sk-flex">
              <div class="sk-col">
                <el-skeleton-item variant="text" style="width: 52%; height: 30px" />
                <el-skeleton-item variant="text" style="width: 78%; height: 15px" />
                <el-skeleton-item variant="text" style="width: 60%; height: 15px" />
                <div style="display: flex; gap: 12px; margin-top: 14px">
                  <el-skeleton-item variant="button" style="width: 160px; height: 42px; border-radius: 8px" />
                  <el-skeleton-item variant="button" style="width: 150px; height: 42px; border-radius: 8px" />
                </div>
              </div>
              <el-skeleton-item variant="circle" style="width: 170px; height: 170px" />
            </div>
          </template>
        </el-skeleton>
      </div>
      <div class="sk-tiles">
        <div v-for="i in 4" :key="i" class="sk-tile">
          <el-skeleton animated :rows="2" />
        </div>
      </div>
      <div class="sk-main"><el-skeleton animated :rows="5" /></div>
      <div class="sk-grid">
        <div class="sk-main"><el-skeleton animated :rows="6" /></div>
        <div class="sk-side"><el-skeleton animated :rows="4" /></div>
      </div>
    </template>

    <!-- ===== 错误状态 ===== -->
    <div v-else-if="error" class="panel error-box">
      <el-result icon="warning" title="页面加载失败" :sub-title="error">
        <template #extra>
          <el-button type="primary" round @click="load">重新加载</el-button>
        </template>
      </el-result>
    </div>

    <template v-else>
      <!-- ===== Hero ===== -->
      <section class="hero rise" style="--d: 0ms">
        <div class="hero-inner">
          <div class="hero-left">
            <p class="hero-kicker">{{ greeting }}，{{ userStore.displayName }} · {{ todayText }}</p>
            <h1 class="hero-title">上传资料，<span class="coral-text">AI 帮你拆出</span>期末复习计划</h1>
            <p class="hero-sub">
              历年真题、课堂笔记、老师划的重点，交给 AI 拆成按天排好的复习任务。你只管打卡，剩下的交给它。
            </p>
            <div class="hero-actions">
              <el-button type="primary" size="large" round @click="$router.push('/analysis')">
                <el-icon><MagicStick /></el-icon>&nbsp;生成我的复习计划
              </el-button>
              <el-button size="large" round class="ghost-btn" @click="$router.push('/materials')">
                <el-icon><Upload /></el-icon>&nbsp;上传复习资料
              </el-button>
            </div>
          </div>
          <div class="hero-right">
            <div class="hero-ring" :style="{ '--p': countdownPct }">
              <div class="hero-ring-in">
                <span class="hr-num" :class="{ text: nearestExam && nearestExam.days_left === 0 }">{{ nearestExam ? (nearestExam.days_left === 0 ? '今天' : nearestExam.days_left) : '—' }}</span>
                <span class="hr-label">{{ nearestExam ? `天后 · ${nearestExam.subject}` : '暂无考试' }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ===== 流程引导 ===== -->
      <section class="panel flow rise" style="--d: 80ms">
        <div class="panel-head">
          <h2>四步搞定期末</h2>
          <span class="panel-sub">从资料到计划，全程 AI 代劳</span>
        </div>
        <div class="flow-steps">
          <div v-for="s in flowSteps" :key="s.name" class="flow-step" @click="goStep(s.to)">
            <span class="step-icon"><el-icon :size="18"><component :is="s.icon" /></el-icon></span>
            <div class="step-text">
              <span class="step-name">{{ s.name }}</span>
              <span class="step-desc">{{ s.desc }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- ===== 数据总览 ===== -->
      <section class="stats rise" style="--d: 160ms">
        <div v-for="s in statTiles" :key="s.label" class="stat-tile">
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

      <!-- ===== 今日最重要的三件事（模块 7.4） ===== -->
      <section v-if="top3" class="panel top3 rise" style="--d: 180ms">
        <div class="panel-head">
          <h2>今日最重要的三件事</h2>
          <span class="panel-sub">按权重、截止时间与压力指数置顶</span>
        </div>
        <p v-if="top3.note" class="t3-note">{{ top3.note }}</p>
        <ol v-else class="t3-list">
          <li v-for="(it, i) in top3.items" :key="it.task_id" class="t3-item" :class="{ first: i === 0 }">
            <span class="t3-rank">{{ i + 1 }}</span>
            <div class="t3-body">
              <div class="t3-title">{{ it.title }}</div>
              <div class="t3-meta">
                <span v-if="it.subject" class="t3-subject">{{ it.subject }}</span>
                <span class="t3-reason">{{ it.reason }}</span>
              </div>
            </div>
            <span class="t3-min">{{ it.estimated_minutes }} min</span>
          </li>
        </ol>
      </section>

      <!-- ===== 压力指数（模块 7.1） ===== -->
<section v-if="pressure" class="panel pressure rise" :class="{ alert: pressure.need_emergency }" style="--d: 200ms">
  <div class="pressure-main">
    <div class="pressure-score">
      <span class="ps-num">{{ pressure.score }}</span>
      <span class="ps-label">期末压力指数 · {{ pressure.level }}</span>
    </div>
    <div class="pressure-bar">
      <div class="pb-fill" :style="{ width: pressure.score + '%' }"></div>
    </div>
    <p class="pressure-tip">{{ pressure.suggestion }}</p>
  </div>
  <el-button type="primary" round @click="onEmergency">
    开启临时救急模式
  </el-button>
</section>

<!-- ===== 临时救急模式 · 冲刺清单（模块 7.2） ===== -->
<el-dialog
  v-model="emergencyVisible"
  title="临时救急模式 · 考前冲刺清单"
  width="640px"
  align-center
>
  <div v-if="emergency" class="emergency">
    <div class="eg-head">
      <span class="eg-subject">{{ emergency.subject }}</span>
      <span class="eg-meta">距考试 {{ emergency.days_left }} 天 · {{ emergency.exam_date }}</span>
    </div>
    <p v-if="emergency.note" class="eg-note">{{ emergency.note }}</p>
    <ul v-else class="eg-list">
      <li v-for="(it, i) in emergency.items" :key="i" class="eg-item">
        <span class="eg-idx">{{ i + 1 }}</span>
        <div class="eg-body">
          <div class="eg-line">
            <span class="eg-kind" :class="it.kind === '考点' ? 'focus' : 'kp'">{{ it.kind }}</span>
            <span class="eg-content">{{ it.content }}</span>
          </div>
          <div v-if="it.basis" class="eg-basis">{{ it.basis }}</div>
        </div>
        <span v-if="it.weight != null" class="eg-weight">权重 {{ it.weight }}</span>
      </li>
    </ul>
  </div>
  <div v-else class="eg-loading">加载中…</div>
</el-dialog>

<!-- ===== 低情绪减负与计划重排（模块 7.7） ===== -->
<el-dialog
  v-model="reliefVisible"
  title="低情绪减负 · 计划重排"
  width="620px"
  align-center
>
  <div class="relief">
    <div class="rf-opts">
      <el-button :type="reliefOption === 'lighten' ? 'primary' : 'default'" round @click="pickRelief('lighten')">
        减轻当日任务
      </el-button>
      <el-button :type="reliefOption === 'halfday' ? 'primary' : 'default'" round @click="pickRelief('halfday')">
        暂停半天
      </el-button>
      <span class="rf-cap">重排后今日可用 {{ relief ? relief.today_capacity : '—' }} 分钟</span>
    </div>
    <div v-if="relief" class="rf-body">
      <p class="rf-summary">{{ relief.summary }}</p>
      <ul v-if="relief.moves.length" class="rf-list">
        <li v-for="m in relief.moves" :key="m.task_id" class="rf-item">
          <span class="rf-title">{{ m.title }}</span>
          <span class="rf-dates">{{ m.from_date }} → {{ m.to_date }}</span>
        </li>
      </ul>
      <div v-if="relief.conflicts.length" class="rf-conflicts">
        <div class="rf-conf-head">以下任务考前排不下，需要取舍：</div>
        <ul>
          <li v-for="c in relief.conflicts" :key="c.task_id">{{ c.title }} —— {{ c.reason }}</li>
        </ul>
      </div>
    </div>
    <div v-else class="rf-loading">加载中…</div>
  </div>
  <template #footer>
    <el-button @click="reliefVisible = false">取消</el-button>
    <el-button type="primary" :disabled="!relief" @click="confirmRelief">确认调整</el-button>
  </template>
</el-dialog>

      <!-- ===== 情绪记录（模块 7.6） ===== -->
      <section class="panel mood rise" style="--d: 280ms">
        <div class="panel-head">
          <h2>今日情绪记录</h2>
          <span class="panel-sub">给今天的心情打个分，帮你调整复习节奏</span>
        </div>
        <div class="mood-body">
          <div class="mood-pick">
            <el-rate v-model="moodScore" :max="5" size="large" @change="onMoodChange" />
            <span class="mood-hint">{{ moodHint }}</span>
          </div>
          <div v-if="mood" class="mood-result" :class="{ low: mood.need_relief }">
            <div class="mood-score">
              <span class="ms-num">{{ mood.composite_score }}</span>
              <span class="ms-label">情绪综合评分（满分 5）</span>
            </div>
            <p class="mood-tip">{{ mood.suggestion }}</p>
            <el-button v-if="mood.need_relief" type="primary" round @click="onRelief">
              减轻今日负担
            </el-button>
          </div>
        </div>
      </section>

      <!-- ===== 考前重点回顾（模块 7.3） ===== -->
      <section v-if="review && review.items.length" class="panel review rise" style="--d: 320ms">
        <div class="panel-head">
          <h2>考前重点回顾</h2>
          <span class="panel-sub">{{ review.subject }} · 距考试 {{ review.days_left }} 天，按权重从高到低过一遍</span>
        </div>
        <ul class="rv-list">
          <li v-for="(it, i) in review.items" :key="i" class="rv-item">
            <span class="rv-idx">{{ i + 1 }}</span>
            <span class="rv-name">{{ it.name }}</span>
            <div class="rv-bar"><div class="rv-fill" :style="{ width: Math.round(it.weight * 100) + '%' }"></div></div>
            <span class="rv-weight">{{ Math.round(it.weight * 100) }}%</span>
            <span v-if="it.suggest_hours" class="rv-hours">建议 {{ it.suggest_hours }}h</span>
          </li>
        </ul>
      </section>

      <!-- ===== 学习时段推荐（模块 7.5） ===== -->
      <section v-if="timeslots" class="panel timeslots rise" style="--d: 360ms">
        <div class="panel-head">
          <h2>学习时段推荐</h2>
          <span class="panel-sub">按每日可用 {{ timeslots.daily_hours }} 小时分配到时段</span>
        </div>
        <p v-if="timeslots.note" class="ts-note">{{ timeslots.note }}</p>
        <div class="ts-grid">
          <div v-for="s in timeslots.slots" :key="s.name" class="ts-card">
            <div class="ts-name">{{ s.name }}</div>
            <div class="ts-time">{{ s.start }}–{{ s.end }}</div>
            <div class="ts-min">{{ s.minutes }} 分钟</div>
            <div class="ts-focus">{{ s.focus }}</div>
          </div>
        </div>
      </section>

      <!-- ===== 考表 · 考试倒计时（日程时间线） ===== -->
      <section class="panel rise" style="--d: 240ms">
        <div class="panel-head">
          <h2>考表 · 倒计时</h2>
          <el-button link type="primary" @click="$router.push('/exams')">管理课程 →</el-button>
        </div>

        <!-- 空状态 -->
        <div v-if="!exams.length" class="empty-box">
          <span class="empty-icon"><el-icon :size="26"><Calendar /></el-icon></span>
          <div class="empty-title">还没有录入考试</div>
          <div class="empty-sub">先录入考试日期，考表和倒计时才有内容</div>
          <el-button type="primary" round @click="$router.push('/exams')">去录入考试</el-button>
        </div>

        <div v-else class="timeline">
          <div v-for="e in sortedExams" :key="e.id" class="tl-item">
            <span class="tl-node" :class="{ urgent: e.days_left <= 3 }"></span>
            <div class="tl-date">
              <span class="tl-md">{{ fmtMd(e.exam_date) }}</span>
              <span class="tl-week">{{ weekOf(e.exam_date) }}</span>
            </div>
            <div class="tl-body">
              <div class="tl-subject"><span class="tl-dot" :style="{ background: subjectColor(e.subject).color }" />{{ e.subject }}</div>
              <div class="tl-meta">{{ e.location || '地点未填' }} · {{ e.duration_minutes }} 分钟</div>
              <el-progress
                v-if="e.total_tasks"
                :percentage="Math.round(e.progress * 100)"
                :stroke-width="5"
                :show-text="false"
                color="#e66348"
                class="tl-bar"
              />
              <router-link v-else class="tl-cta" to="/analysis">还没有复习计划，去生成 →</router-link>
            </div>
            <div class="tl-count" :class="{ urgent: e.days_left <= 3 }">
              <span class="tl-days" :class="{ text: e.days_left === 0 }">{{ e.days_left === 0 ? '今天' : e.days_left }}</span>
              <span class="tl-unit">{{ e.days_left === 0 ? '开考' : '天后' }}</span>
            </div>
          </div>
        </div>
      </section>

      <el-row :gutter="20" class="rise" style="--d: 320ms">
        <!-- ===== 任务看板 ===== -->
        <el-col :xs="24" :md="16">
          <section id="board" class="panel">
            <div class="panel-head">
              <h2>任务看板</h2>
              <span class="panel-sub">按天执行，别积压到最后一天</span>
            </div>
            <div class="board-cols">
              <div v-for="col in boardCols" :key="col.key" class="board-col">
                <div class="col-head">
                  <span class="col-dot" :style="{ background: col.color }"></span>
                  <span class="col-name">{{ col.title }}</span>
                  <span class="col-count" :style="{ background: col.soft, color: col.color }">{{ col.items.length }}</span>
                </div>
                <div class="col-body">
                  <div
                    v-for="task in col.items"
                    :key="task.id"
                    class="task-card"
                    :class="{ done: task.is_done }"
                    :style="{ borderLeft: `4px solid ${subjectColor(task.exam).color}` }"
                  >
                    <el-checkbox v-if="!task.is_done" :model-value="false" @change="onToggle(task)" />
                    <span v-else class="task-check"><el-icon :size="10"><Check /></el-icon></span>
                    <div class="task-body">
                      <div class="task-title">{{ task.title }}</div>
                      <div class="task-meta">
                        <el-tag size="small" effect="plain" round :type="['', 'danger', 'warning', 'info'][task.priority]">
                          {{ ['', '高', '中', '低'][task.priority] }}优先
                        </el-tag>
                        <span class="task-exam">{{ task.exam }}</span>
                        <span class="task-min">{{ task.estimated_minutes }} 分钟</span>
                        <span class="task-date" :class="{ overdue: dateChip(task) === '已逾期' }">{{ dateChip(task) }}</span>
                      </div>
                    </div>
                    <el-button v-if="task.is_done" link size="small" class="undo" @click="onToggle(task)">撤销</el-button>
                  </div>
                  <div v-if="!col.items.length" class="col-empty">
                    <span class="ce-icon"><el-icon :size="20"><component :is="col.emptyIcon" /></el-icon></span>
                    <span class="ce-text">{{ col.emptyText }}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </el-col>

        <!-- ===== 右列：总进度 + 连续打卡 ===== -->
        <el-col :xs="24" :md="8">
          <section class="panel">
            <div class="panel-head"><h2>复习总进度</h2></div>
            <div class="ring-wrap">
              <div ref="chartRef" class="ring-chart"></div>
              <div class="ring-center">
                <span class="ring-pct">{{ rateText }}</span>
                <span class="ring-sub">已完成 {{ overall.done }} / {{ overall.total }} 个任务</span>
              </div>
            </div>
            <div class="ring-legend">
              <span class="lg"><i class="lg-dot done"></i>已完成</span>
              <span class="lg"><i class="lg-dot remain"></i>待完成</span>
            </div>
          </section>

          <section class="panel streak-panel">
            <div class="streak-head">
              <span class="streak-icon"><el-icon :size="16"><Timer /></el-icon></span>
              <div>
                <div class="streak-title">连续打卡 {{ extras.streak }} 天</div>
                <div class="streak-sub">本周专注 {{ extras.focus_minutes }} 分钟 · 状态不错</div>
              </div>
            </div>
            <div class="week-dots">
              <div v-for="(d, i) in weekDots" :key="d" class="week-dot" :class="{ on: i >= 7 - extras.streak, today: i === 6 }">
                <span class="dot-i">{{ i >= 7 - extras.streak ? '✓' : '' }}</span>
                <span class="dot-label">{{ d }}</span>
              </div>
            </div>
          </section>

          <!-- ===== 番茄钟 · 每日学习目标（FMZH-SRS-2.10.0） ===== -->
          <section class="panel focus-panel">
            <div class="panel-head">
              <h2>专注 · 番茄钟</h2>
              <span class="panel-sub">时长是学习统计依据</span>
            </div>

            <div class="focus-setup">
              <el-select v-model="focusExamId" size="default" placeholder="选择科目" :disabled="focusRunning">
                <el-option v-for="e in sortedExams" :key="e.id" :label="e.subject" :value="e.id" />
              </el-select>
              <el-select v-model="focusMinutes" size="default" :disabled="focusRunning" @change="onDurationChange">
                <el-option v-for="m in FOCUS_PRESETS" :key="m" :label="`${m} 分钟`" :value="m" />
              </el-select>
            </div>

            <div class="focus-clock" :class="{ running: focusRunning }">{{ clockText }}</div>

            <div v-if="!sortedExams.length" class="focus-tip">
              还没有科目，先<router-link to="/exams">录入考试</router-link>才能开始专注
            </div>

            <div class="focus-actions">
              <el-button type="primary" round :disabled="!focusExamId" @click="toggleFocus">
                <el-icon><component :is="focusRunning ? 'VideoPause' : 'VideoPlay'" /></el-icon>&nbsp;{{ focusRunning ? '暂停' : (focusStarted ? '继续' : '开始专注') }}
              </el-button>
              <el-button round class="ghost-btn" @click="resetFocus">重置</el-button>
            </div>

            <div class="focus-goal">
              <div class="fg-row">
                <span class="fg-label">今日专注</span>
                <span class="fg-num">
                  {{ focusData.total_minutes }}<em> / {{ focusData.goal_minutes || '—' }} 分钟</em>
                </span>
                <span v-if="focusData.achieved" class="fg-badge">已达标</span>
              </div>
              <el-progress :percentage="goalPct" :stroke-width="6" :show-text="false" color="#e66348" />
              <div class="fg-set">
                <span class="fg-hint">每日目标</span>
                <el-input-number v-model="goalInput" :min="0" :max="1440" :step="15" size="small" controls-position="right" />
                <el-button link type="primary" @click="saveGoal">保存</el-button>
              </div>
            </div>
          </section>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { dashboardApi, featureApi, focusApi, taskApi } from '../api'
import { useUserStore } from '../stores/user'
import { USE_MOCK, getToday, mockEmergency, mockMood, mockOverview, mockPressure, mockRelief, mockReview, mockTimeslots, mockTop3 } from '../mock/dashboard'
import { subjectColor } from '../utils/subjectColor'

const userStore = useUserStore()
const router = useRouter()

const loading = ref(true)
const error = ref('')
const exams = ref([])
const tasks = ref([])
const overall = ref({ total: 0, done: 0, rate: 0 })
const extras = ref({ streak: 0, focus_minutes: 0 })
const pressure = ref(null)
const mood = ref(null)
const moodScore = ref(0)
const emergencyVisible = ref(false)
const emergency = ref(null)
const review = ref(null)
const top3 = ref(null)
const timeslots = ref(null)
const reliefVisible = ref(false)
const reliefOption = ref('lighten')
const relief = ref(null)

// —— 番茄钟（FMZH-SRS-2.10.0）：计时结束时长计入对应科目，作为学习统计唯一依据 ——
const FOCUS_PRESETS = [25, 15, 45]
const focusData = ref({ total_minutes: 0, goal_minutes: 0, achieved: false, session_count: 0, by_exam: [] })
const focusExamId = ref(null)
const focusMinutes = ref(25)
const remainSec = ref(25 * 60)
const focusRunning = ref(false)
const focusStarted = ref(false)
const recordedMin = ref(0) // 本轮已写入统计的分钟数（防止重复计）
const goalInput = ref(60)
const weekFocus = ref(0)
let focusTimerId = null

const clockText = computed(() => {
  const m = String(Math.floor(remainSec.value / 60)).padStart(2, '0')
  const s = String(remainSec.value % 60).padStart(2, '0')
  return `${m}:${s}`
})
const goalPct = computed(() => {
  const g = focusData.value.goal_minutes
  if (!g) return 0
  return Math.min(100, Math.round((focusData.value.total_minutes / g) * 100))
})

const chartRef = ref(null)
let chart = null

// 进度环配色：数据色珊瑚 #e66348 vs 纸面轨道 #e4dfd0（墨纸设计系统）
const RING_TRACK = '#e4dfd0'

const flowSteps = [
  { icon: 'Upload', name: '上传资料', desc: '历年题、笔记、老师重点', to: '/materials' },
  { icon: 'EditPen', name: '填写目标', desc: '一句话说清你的情况', to: '/analysis' },
  { icon: 'MagicStick', name: '生成计划', desc: 'AI 拆出每天的任务', to: '/analysis' },
  { icon: 'CircleCheck', name: '每日打卡', desc: '跟着计划稳步推进', to: '#board' },
]

const todayText = computed(() => {
  const now = new Date()
  const week = ['日', '一', '二', '三', '四', '五', '六'][now.getDay()]
  return `${now.getMonth() + 1} 月 ${now.getDate()} 日 · 星期${week}`
})
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})

// —— 看板：待完成 / 进行中 / 已完成 ——
const board = computed(() => ({
  todo: tasks.value.filter((t) => !t.is_done && t.plan_date > getToday()),
  doing: tasks.value.filter((t) => !t.is_done && t.plan_date <= getToday()),
  done: tasks.value.filter((t) => t.is_done),
}))
const boardCols = computed(() => [
  { key: 'todo', title: '待完成', color: 'var(--ink-3)', soft: 'var(--bg-soft)', emptyIcon: 'Clock', emptyText: '暂无待办，去生成复习计划吧', items: board.value.todo },
  { key: 'doing', title: '进行中', color: 'var(--amber)', soft: 'var(--amber-soft)', emptyIcon: 'EditPen', emptyText: '今天没有进行中的任务', items: board.value.doing },
  { key: 'done', title: '已完成', color: 'var(--green)', soft: 'var(--green-soft)', emptyIcon: 'CircleCheck', emptyText: '完成的任务会出现在这里', items: board.value.done },
])

const rateText = computed(() => `${Math.round((overall.value.rate || 0) * 100)}%`)
const todayTotal = computed(() => tasks.value.filter((t) => t.plan_date === getToday()).length)
const todayDone = computed(
  () => tasks.value.filter((t) => t.plan_date === getToday() && t.is_done).length,
)
const nearestExam = computed(() =>
  exams.value.filter((e) => e.days_left >= 0).sort((a, b) => a.days_left - b.days_left)[0],
)
// Hero 倒计时环：剩余天数占 14 天窗口的比例
const countdownPct = computed(() => {
  if (!nearestExam.value) return 0
  return Math.min(100, Math.max(0, Math.round((nearestExam.value.days_left / 14) * 100)))
})
const sortedExams = computed(() =>
  [...exams.value].sort((a, b) => a.exam_date.localeCompare(b.exam_date)),
)
const weekDots = ['一', '二', '三', '四', '五', '六', '日']

const moodHint = computed(() => {
  const map = ['', '很差', '较差', '一般', '不错', '很好']
  return moodScore.value ? map[moodScore.value] : '今天心情怎么样？'
})

const statTiles = computed(() => [
  {
    icon: 'Calendar', label: '最近考试', color: 'var(--coral-deep)', soft: 'var(--coral-soft)',
    value: nearestExam.value ? `${nearestExam.value.days_left} 天` : '—',
    sub: nearestExam.value?.subject || '先去录入考试',
  },
  { icon: 'List', label: '今日任务', color: 'var(--amber)', soft: 'var(--amber-soft)', value: `${todayDone.value}/${todayTotal.value}`, sub: '今日已完成' },
  { icon: 'TrendCharts', label: '总完成率', color: 'var(--green)', soft: 'var(--green-soft)', value: rateText.value, sub: `共 ${overall.value.total} 个任务` },
  { icon: 'Timer', label: '连续打卡', color: 'var(--teal)', soft: 'var(--teal-soft)', value: `${extras.value.streak} 天`, sub: `本周专注 ${extras.value.focus_minutes} 分钟` },
])

const fmtMd = (d) => {
  const [, m, day] = d.split('-')
  return `${+m}月${+day}日`
}
const weekOf = (d) => `周${['日', '一', '二', '三', '四', '五', '六'][new Date(`${d}T00:00:00`).getDay()]}`
const dateChip = (t) => {
  if (t.is_done) return '已打卡'
  if (t.plan_date === getToday()) return '今天'
  if (t.plan_date < getToday()) return '已逾期'
  return fmtMd(t.plan_date)
}

// mock 模式下打卡/撤销仅改本地数据；真实模式下走接口
const onToggle = async (task) => {
  if (USE_MOCK) {
    task.is_done = !task.is_done
    syncOverall()
    renderRing()
    ElMessage.success(task.is_done ? '打卡成功，继续加油！' : '已取消打卡')
    return
  }
  // —— 真实接口 ——
  if (task.is_done) {
    await taskApi.uncheckin(task.id)
    ElMessage.info('已取消打卡')
  } else {
    await taskApi.checkin(task.id)
    ElMessage.success('打卡成功，继续加油！')
  }
  load()
}

const syncOverall = () => {
  const total = tasks.value.length
  const done = tasks.value.filter((t) => t.is_done).length
  overall.value = { total, done, rate: total ? done / total : 0 }
}

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    if (USE_MOCK) {
      const data = await mockOverview()
      exams.value = data.exams
      tasks.value = data.tasks
      extras.value = data.extras
      pressure.value = { ...mockPressure }
      mood.value = { ...mockMood }
      moodScore.value = mockMood.mood_score
      review.value = structuredClone(mockReview)
      top3.value = structuredClone(mockTop3)
      timeslots.value = structuredClone(mockTimeslots)
      // 预览态：番茄钟用本地假数据
      focusData.value = { total_minutes: 75, goal_minutes: 120, achieved: false, session_count: 3, by_exam: [] }
      goalInput.value = 120
      weekFocus.value = data.extras.focus_minutes
      syncOverall()
    } else {
      // —— 真实接口 ——
      const [overview, allTasks, pressureData, moodData, reviewData, top3Data, slotData] =
        await Promise.all([
          dashboardApi.overview(),
          taskApi.list(),
          featureApi.pressure(),
          featureApi.moodToday(),
          featureApi.review(),
          featureApi.top3(),
          featureApi.timeslots(),
        ])
      exams.value = overview.exams
      overall.value = overview.overall
      const examMap = Object.fromEntries(overview.exams.map((e) => [e.id, e.subject]))
      tasks.value = allTasks.map((t) => ({ ...t, exam: examMap[t.exam_id] || '未归类' }))
      // 连续打卡：截至今天连续有打卡任务的天数
      const doneTasks = tasks.value.filter((t) => t.is_done)
      const doneDays = new Set(doneTasks.map((t) => t.plan_date))
      const toLocal = (dt) =>
        `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
      let streak = 0
      const cursor = new Date()
      while (doneDays.has(toLocal(cursor))) {
        streak += 1
        cursor.setDate(cursor.getDate() - 1)
      }
      // 专注时长：取自番茄钟记录（学习时长统计的唯一依据）
      await loadFocus()
      extras.value = { streak, focus_minutes: weekFocus.value }
      pressure.value = pressureData
      mood.value = moodData
      moodScore.value = moodData?.mood_score || 0
      review.value = reviewData
      top3.value = top3Data
      timeslots.value = slotData
    }
    renderRing()
  } catch (e) {
    error.value = e?.message || '网络异常，请稍后重试'
  } finally {
    loading.value = false
  }
}

const renderRing = () => {
  if (!chartRef.value) return
  const done = overall.value.done || 0
  const total = overall.value.total || 0
  const remain = Math.max(total - done, 0)
  if (!chart) chart = echarts.init(chartRef.value)
  chart.setOption({
    series: [
      {
        type: 'pie',
        radius: ['68%', '86%'],
        center: ['50%', '50%'],
        silent: true, // 静态统计环，不需要悬浮层
        label: { show: false },
        itemStyle: { borderColor: '#f8f5ec', borderWidth: 3 },
        data:
          total === 0
            ? [{ value: 1, itemStyle: { color: RING_TRACK } }]
            : [
                { value: done, itemStyle: { color: '#e66348' } },
                { value: remain, itemStyle: { color: RING_TRACK } },
              ],
      },
    ],
  })
}

const onEmergency = async () => {
  emergencyVisible.value = true
  if (USE_MOCK) {
    emergency.value = structuredClone(mockEmergency)
    return
  }
  emergency.value = null
  try {
    emergency.value = await featureApi.emergency()
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const onMoodChange = async (val) => {
  if (!val) return
  if (USE_MOCK) {
    mood.value = { ...mockMood, mood_score: val }
    return
  }
  try {
    mood.value = await featureApi.submitMood({ mood_score: val })
    ElMessage.success('已记录今日情绪')
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const loadRelief = async () => {
  if (USE_MOCK) {
    relief.value = structuredClone(mockRelief[reliefOption.value])
    return
  }
  relief.value = null
  try {
    relief.value = await featureApi.relief({ option: reliefOption.value })
  } catch (e) {
    // request.js 已统一提示错误
  }
}

const onRelief = () => {
  reliefVisible.value = true
  reliefOption.value = 'lighten'
  loadRelief()
}

const pickRelief = (option) => {
  if (reliefOption.value === option) return
  reliefOption.value = option
  loadRelief()
}

const confirmRelief = async () => {
  if (USE_MOCK) {
    ElMessage.success('已按演示方案重排（预览态不落库）')
    reliefVisible.value = false
    return
  }
  try {
    await featureApi.reliefApply({ option: reliefOption.value })
    ElMessage.success('计划已按确认方案重排')
    reliefVisible.value = false
    await load()
  } catch (e) {
    // request.js 已统一提示错误
  }
}

// —— 番茄钟逻辑 ——
const loadFocus = async () => {
  const [today, sessions] = await Promise.all([focusApi.today(), focusApi.sessions()])
  focusData.value = today
  goalInput.value = today.goal_minutes || 60
  const cutoff = new Date()
  cutoff.setHours(0, 0, 0, 0)
  cutoff.setDate(cutoff.getDate() - 6)
  weekFocus.value = sessions
    .filter((s) => new Date(s.start_time) >= cutoff)
    .reduce((sum, s) => sum + s.duration_minutes, 0)
}

const onDurationChange = () => {
  if (!focusRunning.value) {
    focusStarted.value = false
    recordedMin.value = 0
    remainSec.value = focusMinutes.value * 60
  }
}

const tickFocus = () => {
  remainSec.value -= 1
  if (remainSec.value <= 0) finishFocus()
}

// 把本轮"自上次落盘以来"已专注的整分钟写入统计；不足 1 分钟不计。
// 暂停 / 重置 / 倒计时结束都走这里，靠 recordedMin 保证不重复计。
const flushFocus = async () => {
  const elapsedMin = Math.floor((focusMinutes.value * 60 - Math.max(remainSec.value, 0)) / 60)
  const pending = elapsedMin - recordedMin.value
  if (pending < 1) return 0
  recordedMin.value = elapsedMin

  if (USE_MOCK) {
    focusData.value.total_minutes += pending
    focusData.value.achieved =
      focusData.value.goal_minutes > 0 && focusData.value.total_minutes >= focusData.value.goal_minutes
    weekFocus.value += pending
    extras.value = { ...extras.value, focus_minutes: weekFocus.value }
    return pending
  }
  await focusApi.createSession({ exam_id: focusExamId.value, duration_minutes: pending })
  await loadFocus()
  extras.value = { ...extras.value, focus_minutes: weekFocus.value }
  return pending
}

const toggleFocus = async () => {
  if (focusRunning.value) {
    // 暂停：先把已专注的整分钟落盘
    focusRunning.value = false
    clearInterval(focusTimerId)
    focusTimerId = null
    const n = await flushFocus()
    ElMessage.info(n ? `已暂停，记录 ${n} 分钟专注` : '已暂停（不足 1 分钟，未计入）')
    return
  }
  if (!focusExamId.value) {
    ElMessage.warning('请先选择科目')
    return
  }
  focusRunning.value = true
  focusStarted.value = true
  focusTimerId = setInterval(tickFocus, 1000)
}

const resetFocus = async () => {
  focusRunning.value = false
  clearInterval(focusTimerId)
  focusTimerId = null
  const n = await flushFocus() // 已消耗 ≥1 分钟则记上
  focusStarted.value = false
  recordedMin.value = 0
  remainSec.value = focusMinutes.value * 60
  ElMessage.info(n ? `已重置，记录 ${n} 分钟专注` : '已重置')
}

const finishFocus = async () => {
  clearInterval(focusTimerId)
  focusTimerId = null
  focusRunning.value = false
  remainSec.value = 0 // 确保 elapsed 按整轮计算
  await flushFocus()
  focusStarted.value = false
  recordedMin.value = 0
  remainSec.value = focusMinutes.value * 60
  const tip = focusData.value.achieved ? '，今日目标已达成！' : '，继续加油！'
  ElMessage.success(`本轮专注结束，时长已计入统计${tip}`)
}

const saveGoal = async () => {
  if (USE_MOCK) {
    focusData.value.goal_minutes = goalInput.value
    ElMessage.success('目标已保存')
    return
  }
  await focusApi.setGoal({ target_minutes: goalInput.value })
  focusData.value = await focusApi.today()
  ElMessage.success('目标已保存')
}

const goStep = (to) => {
  if (to === '#board') {
    document.getElementById('board')?.scrollIntoView({ behavior: 'smooth' })
    return
  }
  router.push(to)
}

const onResize = () => chart?.resize()

onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  clearInterval(focusTimerId)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
/* -- 压力指数（模块 7.1） -- */
.pressure {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 24px;
}

.pressure.alert {
  border-color: var(--coral-deep);
  box-shadow: 4px 4px 0 var(--coral);
}

.pressure-main { flex: 1; min-width: 0; }
.pressure-score { display: flex; align-items: baseline; gap: 10px; }

.ps-num {
  font-family: var(--font-num);
  font-size: 34px;
  font-weight: 700;
  color: var(--ink-1);
  font-variant-numeric: tabular-nums;
}

.ps-label { font-size: 13px; font-weight: 700; color: var(--ink-2); }

.pressure-bar {
  margin: 10px 0 8px;
  height: 10px;
  background: var(--bg-soft);
  border: 1.5px solid var(--ink-1);
  border-radius: 6px;
  overflow: hidden;
}

.pb-fill {
  height: 100%;
  background: var(--green);
  transition: width 0.4s ease;
}

.pressure.alert .pb-fill { background: var(--coral); }
.pressure-tip { margin: 0; font-size: 13px; color: var(--ink-3); }

/* -- 临时救急模式（模块 7.2） -- */
.eg-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1.5px solid var(--ink-1);
}
.eg-subject {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 900;
  color: var(--ink-1);
}
.eg-meta { font-size: 12px; color: var(--ink-3); }
.eg-note {
  margin: 16px 0 0;
  padding: 12px 14px;
  background: var(--bg-soft);
  border: 1.5px dashed var(--ink-1);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--ink-2);
  text-align: center;
}
.eg-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  max-height: 52vh;
  overflow-y: auto;
}
.eg-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px dashed var(--bg-soft);
}
.eg-item:last-child { border-bottom: none; }
.eg-idx {
  flex: none;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--ink-1);
  color: var(--bg-card);
  font-family: var(--font-num);
  font-size: 12px;
  font-weight: 700;
}
.eg-body { flex: 1; min-width: 0; }
.eg-line { display: flex; align-items: baseline; gap: 8px; }
.eg-kind {
  flex: none;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
}
.eg-kind.focus { background: var(--coral-soft); color: var(--coral-deep); }
.eg-kind.kp { background: var(--bg-soft); color: var(--ink-2); }
.eg-content { font-size: 14px; font-weight: 600; color: var(--ink-1); }
.eg-basis { margin-top: 3px; font-size: 12px; color: var(--ink-3); }
.eg-weight {
  flex: none;
  font-family: var(--font-num);
  font-size: 12px;
  color: var(--ink-2);
}
.eg-loading { padding: 28px 0; text-align: center; color: var(--ink-3); font-size: 13px; }

/* —— 情绪记录（模块 7.6） —— */
.mood {
  margin-top: 16px;
}

.mood-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}

.mood-pick {
  display: flex;
  align-items: center;
  gap: 14px;
}

.mood-hint {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-2);
}

.mood-result {
  display: flex;
  align-items: center;
  gap: 18px;
  background: var(--bg-soft);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-md);
  padding: 12px 18px;
}

.mood-result.low {
  background: var(--red-soft);
  border-color: var(--coral-deep);
}

.mood-score { display: flex; align-items: baseline; gap: 8px; }

.ms-num {
  font-family: var(--font-num);
  font-size: 28px;
  font-weight: 700;
  color: var(--ink-1);
  font-variant-numeric: tabular-nums;
}

.ms-label { font-size: 12px; color: var(--ink-3); }
.mood-tip { margin: 0; font-size: 13px; color: var(--ink-2); }

@media (max-width: 992px) {
  .mood-body { flex-direction: column; align-items: stretch; }
}

/* -- 考前重点回顾（模块 7.3） -- */
.review {
  margin-top: 16px;
}

.rv-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.rv-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--bg-soft);
}
.rv-item:last-child { border-bottom: none; }

.rv-idx {
  flex: none;
  width: 20px;
  text-align: center;
  font-family: var(--font-num);
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-3);
}

.rv-name {
  flex: none;
  width: 38%;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-1);
}

.rv-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-soft);
  border-radius: 4px;
  overflow: hidden;
}
.rv-fill {
  height: 100%;
  background: var(--coral);
  border-radius: 4px;
  transition: width 0.4s ease;
}

.rv-weight {
  flex: none;
  width: 44px;
  text-align: right;
  font-family: var(--font-num);
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-2);
}

.rv-hours {
  flex: none;
  width: 72px;
  text-align: right;
  font-size: 12px;
  color: var(--ink-3);
}

/* -- 今日最重要的三件事（模块 7.4） -- */
.top3 {
  margin-top: 16px;
}

.t3-note {
  margin: 0;
  padding: 12px 0;
  text-align: center;
  font-size: 13px;
  color: var(--ink-3);
}

.t3-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.t3-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  background: var(--bg-soft);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-md);
}

.t3-item.first {
  background: var(--coral-soft);
  box-shadow: 3px 3px 0 var(--coral);
}

.t3-rank {
  flex: none;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--ink-1);
  color: var(--bg-card);
  font-family: var(--font-num);
  font-size: 14px;
  font-weight: 700;
}

.t3-item.first .t3-rank { background: var(--coral); }

.t3-body { flex: 1; min-width: 0; }
.t3-title { font-size: 14px; font-weight: 700; color: var(--ink-1); }

.t3-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
}

.t3-subject {
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--bg-card);
  border: 1px solid var(--ink-1);
  font-size: 11px;
  color: var(--ink-2);
}

.t3-reason { font-size: 12px; color: var(--ink-3); }

.t3-min {
  flex: none;
  font-family: var(--font-num);
  font-size: 12px;
  color: var(--ink-2);
}

@media (max-width: 992px) {
  .t3-item { flex-wrap: wrap; }
}

/* -- 学习时段推荐（模块 7.5） -- */
.timeslots {
  margin-top: 16px;
}

.ts-note {
  margin: 0 0 14px;
  padding: 10px 14px;
  background: var(--bg-soft);
  border: 1.5px dashed var(--ink-1);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--ink-3);
  text-align: center;
}

.ts-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.ts-card {
  padding: 14px 16px;
  background: var(--bg-soft);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-md);
}

.ts-name {
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 900;
  color: var(--ink-1);
}

.ts-time {
  margin-top: 2px;
  font-family: var(--font-num);
  font-size: 12px;
  color: var(--ink-3);
}

.ts-min {
  margin-top: 8px;
  font-family: var(--font-num);
  font-size: 20px;
  font-weight: 700;
  color: var(--coral-deep);
}

.ts-focus {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-2);
}

@media (max-width: 992px) {
  .ts-grid { grid-template-columns: repeat(2, 1fr); }
}

/* -- 低情绪减负（模块 7.7） -- */
.rf-opts {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.rf-cap {
  margin-left: auto;
  font-size: 12px;
  color: var(--ink-3);
}
.rf-body { margin-top: 16px; }
.rf-summary {
  margin: 0;
  padding: 10px 14px;
  background: var(--bg-soft);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-1);
}
.rf-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  max-height: 34vh;
  overflow-y: auto;
}
.rf-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--bg-soft);
  font-size: 13px;
}
.rf-item:last-child { border-bottom: none; }
.rf-title { color: var(--ink-1); font-weight: 600; }
.rf-dates {
  flex: none;
  font-family: var(--font-num);
  font-size: 12px;
  color: var(--coral-deep);
}
.rf-conflicts {
  margin-top: 12px;
  padding: 10px 14px;
  background: var(--red-soft);
  border: 1.5px solid var(--coral-deep);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--ink-2);
}
.rf-conf-head { font-weight: 700; color: var(--coral-deep); margin-bottom: 4px; }
.rf-conflicts ul { margin: 0; padding-left: 18px; }
.rf-loading { padding: 28px 0; text-align: center; color: var(--ink-3); font-size: 13px; }

/* —— 通用面板（纸片 + 墨线 + 硬阴影） —— */
.panel {
  background: var(--bg-card);
  border: 2px solid var(--ink-1);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-ink-xs);
  padding: 22px 24px;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  font-size: 13px;
  color: var(--ink-3);
}

/* 入场动画 */
.rise {
  animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: var(--d, 0ms);
}
@keyframes rise {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: none; }
}

/* —— 骨架屏 —— */
.sk-hero,
.sk-tile,
.sk-main,
.sk-side {
  background: var(--bg-card);
  border: 2px solid var(--line-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-ink-xs);
}
.sk-hero { padding: 36px 40px; }
.sk-flex { display: flex; gap: 40px; justify-content: space-between; align-items: center; }
.sk-col { flex: 1; max-width: 520px; display: flex; flex-direction: column; gap: 12px; }
.sk-tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 16px 0; }
.sk-tile { padding: 20px; }
.sk-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-top: 16px; }
.sk-main, .sk-side { padding: 22px 24px; margin-top: 16px; }

/* —— Hero：墨面板 + 巨型倒计时（首页视觉冲击区） —— */
.hero {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: var(--ink-1);
  border: 2px solid var(--ink-1);
  box-shadow: 6px 6px 0 var(--coral);
}
/* 面板内侧巨型水印字 */
.hero::after {
  content: '冲刺';
  position: absolute;
  right: 170px;
  top: 50%;
  transform: translateY(-50%);
  font-family: var(--font-serif);
  font-weight: 900;
  font-size: 210px;
  line-height: 1;
  color: rgba(240, 237, 227, 0.045);
  pointer-events: none;
  user-select: none;
}
.hero-inner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  padding: 46px 48px;
}
.hero-kicker {
  margin: 0 0 18px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: var(--coral-bright);
}
.hero-title {
  font-family: var(--font-serif);
  font-size: 36px;
  line-height: 1.5;
  font-weight: 900;
  letter-spacing: 0.02em;
  color: var(--bg-page);
  margin: 0;
}
.coral-text {
  color: var(--coral-bright);
}
.hero-sub {
  margin: 18px 0 0;
  font-size: 14px;
  line-height: 1.9;
  color: rgba(240, 237, 227, 0.62);
  max-width: 480px;
}
.hero-actions {
  display: flex;
  gap: 14px;
  margin-top: 28px;
}
/* 墨底上的按钮：纸色描边 + 纸色硬阴影 */
.hero-actions :deep(.el-button--primary) {
  border-color: var(--bg-page);
  box-shadow: 2px 2px 0 var(--bg-page);
}
.hero-actions :deep(.el-button--primary:hover) {
  box-shadow: 3px 3px 0 var(--bg-page);
}
.ghost-btn {
  border: 1.5px solid rgba(240, 237, 227, 0.55);
  color: var(--bg-page);
  background: transparent;
}
.ghost-btn:hover {
  border-color: var(--coral-bright);
  color: var(--coral-bright);
}
.hero-right {
  flex-shrink: 0;
}
.hero-ring {
  position: relative;
  width: 210px;
  height: 210px;
  border-radius: 50%;
  background: conic-gradient(var(--coral) calc(var(--p, 36) * 1%), rgba(240, 237, 227, 0.13) 0);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 34px), #000 calc(100% - 33px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 34px), #000 calc(100% - 33px));
  display: grid;
  place-items: center;
}
.hero-ring-in {
  position: absolute;
  text-align: center;
}
.hr-num {
  display: block;
  font-size: 78px;
  font-weight: 700;
  color: var(--bg-page);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}
.hr-num.text {
  font-family: var(--font-serif);
  font-size: 34px;
  font-weight: 900;
  letter-spacing: 0.04em;
}
.hr-label {
  display: block;
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: rgba(240, 237, 227, 0.6);
}

/* —— 流程引导 —— */
.flow {
  margin-top: 16px;
}
.flow-steps {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.flow-step {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-soft);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-md);
  padding: 15px;
  cursor: pointer;
  transition: all 0.18s;
}
.flow-step:hover {
  background: var(--bg-card);
  box-shadow: var(--shadow-ink-sm);
  transform: translate(-1px, -1px);
}
.flow-step:active {
  transform: translate(2px, 2px);
  box-shadow: 0 0 0 var(--ink-1);
}
.step-icon {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: var(--coral-soft);
  color: var(--coral-deep);
  border: 1.5px solid var(--ink-1);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.step-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.step-name {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--ink-1);
  white-space: nowrap;
}
.step-desc {
  font-size: 12px;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* —— 数据总览（高信息密度聚合面板） —— */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 16px 0;
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
  font-family: var(--font-num);
  font-size: 23px;
  font-weight: 700;
  color: var(--ink-1);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.stat-label {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
}
.stat-sub {
  font-size: 11px;
  color: var(--ink-3);
}

/* —— 考表时间线（印刷风虚线 + 菱形节点） —— */
.timeline {
  position: relative;
  padding-left: 24px;
}
.timeline::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 10px;
  bottom: 10px;
  border-left: 2px dashed var(--line-strong);
}
.tl-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 12px 0;
}
.tl-item:last-child {
  padding-bottom: 2px;
}
.tl-node {
  position: absolute;
  left: -25px;
  top: 18px;
  width: 11px;
  height: 11px;
  background: var(--coral);
  border: 1.5px solid var(--ink-1);
  transform: rotate(45deg);
}
.tl-node.urgent {
  background: var(--red);
}
.tl-date {
  width: 62px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 2px;
}
.tl-md {
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-1);
}
.tl-week {
  font-size: 11px;
  color: var(--ink-3);
}
.tl-body {
  flex: 1;
  min-width: 0;
}
.tl-subject {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-1);
}
.tl-dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 1.5px solid var(--ink-1);
  margin-right: 7px;
  vertical-align: 1px;
}
.tl-meta {
  margin-top: 3px;
  font-size: 12px;
  color: var(--ink-3);
}
.tl-bar {
  margin-top: 8px;
  max-width: 240px;
}
.tl-cta {
  display: inline-block;
  margin-top: 8px;
  font-size: 12px;
  color: var(--coral-deep);
  text-decoration: none;
}
.tl-cta:hover {
  text-decoration: underline;
}
.tl-count {
  flex-shrink: 0;
  text-align: center;
  background: var(--coral-soft);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-ink-xs);
  padding: 7px 13px;
  min-width: 64px;
}
.tl-count.urgent {
  background: var(--red-soft);
}
.tl-days {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--coral-deep);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.tl-days.text {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 900;
  padding: 4px 0;
}
.tl-count.urgent .tl-days {
  color: var(--red);
}
.tl-unit {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  color: var(--ink-3);
}

/* —— 任务看板 —— */
.board-cols {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.col-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.col-dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
}
.col-name {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--ink-1);
}
.col-count {
  font-size: 12px;
  font-weight: 700;
  border-radius: 4px;
  border: 1px solid var(--line-strong);
  padding: 0 8px;
}
.col-body {
  background: var(--bg-soft);
  border: 1.5px solid var(--line);
  border-radius: var(--radius-md);
  padding: 12px;
  min-height: 190px;
}
.task-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: var(--bg-card);
  border: 1.5px solid var(--ink-1);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  margin-bottom: 10px;
  transition: all 0.15s;
}
.task-card:last-child {
  margin-bottom: 0;
}
.task-card:hover {
  box-shadow: var(--shadow-ink-sm);
  transform: translate(-1px, -1px);
}
.task-card.done {
  opacity: 0.66;
}
.task-card.done .task-title {
  text-decoration: line-through;
  color: var(--ink-3);
}
.task-check {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  background: var(--coral);
  color: #fff;
  border: 1.5px solid var(--ink-1);
  display: grid;
  place-items: center;
  margin-top: 2px;
  flex-shrink: 0;
}
.task-body {
  flex: 1;
  min-width: 0;
}
.task-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink-1);
  line-height: 1.5;
}
.task-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 7px;
}
.task-exam,
.task-min,
.task-date {
  font-size: 11.5px;
  color: var(--ink-3);
}
.task-date.overdue {
  color: var(--amber);
  font-weight: 600;
}
.undo {
  color: var(--ink-3);
  font-size: 12px;
  flex-shrink: 0;
}
.undo:hover {
  color: var(--coral-deep);
}
.col-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 44px 0;
}
.ce-icon {
  color: var(--ink-3);
}
.ce-text {
  font-size: 12.5px;
  color: var(--ink-3);
}

/* —— 进度环 —— */
.ring-wrap {
  position: relative;
}
.ring-chart {
  width: 100%;
  height: 210px;
}
.ring-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
}
.ring-pct {
  display: block;
  font-family: var(--font-num);
  font-size: 32px;
  font-weight: 700;
  color: var(--ink-1);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.ring-sub {
  display: block;
  font-size: 12px;
  color: var(--ink-3);
}
.ring-legend {
  display: flex;
  justify-content: center;
  gap: 22px;
  font-size: 12px;
  color: var(--ink-2);
}
.lg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.lg-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.lg-dot.done {
  background: var(--coral);
}
.lg-dot.remain {
  background: #e4dfd0;
  border: 1px solid #cfc9b8;
}

/* —— 连续打卡 —— */
.streak-panel {
  margin-top: 16px;
}
.streak-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.streak-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--coral-soft);
  color: var(--coral-deep);
  border: 1.5px solid var(--ink-1);
  display: grid;
  place-items: center;
}
.streak-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-1);
}
.streak-sub {
  font-size: 12px;
  color: var(--ink-3);
  margin-top: 2px;
}
.week-dots {
  display: flex;
  justify-content: space-between;
}
.week-dot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.dot-i {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--bg-soft);
  color: var(--ink-3);
  border: 1.5px solid var(--line);
  font-size: 13px;
  font-weight: 700;
  display: grid;
  place-items: center;
}
.week-dot.on .dot-i {
  background: var(--coral);
  border-color: var(--ink-1);
  color: #fff;
}
.week-dot.today .dot-i {
  outline: 2px solid var(--coral);
  outline-offset: 2px;
}
.dot-label {
  font-size: 11px;
  color: var(--ink-3);
}

/* —— 番茄钟 —— */
.focus-panel {
  margin-top: 16px;
}
.focus-setup {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}
.focus-setup .el-select {
  flex: 1;
}
.focus-clock {
  font-family: var(--font-num);
  font-size: 52px;
  font-weight: 700;
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
  text-align: center;
  color: var(--ink-1);
  line-height: 1;
  padding: 8px 0 14px;
}
.focus-clock.running {
  color: var(--coral-deep);
}
.focus-tip {
  text-align: center;
  font-size: 12px;
  color: var(--ink-3);
  margin: -6px 0 12px;
}
.focus-tip a {
  color: var(--coral-deep);
  font-weight: 700;
}
.focus-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-bottom: 18px;
}
.focus-goal {
  border-top: 1.5px dashed var(--line);
  padding-top: 14px;
}
.fg-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.fg-label {
  font-size: 13px;
  color: var(--ink-2);
}
.fg-num {
  font-family: var(--font-num);
  font-size: 18px;
  font-weight: 700;
  color: var(--ink-1);
}
.fg-num em {
  font-style: normal;
  font-size: 12px;
  font-weight: 400;
  color: var(--ink-3);
}
.fg-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--green);
  border-radius: 10px;
  padding: 2px 9px;
}
.fg-set {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.fg-hint {
  font-size: 12px;
  color: var(--ink-3);
}
.fg-set .el-input-number {
  width: 110px;
}

/* —— 空状态 / 错误 —— */
.empty-box {
  text-align: center;
  padding: 40px 0 30px;
}
.empty-icon {
  display: inline-grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: var(--bg-soft);
  color: var(--ink-3);
  border: 1.5px solid var(--line-strong);
}
.empty-title {
  margin-top: 14px;
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-1);
}
.empty-sub {
  margin: 5px 0 18px;
  font-size: 13px;
  color: var(--ink-3);
}
.error-box {
  padding: 24px;
}

/* —— 响应式 —— */
@media (max-width: 992px) {
  .hero-inner {
    flex-direction: column;
    align-items: flex-start;
  }
  .hero-right {
    display: none;
  }
  .flow-steps {
    grid-template-columns: repeat(2, 1fr);
  }
  .stats,
  .sk-tiles {
    grid-template-columns: repeat(2, 1fr);
  }
  .sk-grid {
    grid-template-columns: 1fr;
  }
  .board-cols {
    grid-template-columns: 1fr;
  }
  .el-col {
    margin-bottom: 16px;
  }
}
</style>
