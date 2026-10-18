<template>
  <div class="dash">
    <div class="desk-heading">
      <div>
        <p class="eyebrow">
          你的期末复习工作台 <span class="edition">STUDY / DAILY</span>
        </p>
        <p class="desk-date">
          {{ todayText }}
          <span v-if="USE_MOCK">· 演示日期 {{ getToday() }}</span>
        </p>
      </div>
      <div class="desk-utilities">
        <el-select
          v-if="USE_MOCK"
          v-model="mockScenario"
          aria-label="演示场景"
          @change="changeScenario"
          size="small"
          class="scenario-picker"
          ><el-option label="日常复习" value="normal" /><el-option
            label="多任务 · 40 项"
            value="busy" /><el-option label="新用户" value="new" /></el-select>
        <el-button :loading="refreshing" :disabled="loading" text @click="load"
          ><el-icon><Refresh /></el-icon>&nbsp;刷新数据</el-button
        >
      </div>
    </div>
    <aside class="home-notices" aria-label="站内提醒">
      <div>
        <strong>{{ notices.error || (notices.loading ? '正在检查提醒' : notices.unread ? `${notices.unread} 条未读提醒` : '当前没有未读通知') }}</strong>
        <p v-if="!notices.error">{{ notices.unread ? notices.preview.map(n => n.title).join('；') : notices.enabled ? '查看通知历史，或为考试与复习任务设置提醒。' : '提醒已暂停，可在通知中心重新开启。' }}</p>
      </div>
      <el-button v-if="notices.error" text @click="notices.refresh()">重试</el-button>
      <router-link to="/notifications">{{ notices.unread ? '查看通知 ↗' : '打开通知中心 ↗' }}</router-link>
    </aside>
    <div v-if="loading" class="loading-desk" aria-label="正在加载学习进度">
      <el-skeleton :rows="8" animated />
    </div>
    <div v-else-if="error" class="panel">
      <el-result icon="warning" title="学习数据暂时无法加载" :sub-title="error"
        ><template #extra
          ><el-button type="primary" @click="load"
            >重新加载</el-button
          ></template
        ></el-result
      >
    </div>
    <template v-else>
      <section class="hero rise">
        <div class="hero-copy">
          <p class="hero-kicker">
            <span class="live-dot"></span>{{ greeting }}，{{
              userStore.displayName
            }}
          </p>
          <h1 tabindex="-1">期末有计划，<br /><span>今天不慌张。</span></h1>
          <p class="hero-sub">{{ heroMessage }}</p>
          <div class="hero-actions">
            <el-button
              type="primary"
              size="large"
              @click="goStep(overall.total ? '#board' : '/analysis')"
              >{{ overall.total ? '开始今日复习' : '生成我的复习计划'
              }}<el-icon class="action-arrow"><Right /></el-icon
            ></el-button>
            <router-link to="/materials" class="hero-link"
              >上传复习资料 <el-icon><TopRight /></el-icon
            ></router-link>
          </div>
          <div class="cover-progress">
            <ProgressRing :value="overall.rate * 100" label="全部科目复习总进度"
              ><strong
                >{{ Math.round(overall.rate * 100) }}<small>%</small></strong
              ></ProgressRing
            ><span
              ><b>所有科目，一起向前</b
              ><small
                >已完成 {{ overall.done }} /
                {{ overall.total }} 个复习任务</small
              ></span
            >
          </div>
        </div>
        <div class="exam-ticket">
          <div class="ticket-top">
            <span>下一场考试</span
            ><span class="ticket-no">{{
              nearestExam ? '01 / ' + upcomingExams.length : '— / —'
            }}</span>
          </div>
          <div v-if="nearestExam" class="ticket-count">
            <strong>{{
              nearestExam.days_left === 0
                ? '今天'
                : String(nearestExam.days_left).padStart(2, '0')
            }}</strong
            ><span>{{
              nearestExam.days_left === 0 ? '从容应考' : '天后开考'
            }}</span>
          </div>
          <div v-else class="ticket-empty">
            <el-icon :size="36"><Calendar /></el-icon
            ><span>给下一场考试<br />留一个位置</span>
          </div>
          <div class="ticket-bottom">
            <b>{{ nearestExam?.subject || '还没有近期考试' }}</b
            ><span>{{
              nearestExam
                ? fmtMd(nearestExam.exam_date) +
                  ' · ' +
                  (nearestExam.location || '地点待补充')
                : '录入考试，开启备考倒计时'
            }}</span
            ><router-link to="/exams"
              >{{
                nearestExam ? '查看考试安排' : '录入我的考试'
              }}
              ↗</router-link
            >
          </div>
          <span
            class="ticket-stamp"
            v-if="nearestExam && nearestExam.days_left <= 7"
            >本周重点</span
          >
        </div>
      </section>

      <section class="metrics rise" aria-label="学习数据总览">
        <router-link
          v-for="(s, i) in statTiles"
          :key="s.label"
          :to="s.to"
          class="metric"
        >
          <span class="metric-label"
            ><span class="metric-index">0{{ i + 1 }}</span
            >{{ s.label }}<el-icon><TopRight /></el-icon
          ></span>
          <strong>{{ s.value }}</strong
          ><span class="metric-sub">{{ s.sub }}</span>
        </router-link>
      </section>
      <p v-if="featureWarning" class="inline-warning" role="status">
        {{ featureWarning
        }}<el-button text size="small" @click="refreshFeatures">重试</el-button>
      </p>
      <StudyWorkspace
        :style="{ '--workspace-offset': workspaceOffset + 'px' }"
        :tasks="tasks"
        :exams="exams"
        :priorities="top3?.items || []"
        :today="getToday()"
        :history="history"
        :focus="focusData"
        :budget="dailyBudget"
        :selected="selectedTask"
        :pending-ids="pendingIds"
        :running="focusRunning"
        :clock="clockText"
        @select="selectTask"
        @start="startTask"
        @toggle="onToggle"
        @budget="openPlanning"
        @enter="goStep('#board')"
      >
        <template #focus>
          <section class="panel focus-panel workspace-focus">
            <div class="section-head" data-tour="focus">
              <h2>番茄钟</h2>
              <span class="focus-status">{{
                focusRunning ? '专注中' : focusStarted ? '已暂停' : '准备开始'
              }}</span>
            </div>
            <div class="focus-setup">
              <el-select
                v-model="focusExamId"
                aria-label="专注科目"
                @change="onFocusExamChange"
                placeholder="选择科目"
                :disabled="focusStarted"
                ><el-option
                  v-for="e in sortedExams"
                  :key="e.id"
                  :label="e.subject"
                  :value="e.id" /></el-select
              ><el-select
                v-model="focusMinutes"
                aria-label="专注时长"
                :disabled="focusStarted"
                @change="onDurationChange"
                ><el-option
                  v-for="m in FOCUS_PRESETS"
                  :key="m"
                  :label="`${m} 分钟`"
                  :value="m"
              /></el-select>
            </div>
            <div class="focus-clock" :class="{ running: focusRunning }">
              {{ clockText }}
            </div>
            <p v-if="!exams.length" class="focus-hint">
              先<router-link to="/exams">录入考试科目</router-link
              >，再开始专注。
            </p>
            <div class="focus-actions">
              <el-button
                type="primary"
                :disabled="!focusExamId || focusSaving"
                :loading="focusSaving"
                @click="toggleFocus"
                ><el-icon
                  ><component
                    :is="focusRunning ? 'VideoPause' : 'VideoPlay'" /></el-icon
                >&nbsp;{{
                  focusRunning ? '暂停' : focusStarted ? '继续专注' : '开始专注'
                }}</el-button
              ><el-button :disabled="focusSaving" @click="resetFocus"
                >结束本轮</el-button
              >
            </div>
            <div class="focus-goal">
              <div class="goal-line">
                <span
                  >今日专注 <b>{{ focusData.total_minutes }}</b
                  ><small>
                    / {{ focusData.goal_minutes || '未设目标'
                    }}{{ focusData.goal_minutes ? ' 分钟' : '' }}</small
                  ></span
                ><span v-if="focusData.achieved" class="achieved">已达标</span>
              </div>
              <el-progress
                :percentage="goalPct"
                :show-text="false"
                :stroke-width="5"
                color="#35554c"
              />
            </div>
          </section>
        </template>
      </StudyWorkspace>
      <section class="care-section" aria-labelledby="care-heading">
        <header class="care-heading">
          <h2 id="care-heading">情绪记录与减负</h2>
          <small>{{
            pressure
              ? `当前压力 ${pressure.score} · ${pressure.level}`
              : '状态记录、救急与减负'
          }}</small>
        </header>
        <div class="care-grid">
          <section
            v-if="pressure"
            class="panel pressure"
            :class="{ alert: pressure.need_emergency }"
          >
            <div class="section-head">
              <div>
                <p class="eyebrow">节奏比焦虑更重要</p>
                <h2>备考压力观察</h2>
              </div>
              <span class="pressure-level">{{ pressure.level }}</span>
            </div>
            <div class="pressure-reading">
              <strong>{{ pressure.score }}<small>/ 100</small></strong
              ><span>{{ pressure.suggestion }}</span>
            </div>
            <div
              class="pressure-scale"
              role="meter"
              aria-label="备考压力指数"
              :aria-valuenow="pressure.score"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <i :style="{ width: pressure.score + '%' }"></i>
            </div>
            <div class="pressure-labels">
              <span>轻松</span><span>适中</span><span>偏压</span
              ><span>高压</span>
            </div>
            <el-button text type="primary" @click="onEmergency"
              >时间紧张？查看救急清单 <el-icon><Right /></el-icon
            ></el-button>
          </section>
          <section class="panel mood">
            <div class="section-head">
              <div>
                <p class="eyebrow">也照顾一下自己</p>
                <h2>今天的状态怎么样？</h2>
              </div>
              <span class="mood-word">{{ moodHint }}</span>
            </div>
            <el-rate
              v-model="moodScore"
              :max="5"
              size="large"
              :disabled="moodSaving"
              aria-label="今日心情，1 到 5 分"
              @change="onMoodChange"
            />
            <p class="mood-explain">
              {{
                mood?.suggestion ||
                '记录 1～5 分的心情，结合复习情况获得节奏建议。'
              }}
            </p>
            <div class="mood-bottom">
              <span v-if="mood"
                >综合评分 <b class="num">{{ mood.composite_score }}</b> /
                5</span
              ><el-button
                v-if="mood?.need_relief"
                type="primary"
                plain
                size="small"
                @click="onRelief"
                >减轻今日负担</el-button
              >
            </div>
          </section>
        </div>
      </section>
      <section class="panel exam-panel">
        <div class="section-head">
          <div>
            <p class="eyebrow">把时间看清楚</p>
            <h2>考试时间线</h2>
          </div>
          <router-link to="/exams" class="text-link">全部考试 ↗</router-link>
        </div>
        <div v-if="!sortedExams.length" class="quiet-empty">
          还没有考试安排，<router-link to="/exams">去录入第一门考试</router-link
          >。
        </div>
        <div v-else class="exam-timeline">
          <article
            v-for="e in examProgress"
            :key="e.id"
            :class="{
              urgent: e.days_left >= 0 && e.days_left <= 7,
              past: e.days_left < 0,
            }"
          >
            <div class="exam-date">
              <b>{{ fmtMd(e.exam_date) }}</b
              ><span>{{ weekOf(e.exam_date) }}</span>
            </div>
            <div class="exam-info">
              <b
                ><i :style="{ background: colorFor(e.id).color }"></i
                >{{ e.subject }}</b
              >
              <p>
                {{ e.location || '地点待补充' }} · {{ e.duration_minutes }} 分钟
              </p>
              <span v-if="e.total_tasks"
                >复习任务 {{ e.done_tasks }}/{{ e.total_tasks }}</span
              ><router-link
                v-else-if="e.days_left >= 0"
                :to="{ path: '/analysis', query: { exam: e.id } }"
                >生成这门课的计划 ↗</router-link
              >
            </div>
            <div class="exam-days">
              <strong>{{
                e.days_left < 0
                  ? '已结束'
                  : e.days_left === 0
                    ? '今天'
                    : e.days_left
              }}</strong
              ><span v-if="e.days_left > 0">天后开考</span>
            </div>
          </article>
        </div>
      </section>
      <p v-if="USE_MOCK" class="demo-note">
        当前为交互演示 · 数据不会保存到服务器，刷新后恢复示例。
      </p>
      <section class="guide-replay" aria-label="重新查看教程">
        <div><h2>需要再熟悉一下复习流程？</h2><p>从录入考试到每天专注，随时可以重新走一遍。</p></div>
        <el-button @click="startGuide">重新查看新手教程 <span aria-hidden="true">↗</span></el-button>
      </section>
      <el-dialog
        v-model="planningVisible"
        title="全科时间与排程"
        width="660px"
        align-center
        class="planning-dialog"
      >
        <p class="planning-intro">
          每天的可用时间由所有科目共享。先保存预算，再预览如何安排未完成的 AI
          任务；手动任务与完成记录会保留。
        </p>
        <div class="budget-editor">
          <label for="daily-budget">每天可用</label
          ><el-input-number
            id="daily-budget"
            v-model="budgetHours"
            :min="0.5"
            :max="16"
            :step="0.5"
            aria-label="全科每日可用小时数"
          /><span>小时</span
          ><el-button :loading="planningBusy" @click="saveBudget"
            >保存预算</el-button
          >
        </div>
        <p class="budget-note">
          保存后，今日专注目标也设为这个时长；任务日期需确认重排后才会改变。
        </p>
        <el-button type="primary" :loading="planningBusy" @click="previewPlan"
          >预览全科排程</el-button
        >
        <div v-if="planPreview" class="plan-preview">
          <div
            v-if="planPreview.conflicts.length"
            class="plan-conflicts"
            role="alert"
          >
            <b>还有任务排不下，暂不能确认</b>
            <ul>
              <li v-for="(issue, i) in planPreview.conflicts" :key="i">
                {{ issue.title || issue.date }}：{{ issue.reason }}（{{
                  issue.minutes
                }}
                分钟）
              </li>
            </ul>
          </div>
          <p v-else>
            全部任务可以在考试前安排，每天合计不超过
            {{ planPreview.daily_minutes }} 分钟。
          </p>
          <div class="preview-scroll">
            <table>
              <thead>
                <tr>
                  <th>日期</th>
                  <th>全科计划</th>
                  <th>各科分配</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="day in planPreview.days" :key="day.date">
                  <td>{{ day.date }}</td>
                  <td>{{ day.minutes }} 分钟</td>
                  <td>{{ planDaySubjects(day.date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <router-link
            v-if="planPreview.conflicts.length"
            to="/exams"
            @click="planningVisible = false"
            >去课程管理调整任务 ↗</router-link
          >
        </div>
        <template #footer
          ><el-button @click="planningVisible = false">取消</el-button
          ><el-button
            type="primary"
            :loading="planningBusy"
            :disabled="!planPreview || !!planPreview.conflicts.length"
            @click="confirmPlan"
            >确认全科重排</el-button
          ></template
        >
      </el-dialog>
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
            <span class="eg-meta"
              >距考试 {{ emergency.days_left }} 天 ·
              {{ emergency.exam_date }}</span
            >
          </div>
          <p v-if="emergency.note" class="eg-note">{{ emergency.note }}</p>
          <ul v-else class="eg-list">
            <li v-for="(it, i) in emergency.items" :key="i" class="eg-item">
              <span class="eg-idx">{{ i + 1 }}</span>
              <div class="eg-body">
                <div class="eg-line">
                  <span
                    class="eg-kind"
                    :class="it.kind === '考点' ? 'focus' : 'kp'"
                    >{{ it.kind }}</span
                  >
                  <span class="eg-content">{{ it.content }}</span>
                </div>
                <div v-if="it.basis" class="eg-basis">{{ it.basis }}</div>
              </div>
              <span v-if="it.weight != null" class="eg-weight"
                >权重 {{ it.weight }}</span
              >
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
            <el-button
              :type="reliefOption === 'lighten' ? 'primary' : 'default'"
              round
              @click="pickRelief('lighten')"
            >
              减轻当日任务
            </el-button>
            <el-button
              :type="reliefOption === 'halfday' ? 'primary' : 'default'"
              round
              @click="pickRelief('halfday')"
            >
              暂停半天
            </el-button>
            <span class="rf-cap"
              >重排后今日可用
              {{ relief ? relief.today_capacity : '—' }} 分钟</span
            >
          </div>
          <div v-if="relief" class="rf-body">
            <p class="rf-summary">{{ relief.summary }}</p>
            <ul v-if="relief.moves.length" class="rf-list">
              <li v-for="m in relief.moves" :key="m.task_id" class="rf-item">
                <span class="rf-title">{{ m.title }}</span>
                <span class="rf-dates"
                  >{{ m.from_date }} → {{ m.to_date }}</span
                >
              </li>
            </ul>
            <div v-if="relief.conflicts.length" class="rf-conflicts">
              <div class="rf-conf-head">以下任务考前排不下，需要取舍：</div>
              <ul>
                <li v-for="c in relief.conflicts" :key="c.task_id">
                  {{ c.title }} —— {{ c.reason }}
                </li>
              </ul>
            </div>
          </div>
          <div v-else class="rf-loading">加载中…</div>
        </div>
        <template #footer>
          <el-button @click="reliefVisible = false">取消</el-button>
          <el-button
            type="primary"
            :disabled="!relief || !!relief.conflicts.length"
            @click="confirmRelief"
            >确认调整</el-button
          >
        </template>
      </el-dialog>
    </template>
    <OnboardingTour v-model="guideVisible" @closed="finishGuide" />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import ProgressRing from '../components/ProgressRing.vue'
import StudyWorkspace from '../components/StudyWorkspace.vue'
import OnboardingTour from '../components/OnboardingTour.vue'
import {
  buildStudyPlan,
  applyStudyPlan,
  buildReliefPreview,
} from '../utils/studyPlan'
import { checkinHistory, daysUntil, taskProgress } from '../utils/studyProgress'
import { ElMessage } from 'element-plus'
import {
  dashboardApi,
  examApi,
  featureApi,
  focusApi,
  studyApi,
  taskApi,
} from '../api'
import { useUserStore } from '../stores/user'
import { useNotificationStore } from '../stores/notifications'
import {
  USE_MOCK,
  getToday,
  mockEmergency,
  mockMood,
  mockOverview,
  mockPressure,
  mockTop3,
  mockStudySession,
  setMockScenario,
} from '../mock/dashboard'
import { examColor } from '../utils/subjectColor'

const userStore = useUserStore()
const notices = useNotificationStore()
const router = useRouter()
const route = useRoute()

const loading = ref(true)
const error = ref('')
const exams = ref([])
const tasks = ref([])
const overall = computed(() => taskProgress(tasks.value))
const extras = ref({ streak: 0, focus_minutes: 0 })
const refreshing = ref(false)
const featureWarning = ref('')
const pendingIds = ref(new Set())
const taskFilter = ref('today')
const moodSaving = ref(false)
const focusSaving = ref(false)
const pressure = ref(null)
const mood = ref(null)
const moodScore = ref(0)
const emergencyVisible = ref(false)
const emergency = ref(null)
const top3 = ref(null)
const reliefVisible = ref(false)
const reliefOption = ref('lighten')
const relief = ref(null)

// —— 番茄钟（FMZH-SRS-2.10.0）：计时结束时长计入对应科目，作为学习统计唯一依据 ——
const FOCUS_PRESETS = [25, 15, 45]
const focusData = ref({
  total_minutes: 0,
  goal_minutes: 0,
  achieved: false,
  session_count: 0,
  by_exam: [],
})
const focusExamId = ref(null)
const focusMinutes = ref(25)
const remainSec = ref(25 * 60)
const focusRunning = ref(false)
const focusStarted = ref(false)
const recordedMin = ref(0) // 本轮已写入统计的分钟数（防止重复计）
const goalInput = ref(60)
const weekFocus = ref(0)
let focusTimerId = null
let focusEndAt = 0
let featureRequest = 0

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

const dailyBudget = ref(240)
const workspaceOffset = ref(100)
let headerObserver
const selectedTaskId = ref(null)
const selectedTask = computed(
  () => tasks.value.find((t) => t.id === selectedTaskId.value) || null,
)
const guideVisible = ref(false)
let guideAutoChecked = false
const guideKey = () => ['fmzh_onboarding_v2', userStore.user?.id || 'preview', userStore.user?.created_at || userStore.user?.username || 'demo'].join(':')
const guideDismissed = () => {
  try {
    return localStorage.getItem(guideKey()) === 'completed'
  } catch {
    return false
  }
}
const startGuide = () => {
  window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  guideVisible.value = true
}
const finishGuide = async () => {
  guideVisible.value = false
  try {
    localStorage.setItem(guideKey(), 'completed')
  } catch {}
  await nextTick()
  window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  document.querySelector('.hero h1')?.focus({ preventScroll: true })
}
const mockScenario = ref(mockStudySession.scenario)
const planningVisible = ref(false),
  planningBusy = ref(false),
  budgetHours = ref(4),
  planPreview = ref(null)
const selectTask = (task) => {
  if (focusStarted.value && task?.id !== selectedTaskId.value) {
    ElMessage.info('先结束当前这轮专注，再切换任务')
    return
  }
  selectedTaskId.value = task?.id || null
  if (!focusStarted.value) focusExamId.value = task?.exam_id || null
}
const onFocusExamChange = (id) => {
  selectedTaskId.value =
    tasks.value.find(
      (t) => t.exam_id === id && !t.is_done && t.plan_date <= getToday(),
    )?.id || null
}
const startTask = async (task) => {
  if (
    focusStarted.value &&
    (selectedTaskId.value !== task.id || focusRunning.value)
  ) {
    ElMessage.info('当前已有一轮专注，请先结束本轮')
    return
  }
  selectTask(task)
  if (!focusRunning.value) await toggleFocus()
}
const changeScenario = async (key) => {
  if (focusStarted.value) {
    ElMessage.info('请先结束本轮专注')
    mockScenario.value = mockStudySession.scenario
    return
  }
  setMockScenario(key)
  selectedTaskId.value = null
  await load()
}
const openPlanning = () => {
  if (focusStarted.value) {
    ElMessage.info('先结束本轮专注，再调整全科排程')
    return
  }
  budgetHours.value = dailyBudget.value / 60
  planPreview.value = null
  planningVisible.value = true
}
const saveBudget = async () => {
  if (
    !Number.isFinite(Number(budgetHours.value)) ||
    budgetHours.value < 0.5 ||
    budgetHours.value > 16
  ) {
    ElMessage.warning('请输入 0.5 至 16 小时的每日总时间')
    return
  }
  planningBusy.value = true
  try {
    const minutes = Math.round(budgetHours.value * 60)
    if (USE_MOCK) {
      dailyBudget.value = minutes
      focusData.value.goal_minutes = minutes
      mockStudySession.daily_minutes = minutes
      focusData.value.achieved = focusData.value.total_minutes >= minutes
    } else {
      const setting = await studyApi.saveSettings({ daily_minutes: minutes })
      dailyBudget.value = setting.daily_minutes
      await loadFocus()
    }
    goalInput.value = minutes
    planPreview.value = null
    ElMessage.success('全科预算与今日专注目标已保存')
  } catch {
  } finally {
    planningBusy.value = false
  }
}
const previewPlan = async () => {
  if (Math.round(budgetHours.value * 60) !== dailyBudget.value) {
    ElMessage.info('先保存新的每日时间，再预览')
    return
  }
  planningBusy.value = true
  try {
    planPreview.value = USE_MOCK
      ? buildStudyPlan(tasks.value, exams.value, dailyBudget.value, getToday())
      : await studyApi.preview()
  } catch {
  } finally {
    planningBusy.value = false
  }
}
watch(budgetHours, () => {
  planPreview.value = null
})
const planDaySubjects = (day) => {
  const totals = new Map()
  for (const part of planPreview.value?.assignments || [])
    if (part.date === day)
      totals.set(part.exam_id, (totals.get(part.exam_id) || 0) + part.minutes)
  for (const task of tasks.value)
    if (task.plan_date === day && (task.is_done || task.source !== 'ai'))
      totals.set(
        task.exam_id,
        (totals.get(task.exam_id) || 0) + task.estimated_minutes,
      )
  return [...totals]
    .map(
      ([id, minutes]) =>
        `${exams.value.find((e) => e.id === id)?.subject || '未归类'} ${minutes}分`,
    )
    .join(' · ')
}
const confirmPlan = async () => {
  if (!planPreview.value || planPreview.value.conflicts.length) return
  planningBusy.value = true
  try {
    if (USE_MOCK) {
      tasks.value = applyStudyPlan(tasks.value, planPreview.value)
    } else {
      await studyApi.confirm({ fingerprint: planPreview.value.fingerprint })
      await load()
    }
    planningVisible.value = false
    ElMessage.success('全科计划已更新，回到清单开始复习')
  } catch {
    planPreview.value = null
  } finally {
    planningBusy.value = false
  }
}
watch(
  tasks,
  (value) => {
    if (USE_MOCK) mockStudySession.tasks = JSON.parse(JSON.stringify(value))
  },
  { deep: true },
)
watch(
  focusData,
  (value) => {
    if (USE_MOCK) mockStudySession.focus = JSON.parse(JSON.stringify(value))
  },
  { deep: true },
)
watch(
  () => tasks.value.find((t) => t.id === selectedTaskId.value)?.is_done,
  (value) => {
    if (value && !focusStarted.value)
      selectTask(
        tasks.value.find((t) => !t.is_done && t.plan_date <= getToday()) ||
          null,
      )
  },
)

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

const rateText = computed(() => `${Math.round(overall.value.rate * 100)}%`)
const todayTotal = computed(
  () => tasks.value.filter((t) => t.plan_date === getToday()).length,
)
const todayDone = computed(
  () =>
    tasks.value.filter((t) => t.plan_date === getToday() && t.is_done).length,
)
const todayMinutes = computed(() =>
  tasks.value
    .filter((t) => t.plan_date <= getToday() && !t.is_done)
    .reduce((sum, t) => sum + t.estimated_minutes, 0),
)
const sortedExams = computed(() =>
  [...exams.value]
    .map((e) => ({ ...e, days_left: daysUntil(e.exam_date, getToday()) }))
    .sort((a, b) => a.exam_date.localeCompare(b.exam_date)),
)
const upcomingExams = computed(() =>
  sortedExams.value.filter((e) => e.days_left >= 0),
)
const nearestExam = computed(() => upcomingExams.value[0])
const examProgress = computed(() =>
  sortedExams.value.map((e) => {
    const progress = taskProgress(tasks.value.filter((t) => t.exam_id === e.id))
    return {
      ...e,
      total_tasks: progress.total,
      done_tasks: progress.done,
      progress: progress.rate,
    }
  }),
)
const colorFor = (id) => examColor(exams.value.find((e) => e.id === id))
const history = computed(() => checkinHistory(tasks.value, getToday()))
const heroMessage = computed(() => {
  if (!overall.value.total)
    return '把历年题、课堂笔记和老师重点交给 AI，从一份适合你的复习计划开始。'
  if (!todayMinutes.value)
    return '今天的待办已经处理好了。回顾一下收获，也给自己留一点休息时间。'
  return `今天还有 ${tasks.value.filter((t) => t.plan_date <= getToday() && !t.is_done).length} 项待办，预计 ${todayMinutes.value} 分钟。先做最重要的一件，慢慢把计划变成进度。`
})
const moodHint = computed(() => {
  const map = ['', '很差', '较差', '一般', '不错', '很好']
  return moodScore.value ? map[moodScore.value] : '今天心情怎么样？'
})

const statTiles = computed(() => [
  {
    label: '今日任务',
    value: `${todayDone.value} / ${todayTotal.value}`,
    sub: '已完成 / 今日计划',
    to: '/#board',
  },
  {
    label: '复习总进度',
    value: rateText.value,
    sub: `${overall.value.done} / ${overall.value.total} 个任务已完成`,
    to: '/stats',
  },
  {
    label: '本周专注',
    value: `${extras.value.focus_minutes} min`,
    sub: '来自番茄钟的实际记录',
    to: '/stats',
  },
  {
    label: '近期考试',
    value: `${upcomingExams.value.length} 门`,
    sub: nearestExam.value
      ? `${nearestExam.value.subject} · ${nearestExam.value.days_left === 0 ? '今天开考' : nearestExam.value.days_left + ' 天后'}`
      : '暂时没有待考科目',
    to: '/exams',
  },
])

const fmtMd = (d) => {
  const [, m, day] = d.split('-')
  return `${+m}月${+day}日`
}
const weekOf = (d) =>
  `周${['日', '一', '二', '三', '四', '五', '六'][new Date(`${d}T00:00:00`).getDay()]}`
const dateChip = (t) => {
  if (t.is_done) return '已打卡'
  if (t.plan_date === getToday()) return '今天'
  if (t.plan_date < getToday()) return '已逾期'
  return fmtMd(t.plan_date)
}

const toggleById = (id) => {
  const task = tasks.value.find((t) => t.id === id)
  if (task) onToggle(task)
}

const onToggle = async (task) => {
  if (pendingIds.value.has(task.id)) return
  if (!task.is_done && selectedTaskId.value === task.id && focusStarted.value) {
    await resetFocus()
    if (focusStarted.value) return
  }
  pendingIds.value.add(task.id)
  try {
    if (USE_MOCK) {
      task.is_done = !task.is_done
      task.done_at = task.is_done ? `${getToday()}T12:00:00` : null
      // Demonstration recommendations must not retain completed tasks.
      const undone = tasks.value
        .filter((t) => !t.is_done)
        .sort(
          (a, b) =>
            a.priority - b.priority || a.plan_date.localeCompare(b.plan_date),
        )
      top3.value = {
        items: undone.slice(0, 3).map((t) => ({
          ...t,
          task_id: t.id,
          subject: t.exam,
          reason: '按任务优先级排序 · 演示建议',
        })),
      }
    } else {
      const updated = await (task.is_done
        ? taskApi.uncheckin(task.id)
        : taskApi.checkin(task.id))
      Object.assign(task, updated)
      await refreshFeatures()
    }
    ElMessage.success(task.is_done ? '已完成，进度向前一步' : '已撤销打卡')
  } catch {
    // The request interceptor displays errors; retain the last confirmed task state.
  } finally {
    pendingIds.value.delete(task.id)
  }
}

const applyFeatures = (results) => {
  const targets = [pressure, mood, top3]
  results.forEach((result, i) => {
    if (result.status === 'fulfilled') targets[i].value = result.value
  })
  if (results[1].status === 'fulfilled')
    moodScore.value = results[1].value?.mood_score || 0
  featureWarning.value = results.some((r) => r.status === 'rejected')
    ? '部分复习建议暂未更新，任务与进度仍可正常使用。'
    : ''
}
const refreshFeatures = async () => {
  if (USE_MOCK) return
  const request = ++featureRequest
  const results = await Promise.allSettled([
    featureApi.pressure(),
    featureApi.moodToday(),
    featureApi.top3(),
  ])
  if (request === featureRequest) applyFeatures(results)
}

const load = async () => {
  if (refreshing.value) return
  notices.refresh()
  if (!tasks.value.length && !exams.value.length) loading.value = true
  refreshing.value = true
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
      top3.value = structuredClone(mockTop3)
      // 预览态：番茄钟用本地假数据
      focusData.value = structuredClone(mockStudySession.focus)
      dailyBudget.value = mockStudySession.daily_minutes
      goalInput.value = focusData.value.goal_minutes
      weekFocus.value = data.extras.focus_minutes
    } else {
      // —— 真实接口 ——
      const [overview, allTasks, examDetails, setting] = await Promise.all([
        dashboardApi.overview(),
        taskApi.list(),
        examApi.list(),
        studyApi.settings(),
      ])
      dailyBudget.value = setting.daily_minutes
      exams.value = overview.exams.map((e) => ({
        ...e,
        color: examDetails.find((detail) => detail.id === e.id)?.color || '',
      }))
      const examMap = Object.fromEntries(
        overview.exams.map((e) => [e.id, e.subject]),
      )
      tasks.value = allTasks.map((t) => ({
        ...t,
        exam: examMap[t.exam_id] || '未归类',
      }))
      await Promise.all([
        refreshFeatures(),
        loadFocus().catch(() => {
          featureWarning.value = '专注统计暂未更新，请稍后刷新。'
        }),
      ])
      extras.value = {
        streak: history.value.streak,
        focus_minutes: weekFocus.value,
      }
    }
  } catch (e) {
    error.value = e?.message || '网络异常，请稍后重试'
  } finally {
    loading.value = false
    refreshing.value = false
  }
  await nextTick()
  if (!selectedTask.value)
    selectTask(
      tasks.value.find((t) => !t.is_done && t.plan_date <= getToday()) || null,
    )
  if (!error.value && !guideAutoChecked) {
    guideAutoChecked = true
    if (!guideDismissed()) startGuide()
  }
  if (route.hash === '#board' && !guideVisible.value) goStep('#board')
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
    const emotion = (5 * (val - 1)) / 4
    const completion = todayTotal.value
      ? (5 * todayDone.value) / todayTotal.value
      : 0
    const score =
      Math.round(
        (0.4 * emotion +
          0.3 * completion +
          0.2 * (5 - pressure.value.score / 20)) *
          100,
      ) / 100
    mood.value = {
      ...mockMood,
      mood_score: val,
      composite_score: score,
      need_relief: score < 2.5,
      suggestion:
        score < 2.5
          ? '状态偏低，建议减轻今日任务或暂停半天'
          : '按自己的节奏复习，记得穿插休息',
    }
    return
  }
  moodSaving.value = true
  try {
    mood.value = await featureApi.submitMood({ mood_score: val })
    ElMessage.success('已记录今日情绪')
  } catch (e) {
    moodScore.value = mood.value?.mood_score || 0
  } finally {
    moodSaving.value = false
  }
}

const loadRelief = async () => {
  if (USE_MOCK) {
    relief.value = buildReliefPreview(
      tasks.value,
      exams.value,
      dailyBudget.value,
      getToday(),
      reliefOption.value,
    )
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
    const moves = new Map(relief.value.moves.map((m) => [m.task_id, m.to_date]))
    tasks.value = tasks.value.map((t) =>
      moves.has(t.id) ? { ...t, plan_date: moves.get(t.id) } : t,
    )
    ElMessage.success('已按方案减轻今日任务（本次演示内有效）')
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
  const [today, sessions] = await Promise.all([
    focusApi.today(),
    focusApi.sessions(),
  ])
  focusData.value = today
  goalInput.value = today.goal_minutes
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
  remainSec.value = Math.max(0, Math.ceil((focusEndAt - Date.now()) / 1000))
  if (remainSec.value <= 0) finishFocus()
}

// 把本轮"自上次落盘以来"已专注的整分钟写入统计；不足 1 分钟不计。
// 暂停 / 重置 / 倒计时结束都走这里，靠 recordedMin 保证不重复计。
const flushFocus = async () => {
  const elapsedMin = Math.floor(
    (focusMinutes.value * 60 - Math.max(remainSec.value, 0)) / 60,
  )
  const pending = elapsedMin - recordedMin.value
  if (pending < 1) return 0

  if (USE_MOCK) {
    recordedMin.value = elapsedMin
    focusData.value.total_minutes += pending
    focusData.value.achieved =
      focusData.value.goal_minutes > 0 &&
      focusData.value.total_minutes >= focusData.value.goal_minutes
    weekFocus.value += pending
    extras.value = { ...extras.value, focus_minutes: weekFocus.value }
    return pending
  }
  await focusApi.createSession({
    exam_id: focusExamId.value,
    duration_minutes: pending,
  })
  recordedMin.value = elapsedMin
  await loadFocus()
  extras.value = { ...extras.value, focus_minutes: weekFocus.value }
  return pending
}

const toggleFocus = async () => {
  if (focusSaving.value) return
  if (focusRunning.value) {
    // 暂停：先把已专注的整分钟落盘
    focusRunning.value = false
    clearInterval(focusTimerId)
    focusTimerId = null
    remainSec.value = Math.max(0, Math.ceil((focusEndAt - Date.now()) / 1000))
    focusSaving.value = true
    try {
      const n = await flushFocus()
      ElMessage.info(
        n ? `已暂停，记录 ${n} 分钟专注` : '已暂停（不足 1 分钟，未计入）',
      )
    } catch {
      ElMessage.warning('专注记录尚未保存，请保留页面并重试')
    } finally {
      focusSaving.value = false
    }
    return
  }
  if (!focusExamId.value) {
    ElMessage.warning('请先选择科目')
    return
  }
  focusRunning.value = true
  focusStarted.value = true
  focusEndAt = Date.now() + remainSec.value * 1000
  focusTimerId = setInterval(tickFocus, 1000)
}

const resetFocus = async () => {
  if (focusSaving.value) return
  if (focusRunning.value)
    remainSec.value = Math.max(0, Math.ceil((focusEndAt - Date.now()) / 1000))
  focusRunning.value = false
  clearInterval(focusTimerId)
  focusTimerId = null
  focusSaving.value = true
  try {
    const n = await flushFocus()
    focusStarted.value = false
    recordedMin.value = 0
    remainSec.value = focusMinutes.value * 60
    ElMessage.info(n ? `已重置，记录 ${n} 分钟专注` : '已重置')
  } catch {
    ElMessage.warning('专注记录尚未保存，请重试后再重置')
  } finally {
    focusSaving.value = false
  }
}

const finishFocus = async () => {
  clearInterval(focusTimerId)
  focusTimerId = null
  focusRunning.value = false
  remainSec.value = 0 // 确保 elapsed 按整轮计算
  focusSaving.value = true
  try {
    await flushFocus()
    focusStarted.value = false
    recordedMin.value = 0
    remainSec.value = focusMinutes.value * 60
    ElMessage.success(
      focusData.value.achieved
        ? '专注已记录，今日目标已达成'
        : '本轮专注已记录，休息一下吧',
    )
  } catch {
    ElMessage.warning('本轮专注尚未保存，请点击重置重试')
  } finally {
    focusSaving.value = false
  }
}

const goStep = (to) => {
  if (to === '#board') {
    const board = document.getElementById('board')
    board?.focus({ preventScroll: true })
    window.scrollTo({
      top: board
        ? board.getBoundingClientRect().top +
          window.scrollY -
          workspaceOffset.value
        : 0,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
    })
    return
  }
  router.push(to)
}

watch(
  () => route.hash,
  async (hash) => {
    await nextTick()
    if (hash === '#board') goStep(hash)
  },
)
onMounted(load)
onMounted(() => {
  const header = document.querySelector('.header')
  if (header) {
    headerObserver = new ResizeObserver(() => {
      workspaceOffset.value = Math.ceil(
        header.getBoundingClientRect().height + 16,
      )
    })
    headerObserver.observe(header)
  }
})
onBeforeRouteLeave(async () => {
  // Logout and expired sessions have already removed the token; do not trap navigation.
  if (!localStorage.getItem('fmzh_token')) return true
  if (focusSaving.value) return false
  if (focusRunning.value) {
    remainSec.value = Math.max(0, Math.ceil((focusEndAt - Date.now()) / 1000))
    focusRunning.value = false
    clearInterval(focusTimerId)
  }
  try {
    await flushFocus()
  } catch {
    ElMessage.warning('专注记录尚未保存，请重试后再离开')
    return false
  }
})
onBeforeUnmount(() => {
  headerObserver?.disconnect()
  clearInterval(focusTimerId)
})
</script>

<style scoped>
.guide-replay { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:24px 0 0; margin-top:28px; border-top:1px solid var(--line); }
.guide-replay h2 { font-family:var(--font-serif); font-size:18px; }
.guide-replay p { font-size:12px; line-height:1.8; color:var(--ink-2); margin-top:6px; }
.guide-replay .el-button { flex-shrink:0; }
@media(max-width:600px) { .guide-replay { align-items:flex-start; flex-direction:column; gap:14px; } }

.home-notices { display:flex; align-items:center; gap:16px; padding:14px 18px; margin-bottom:22px; background:var(--bg-soft); border-left:3px solid var(--coral); font-size:12px; }
.home-notices div { min-width:0; flex:1; }
.home-notices p { margin-top:5px; color:var(--ink-2); overflow-wrap:anywhere; line-height:1.7; }
.home-notices a { flex-shrink:0; color:var(--coral-deep); font-weight:700; text-decoration:none; }
/* A daily study desk: paper, ink, coral. Keep the established brand. */
.dash {
  --muted: #687168;
  display: grid;
  gap: 26px;
}
.desk-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.eyebrow {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--muted);
}
.edition {
  margin-left: 12px;
  font: 500 10px var(--font-num);
  letter-spacing: 0.12em;
  color: var(--coral-deep);
}
.desk-date {
  margin: 0;
  color: var(--ink-2);
  font-size: 13px;
}
.desk-date span {
  font-size: 11px;
  color: var(--muted);
}
.loading-desk {
  padding: 40px;
  background: var(--bg-card);
  border-radius: 16px;
}
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 262px;
  position: relative;
  overflow: hidden;
  background: var(--ink-1);
  border: 1px solid var(--ink-1);
  border-radius: 18px;
  padding: 38px 40px;
  gap: 32px;
  box-shadow: 5px 5px 0 var(--coral);
}
.hero::before {
  content: '';
  position: absolute;
  width: 520px;
  height: 520px;
  border-radius: 50%;
  border: 1px solid #f0ede316;
  left: 34%;
  top: -42%;
  pointer-events: none;
  box-shadow:
    0 0 0 48px #f0ede306,
    0 0 0 96px #f0ede304;
}
.hero-copy {
  position: relative;
  z-index: 1;
}
.hero-kicker {
  display: flex;
  gap: 9px;
  align-items: center;
  margin: 0 0 20px;
  font-size: 12px;
  color: #dfdfcd;
}
.live-dot {
  width: 6px;
  height: 6px;
  background: var(--coral-bright);
  border-radius: 50%;
  box-shadow: 0 0 0 4px #f0846b16;
}
.hero h1 {
  margin: 0;
  font-size: clamp(30px, 3.6vw, 46px);
  line-height: 1.4;
  font-weight: 900;
  letter-spacing: 0.03em;
  color: var(--bg-card);
}
.hero h1 span {
  color: var(--coral-bright);
}
.hero-sub {
  max-width: 420px;
  margin: 18px 0 0;
  font-size: 13px;
  line-height: 1.9;
  color: #bec6b9;
  text-wrap: pretty;
}
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 22px;
  margin: 24px 0;
}
.hero-actions .el-button {
  border-color: var(--coral-bright);
  border-radius: 7px;
  box-shadow: none;
  font-size: 13px;
}
.action-arrow {
  margin-left: 20px;
}
.hero-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
  font-size: 12px;
  color: var(--bg-page);
}
.hero-link:hover {
  color: var(--coral-bright);
}
.exam-ticket {
  position: relative;
  align-self: center;
  padding: 20px 22px;
  background: var(--bg-card);
  border-radius: 5px;
  color: var(--ink-1);
  transform: rotate(2deg);
  box-shadow: 5px 6px 0 #0003;
}
.ticket-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--ink-2);
}
.ticket-no {
  font: 500 10px var(--font-num);
  color: var(--muted);
}
.ticket-count {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 16px 0 20px;
}
.ticket-count strong {
  font: 700 78px/0.95 var(--font-num);
  letter-spacing: -0.08em;
}
.ticket-count span {
  font-size: 11px;
  color: var(--muted);
}
.ticket-bottom {
  display: grid;
  gap: 8px;
  border-top: 1px dashed #a6ad9b;
  padding-top: 16px;
  position: relative;
}
.ticket-bottom::before,
.ticket-bottom::after {
  content: '';
  position: absolute;
  top: -8px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--ink-1);
}
.ticket-bottom::before {
  left: -29px;
}
.ticket-bottom::after {
  right: -29px;
}
.ticket-bottom b {
  font-family: var(--font-serif);
  font-size: 18px;
}
.ticket-bottom span {
  font-size: 11px;
  color: var(--muted);
}
.ticket-bottom a {
  margin-top: 8px;
  width: fit-content;
  color: var(--coral-deep);
  font-size: 11px;
  font-weight: 700;
  text-decoration: none;
}
.ticket-stamp {
  position: absolute;
  right: 15px;
  bottom: 25px;
  border: 1px solid #c2472f70;
  padding: 4px;
  font-size: 10px;
  color: var(--coral-deep);
  transform: rotate(-12deg);
}
.ticket-empty {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 24px 0;
  line-height: 1.7;
  color: var(--muted);
  font-size: 13px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 16px 0 20px;
  border-bottom: 1px solid var(--line);
}
.metric {
  display: grid;
  gap: 10px;
  padding: 0 24px;
  color: inherit;
  text-decoration: none;
  border-right: 1px solid var(--line);
}
.metric:first-child {
  padding-left: 0;
}
.metric:last-child {
  border: 0;
  padding-right: 0;
}
.metric-label {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 11px;
  color: var(--ink-2);
}
.metric-label .el-icon {
  margin-left: auto;
  color: var(--muted);
}
.metric-index {
  font: 500 10px var(--font-num);
  color: var(--coral-deep);
}
.metric strong {
  font: 500 32px/1.2 var(--font-num);
  letter-spacing: -0.05em;
  font-variant-numeric: tabular-nums;
  transition: color 0.2s;
}
.metric:hover strong {
  color: var(--coral-deep);
}
.metric-sub {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.5;
}
.panel {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 24px;
  background: var(--bg-card);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  margin-bottom: 20px;
}
.section-head h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 900;
  letter-spacing: 0.025em;
}
.section-head .eyebrow {
  font-size: 10px;
  font-weight: 500;
}
.text-link {
  color: var(--ink-2);
  font-size: 11px;
  text-decoration: none;
  white-space: nowrap;
}
.text-link:hover {
  color: var(--coral-deep);
}
.priority-check.el-button {
  width: 28px;
  height: 28px;
  border: 1px solid #acb0a2;
  background: transparent;
  box-shadow: none;
}
.priority-check.el-button:hover {
  background: var(--green-soft);
  border-color: var(--green);
}
.task-list .el-checkbox {
  height: 24px;
}
.exam-info i {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 2px;
  flex-shrink: 0;
}
.quiet-empty {
  padding: 20px 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}
#board {
  scroll-margin-top: 150px;
}
.focus-panel {
  background: #e8e9dd;
  border-color: #cfd3c0;
}
.focus-panel h2 {
  font-size: 16px;
}
.focus-status {
  font-size: 10px;
  color: var(--green);
}
.focus-setup {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 95px;
  gap: 8px;
}
.focus-clock {
  text-align: center;
  font: 500 50px/1.2 var(--font-num);
  letter-spacing: -0.06em;
  margin: 24px 0;
  font-variant-numeric: tabular-nums;
}
.focus-clock.running {
  color: var(--coral-deep);
}
.focus-actions {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}
.focus-actions .el-button {
  margin: 0;
}
.focus-actions .el-button--primary {
  box-shadow: none;
}
.focus-goal {
  margin-top: 22px;
}
.goal-line {
  display: flex;
  gap: 8px;
  justify-content: space-between;
  font-size: 11px;
  margin-bottom: 10px;
}
.goal-line b {
  font-family: var(--font-num);
}
.goal-line small {
  color: var(--muted);
  font-size: 10px;
}
.achieved {
  color: var(--green);
  font-size: 10px;
}
.focus-hint {
  font-size: 11px;
  color: var(--muted);
}
.care-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}
.care-grid .section-head {
  margin-bottom: 16px;
}
.care-grid h2 {
  font-size: 17px;
}
.pressure-level {
  background: var(--green-soft);
  color: var(--green);
  font-size: 10px;
  padding: 5px 8px;
  border-radius: 4px;
}
.pressure.alert {
  border-color: var(--coral);
}
.pressure.alert .pressure-level {
  background: var(--coral-soft);
  color: var(--coral-deep);
}
.pressure-reading {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 15px;
}
.pressure-reading strong {
  font: 500 36px var(--font-num);
  white-space: nowrap;
}
.pressure-reading small {
  font-size: 12px;
  color: var(--muted);
  margin-left: 6px;
}
.pressure-reading > span {
  font-size: 11px;
  color: var(--ink-2);
  line-height: 1.7;
}
.pressure-scale {
  height: 6px;
  background: var(--bg-soft);
  overflow: hidden;
  border-radius: 3px;
}
.pressure-scale i {
  display: block;
  height: 100%;
  background: var(--green);
  transition: width 0.3s;
}
.pressure.alert .pressure-scale i {
  background: var(--coral);
}
.pressure-labels {
  display: flex;
  justify-content: space-between;
  margin: 8px 0;
  font-size: 9px;
  color: var(--muted);
}
.pressure .el-button {
  padding-left: 0;
  height: auto;
  margin-top: 10px;
  font-size: 11px;
}
.mood-word {
  font-size: 11px;
  color: var(--coral-deep);
}
.mood .el-rate {
  --el-rate-icon-size: 28px;
  --el-rate-fill-color: var(--coral);
}
.mood-explain {
  font-size: 11px;
  line-height: 1.8;
  color: var(--ink-2);
}
.mood-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 10px;
  color: var(--muted);
}
.mood-bottom b {
  font-size: 16px;
  color: var(--ink-1);
}
.exam-timeline {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 20px;
}
.exam-timeline article {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  border-top: 2px solid var(--line);
  padding: 18px 0 10px;
  position: relative;
  min-width: 0;
}
.exam-timeline article::before {
  content: '';
  position: absolute;
  width: 7px;
  height: 7px;
  left: 0;
  top: -5px;
  border-radius: 50%;
  background: #b5bbac;
}
.exam-timeline article.urgent::before {
  background: var(--coral);
}
.exam-date {
  width: 100%;
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.exam-date b {
  font: 500 17px var(--font-num);
}
.exam-date span {
  font-size: 10px;
  color: var(--muted);
}
.exam-info {
  flex: 1;
  min-width: 80px;
}
.exam-info > b {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
}
.exam-info p,
.exam-info > span,
.exam-info a {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.8;
}
.exam-info a {
  color: var(--coral-deep);
  text-decoration: none;
}
.exam-days {
  display: flex;
  flex-direction: column;
  text-align: right;
  gap: 5px;
}
.exam-days strong {
  font: 500 30px/1 var(--font-num);
}
.exam-days span {
  font-size: 9px;
  color: var(--muted);
}
.urgent .exam-days strong {
  color: var(--coral-deep);
}
.past .exam-days strong {
  font: 500 13px var(--font-sans);
  color: var(--muted);
}
.study-path .el-icon {
  margin-left: auto;
  color: var(--muted);
}
.demo-note {
  margin: 0;
  text-align: center;
  font-size: 10px;
  color: var(--muted);
}
.inline-warning {
  margin: 0;
  font-size: 12px;
  color: var(--amber);
}
/* Existing feature dialogs remain functional within the same visual language. */
.eg-head {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line);
}
.eg-subject {
  font-family: var(--font-serif);
  font-weight: 700;
}
.eg-meta {
  font-size: 12px;
  color: var(--muted);
}
.eg-list,
.rf-list {
  list-style: none;
  padding: 0;
  margin: 14px 0;
  max-height: 52dvh;
  overflow: auto;
}
.eg-item {
  display: flex;
  gap: 12px;
  padding: 15px 0;
  border-bottom: 1px solid var(--line);
}
.eg-idx {
  font-family: var(--font-num);
  color: var(--coral-deep);
}
.eg-body {
  flex: 1;
  min-width: 0;
}
.eg-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}
.eg-kind {
  background: var(--coral-soft);
  color: var(--coral-deep);
  border-radius: 3px;
  padding: 2px 5px;
  font-size: 10px;
}
.eg-content {
  font-size: 13px;
}
.eg-basis,
.eg-weight {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
  margin-top: 4px;
}
.eg-note,
.rf-summary {
  line-height: 1.9;
  font-size: 13px;
}
.eg-loading,
.rf-loading {
  padding: 26px 0;
  text-align: center;
  color: var(--muted);
}
.rf-opts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.rf-opts .el-button {
  margin: 0;
}
.rf-cap {
  font-size: 12px;
  width: 100%;
  color: var(--muted);
}
.rf-item {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
}
.rf-dates {
  font-family: var(--font-num);
  color: var(--muted);
}
.rf-conflicts {
  padding: 14px;
  background: var(--coral-soft);
  font-size: 12px;
  line-height: 1.9;
  border-radius: 8px;
}
.rf-conf-head {
  font-weight: 700;
  color: var(--coral-deep);
}
.rf-conflicts ul {
  padding-left: 18px;
}
.rise {
  animation: desk-in 0.5s ease both;
}
@keyframes desk-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (max-width: 1050px) {
  .hero {
    padding: 30px;
    grid-template-columns: minmax(0, 1fr) 225px;
    gap: 24px;
  }
  .panel {
    padding: 20px;
  }
  .metric {
    padding-inline: 16px;
  }
  .metric strong {
    font-size: 28px;
  }
}
@media (max-width: 800px) {
  .hero {
    grid-template-columns: minmax(0, 1fr) 200px;
    padding: 28px;
  }
  .hero h1 {
    font-size: 34px;
  }
  .ticket-count strong {
    font-size: 64px;
  }
  .hero-actions {
    gap: 16px;
  }
  .hero-link {
    font-size: 11px;
  }
  .hero-sub {
    font-size: 12px;
  }
  .edition {
    display: none;
  }
  .metric strong {
    font-size: 26px;
  }
  .metric-index {
    display: none;
  }
  .care-grid {
    gap: 20px;
  }
  .exam-timeline {
    grid-template-columns: 1fr;
  }
  .exam-timeline article {
    display: grid;
    grid-template-columns: 90px minmax(0, 1fr) auto;
    gap: 18px;
    border-top: 1px solid var(--line);
    padding: 18px 0;
  }
  .exam-timeline article::before {
    display: none;
  }
  .exam-date {
    display: grid;
    align-content: start;
    gap: 4px;
  }
  .exam-days {
    align-self: center;
  }
}
@media (max-width: 560px) {
  .dash {
    gap: 22px;
  }
  .desk-heading {
    align-items: flex-start;
    gap: 6px;
  }
  .desk-heading > .el-button {
    padding: 4px;
    height: auto;
    font-size: 11px;
  }
  .desk-date {
    font-size: 11px;
  }
  .desk-date span {
    display: block;
    margin-top: 5px;
  }
  .eyebrow {
    font-size: 10px;
  }
  .hero {
    grid-template-columns: 1fr;
    padding: 26px 24px;
    gap: 28px;
    border-radius: 12px;
    box-shadow: 3px 3px 0 var(--coral);
  }
  .hero h1 {
    font-size: 34px;
  }
  .hero-kicker {
    margin-bottom: 15px;
  }
  .hero-sub {
    max-width: 100%;
  }
  .hero-actions {
    gap: 20px;
    margin: 20px 0;
  }
  .exam-ticket {
    transform: rotate(0);
    padding: 16px 18px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .ticket-top {
    grid-column: 1 / -1;
  }
  .ticket-count {
    margin: 0;
    align-items: center;
    gap: 12px;
  }
  .ticket-count strong {
    font-size: 58px;
  }
  .ticket-count span {
    max-width: 24px;
    line-height: 1.6;
  }
  .ticket-bottom {
    padding: 0 0 0 16px;
    border-top: 0;
    border-left: 1px dashed #a6ad9b;
    gap: 5px;
  }
  .ticket-bottom::before,
  .ticket-bottom::after {
    display: none;
  }
  .ticket-bottom b {
    font-size: 16px;
  }
  .ticket-bottom span,
  .ticket-bottom a {
    font-size: 10px;
  }
  .ticket-bottom a {
    margin-top: 3px;
  }
  .ticket-stamp {
    top: 9px;
    right: 65px;
    bottom: auto;
    font-size: 9px;
    padding: 2px 4px;
  }
  .ticket-empty {
    padding: 10px 0;
    font-size: 11px;
  }
  .metrics {
    grid-template-columns: 1fr 1fr;
    gap: 20px 0;
    padding: 8px 0 20px;
  }
  .metric {
    padding: 0 16px;
  }
  .metric:nth-child(3) {
    padding-left: 0;
  }
  .metric:nth-child(2) {
    border: 0;
    padding-right: 0;
  }
  .metric strong {
    font-size: 30px;
  }
  .metric-sub {
    font-size: 10px;
  }
  .care-grid {
    grid-template-columns: 1fr;
  }
  .panel {
    padding: 20px 18px;
    border-radius: 10px;
  }
  .section-head h2 {
    font-size: 17px;
  }
  .priority-check.el-button {
    width: 26px;
    height: 26px;
  }
  .focus-clock {
    margin: 24px 0;
    font-size: 60px;
  }
  .study-path .el-icon {
    display: none;
  }
  .exam-timeline article {
    grid-template-columns: 74px minmax(0, 1fr) auto;
    gap: 10px;
  }
  .exam-date b {
    font-size: 14px;
  }
  .exam-info > b {
    font-size: 12px;
  }
  .exam-days strong {
    font-size: 27px;
  }
  .pressure-reading {
    gap: 15px;
  }
  .demo-note {
    font-size: 9px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .rise {
    animation: none;
  }
  .pressure-scale i {
    transition: none;
  }
}

/* 本轮：首页封面 → 今日复习工作区 → 可展开的节奏调整。 */
.desk-utilities {
  display: flex;
  align-items: center;
  gap: 8px;
}
.scenario-picker {
  width: 140px;
}
.cover-progress {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-top: 22px;
}
.cover-progress :deep(.progress-ring) {
  width: 66px;
  height: 66px;
}
.cover-progress strong {
  font-family: 'Space Grotesk';
  font-size: 19px;
  line-height: 1;
}
.cover-progress strong small {
  font-size: 10px;
}
.cover-progress > span {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cover-progress > span b {
  font-size: 12px;
}
.cover-progress > span small {
  font-size: 10px;
  color: var(--ink-3);
}
.workspace-focus {
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.workspace-focus .section-head {
  margin-bottom: 9px;
}
.workspace-focus .section-head h2 {
  font-family: inherit;
  font-size: 12px;
}
.workspace-focus .focus-setup {
  gap: 8px;
}
.workspace-focus .focus-clock {
  font-size: 57px;
  margin: 12px 0;
  line-height: 1.1;
}
.workspace-focus .focus-actions {
  gap: 8px;
}
.workspace-focus .focus-actions .el-button {
  font-size: 11px;
  padding: 8px 10px;
  height: 33px;
}
.workspace-focus .focus-goal {
  margin-top: 17px;
  padding-top: 14px;
}
.workspace-focus .goal-line {
  font-size: 10px;
}
.workspace-focus .focus-status {
  font-size: 9px;
}
.care-section {
  margin: 24px 0;
}
.care-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
  padding: 17px 0;
  border-bottom: 1px solid var(--line);
}
.care-heading h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.care-heading small {
  font-size: 10px;
  color: var(--ink-3);
}
.care-section .care-grid {
  margin-top: 18px;
}
.planning-intro {
  font-size: 12px;
  line-height: 1.9;
  margin: 0 0 20px;
  color: var(--ink-3);
}
.budget-editor {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
}
.budget-note {
  font-size: 10px;
  color: var(--ink-3);
  margin: 12px 0 20px;
  line-height: 1.8;
}
.plan-preview {
  margin-top: 20px;
  font-size: 12px;
}
.preview-scroll {
  max-height: 240px;
  overflow: auto;
  margin-top: 12px;
}
.preview-scroll table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.preview-scroll th,
.preview-scroll td {
  padding: 10px;
  border-bottom: 1px solid var(--line);
}
.plan-conflicts {
  padding: 12px;
  background: #f4e5dc;
  color: var(--coral-deep);
  line-height: 1.8;
}
.plan-conflicts ul {
  padding-left: 18px;
}
.plan-preview a {
  display: block;
  margin-top: 12px;
  color: var(--coral-deep);
}
@media (max-width: 760px) {
  .desk-heading {
    align-items: flex-start;
    gap: 12px;
    flex-wrap: wrap;
  }
  .desk-utilities {
    width: 100%;
    justify-content: flex-end;
  }
  .desk-date {
    font-size: 10px;
  }
  .care-heading {
    gap: 10px;
    flex-wrap: wrap;
  }
  .care-heading small {
    width: 100%;
    order: 3;
  }
  .cover-progress :deep(.progress-ring) {
    width: 58px;
    height: 58px;
  }
  .workspace-focus .focus-clock {
    font-size: 50px;
    margin: 10px 0;
  }
  .workspace-focus .focus-goal {
    margin-top: 12px;
  }
  .hero {
    margin-bottom: 20px;
  }
  .metrics {
    margin-bottom: 22px;
  }
}
</style>
