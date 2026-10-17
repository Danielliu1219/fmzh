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
      <el-button :loading="refreshing" :disabled="loading" text @click="load"
        ><el-icon><Refresh /></el-icon>&nbsp;刷新数据</el-button
      >
    </div>
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
          <h1>期末有计划，<br /><span>今天不慌张。</span></h1>
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
          <div class="hero-footnote">
            <span>资料有依据</span><i></i><span>计划按天走</span><i></i
            ><span>每一步都算数</span>
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
      <div class="work-grid">
        <div class="work-main">
          <section
            v-if="top3"
            class="priority-panel rise"
            aria-labelledby="priority-title"
          >
            <div class="section-head">
              <div>
                <p class="eyebrow">先做好这几件事</p>
                <h2 id="priority-title">今日优先</h2>
              </div>
              <span class="section-note">按考点权重与考试临近程度推荐</span>
            </div>
            <p v-if="!priorityItems.length" class="quiet-empty">
              {{ top3.note || '优先任务已完成，按自己的节奏继续。' }}
            </p>
            <ol v-else class="priority-list">
              <li v-for="(item, i) in priorityItems" :key="item.task_id">
                <span class="priority-number">0{{ i + 1 }}</span>
                <div class="priority-copy">
                  <b>{{ item.title }}</b>
                  <p>
                    {{ item.subject }} <span>· {{ item.reason }}</span>
                  </p>
                  <small v-if="item.plan_date > getToday()"
                    >计划 {{ fmtMd(item.plan_date) }} · 可提前复习</small
                  >
                </div>
                <span class="duration"
                  >{{ item.estimated_minutes }}<small>min</small></span
                >
                <el-button
                  circle
                  class="priority-check"
                  :loading="pendingIds.has(item.task_id)"
                  :disabled="pendingIds.has(item.task_id)"
                  :aria-label="`完成${item.title}`"
                  @click="toggleById(item.task_id)"
                  ><el-icon><Check /></el-icon
                ></el-button>
              </li>
            </ol>
          </section>
          <section
            id="board"
            class="panel task-panel rise"
            aria-labelledby="board-title"
          >
            <div class="section-head">
              <div>
                <p class="eyebrow">把计划变成行动</p>
                <h2 id="board-title">我的任务清单</h2>
              </div>
              <router-link to="/exams" class="text-link"
                >管理任务 ↗</router-link
              >
            </div>
            <div class="task-toolbar">
              <div class="task-tabs" role="group" aria-label="筛选学习任务">
                <button
                  v-for="tab in taskTabs"
                  :key="tab.key"
                  type="button"
                  :class="{ active: taskFilter === tab.key }"
                  :aria-pressed="taskFilter === tab.key"
                  @click="taskFilter = tab.key"
                >
                  {{ tab.label }}<span>{{ tab.count }}</span>
                </button>
              </div>
            </div>
            <div v-if="!visibleTasks.length" class="task-empty">
              <el-icon :size="28"><CircleCheck /></el-icon
              ><b>{{ emptyTaskTitle }}</b>
              <p>
                {{
                  overall.total
                    ? '换个筛选看看，或去课程管理调整计划。'
                    : '录入考试并上传资料，让 AI 帮你安排每天的复习。'
                }}
              </p>
              <router-link
                v-if="!overall.total"
                to="/analysis"
                class="text-link"
                >生成复习计划 →</router-link
              >
            </div>
            <ul v-else class="task-list">
              <li
                v-for="task in visibleTasks"
                :key="task.id"
                :class="{ done: task.is_done }"
              >
                <el-checkbox
                  :model-value="task.is_done"
                  :disabled="pendingIds.has(task.id)"
                  :aria-label="`${task.is_done ? '撤销' : '完成'}${task.title}`"
                  @change="onToggle(task)"
                />
                <div class="task-copy">
                  <b>{{ task.title }}</b>
                  <div class="task-meta">
                    <span class="subject-label"
                      ><i
                        :style="{ background: colorFor(task.exam_id).color }"
                      ></i
                      >{{ task.exam }}</span
                    ><span>{{ task.estimated_minutes }} 分钟</span
                    ><span
                      :class="{
                        overdue: !task.is_done && task.plan_date < getToday(),
                      }"
                      >{{ dateChip(task) }}</span
                    ><span
                      v-if="task.priority === 1 && !task.is_done"
                      class="high-priority"
                      >优先完成</span
                    >
                  </div>
                </div>
                <span v-if="pendingIds.has(task.id)" class="task-state"
                  >保存中</span
                ><span v-else-if="task.is_done" class="task-state">已完成</span>
              </li>
            </ul>
            <div class="task-footer">
              <span>今日已完成 {{ todayDone }} / {{ todayTotal }} 项</span
              ><span>剩余预计 {{ todayMinutes }} 分钟</span>
            </div>
          </section>
        </div>
        <aside class="work-aside">
          <section class="panel progress-panel rise">
            <div class="section-head">
              <h2>复习总进度</h2>
              <router-link
                to="/stats"
                class="text-link"
                aria-label="查看学习统计"
                ><el-icon><TopRight /></el-icon
              ></router-link>
            </div>
            <div class="overall-ring">
              <ProgressRing :value="overall.rate * 100" label="复习总进度"
                ><strong class="progress-number"
                  >{{ Math.round(overall.rate * 100) }}<small>%</small></strong
                ><span class="ring-caption">{{
                  overall.total ? '每次打卡，都在向前' : '从第一个任务开始'
                }}</span></ProgressRing
              >
            </div>
            <p class="progress-tally">
              <b>{{ overall.done }}</b> 已完成
              <span>/ {{ overall.total }} 个任务</span>
            </p>
            <div
              class="subject-progress"
              v-for="e in examProgress.filter((e) => e.total_tasks)"
              :key="e.id"
            >
              <div>
                <span
                  ><i :style="{ background: colorFor(e.id).color }"></i
                  >{{ e.subject }}</span
                ><b>{{ e.done_tasks }}/{{ e.total_tasks }}</b>
              </div>
              <el-progress
                :percentage="Math.round(e.progress * 100)"
                :show-text="false"
                :stroke-width="4"
                :color="colorFor(e.id).color"
              />
            </div>
          </section>
          <section class="panel focus-panel rise">
            <div class="section-head">
              <h2>留一段专注时间</h2>
              <span class="focus-status">{{
                focusRunning ? '专注中' : focusStarted ? '已暂停' : '准备开始'
              }}</span>
            </div>
            <div class="focus-setup">
              <el-select
                v-model="focusExamId"
                aria-label="专注科目"
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
                >重置</el-button
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
              <details class="goal-settings">
                <summary>调整每日目标</summary>
                <div>
                  <el-input-number
                    v-model="goalInput"
                    :min="0"
                    :max="1440"
                    :step="15"
                    size="small"
                    aria-label="每日专注目标分钟数"
                  /><el-button text type="primary" @click="saveGoal"
                    >保存</el-button
                  >
                </div>
                <small>0 表示暂不设置目标</small>
              </details>
            </div>
          </section>
          <section class="streak-panel">
            <div>
              <b
                >连续打卡 <span class="num">{{ history.streak }}</span> 天</b
              ><span>本周 · 按实际完成日期记录</span>
            </div>
            <div class="week-dots">
              <div
                v-for="d in history.week"
                :key="d.date"
                class="week-day"
                :class="{ on: d.done, today: d.today, future: d.future }"
                :title="`${d.date} ${d.done ? '已打卡' : d.future ? '未到日期' : '无打卡记录'}`"
              >
                <span>{{ d.label }}</span
                ><i
                  ><el-icon v-if="d.done"><Check /></el-icon
                  ><span v-else>·</span></i
                >
              </div>
            </div>
          </section>
        </aside>
      </div>
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
            <span>轻松</span><span>适中</span><span>偏压</span><span>高压</span>
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
              >综合评分 <b class="num">{{ mood.composite_score }}</b> / 5</span
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
      <div class="resources-grid">
        <section v-if="review?.items?.length" class="panel review">
          <div class="section-head">
            <div>
              <p class="eyebrow">{{ review.subject }} · 权重优先</p>
              <h2>考前再看一遍</h2>
            </div>
            <router-link
              :to="{ path: '/analysis', query: { exam: review.exam_id } }"
              class="text-link"
              >完整分析 ↗</router-link
            >
          </div>
          <ol class="review-list">
            <li v-for="(item, i) in review.items" :key="i">
              <span class="review-order">{{
                String(i + 1).padStart(2, '0')
              }}</span>
              <div>
                <b>{{ item.name }}</b>
                <p>{{ item.basis || item.source || '依据最近一次复习分析' }}</p>
                <div class="review-bar">
                  <i
                    :style="{
                      width:
                        Math.min(100, Math.max(0, item.weight * 100)) + '%',
                    }"
                  ></i>
                </div>
              </div>
              <strong class="num"
                >{{ Math.round(item.weight * 100) }}<small>%</small></strong
              >
            </li>
          </ol>
          <p class="reference-note">
            AI 生成内容仅供复习参考，请结合课程要求核对。
          </p>
        </section>
        <section v-if="timeslots" class="panel timeslots">
          <div class="section-head">
            <div>
              <p class="eyebrow">每日可用 {{ timeslots.daily_hours }} 小时</p>
              <h2>给复习留好时间</h2>
            </div>
          </div>
          <p v-if="timeslots.note" class="quiet-empty">{{ timeslots.note }}</p>
          <ol class="slots-list">
            <li v-for="slot in timeslots.slots" :key="slot.name">
              <div class="slot-time">
                <b>{{ slot.name }}</b
                ><span>{{ slot.start }}–{{ slot.end }}</span>
              </div>
              <div>
                <b>{{ slot.focus }}</b
                ><span>建议投入 {{ slot.minutes }} 分钟</span>
              </div>
            </li>
          </ol>
          <p class="reference-note">推荐时段仅作参考，按你的作息灵活安排。</p>
        </section>
      </div>
      <nav class="study-path" aria-label="复习流程">
        <router-link
          v-for="(s, i) in flowSteps"
          :key="s.name"
          :to="s.to === '#board' ? '/#board' : s.to"
          @click="s.to === '#board' && goStep(s.to)"
          ><span class="num">0{{ i + 1 }}</span
          ><span
            >{{ s.name }}<small>{{ s.desc }}</small></span
          ><el-icon><Right /></el-icon
        ></router-link>
      </nav>
      <p v-if="USE_MOCK" class="demo-note">
        当前为交互演示 · 数据不会保存到服务器，刷新后恢复示例。
      </p>
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
          <el-button type="primary" :disabled="!relief" @click="confirmRelief"
            >确认调整</el-button
          >
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import ProgressRing from '../components/ProgressRing.vue'
import { checkinHistory, daysUntil, taskProgress } from '../utils/studyProgress'
import { ElMessage } from 'element-plus'
import { dashboardApi, examApi, featureApi, focusApi, taskApi } from '../api'
import { useUserStore } from '../stores/user'
import {
  USE_MOCK,
  getToday,
  mockEmergency,
  mockMood,
  mockOverview,
  mockPressure,
  mockRelief,
  mockReview,
  mockTimeslots,
  mockTop3,
} from '../mock/dashboard'
import { examColor } from '../utils/subjectColor'

const userStore = useUserStore()
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
const review = ref(null)
const top3 = ref(null)
const timeslots = ref(null)
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

const flowSteps = [
  {
    icon: 'Upload',
    name: '上传资料',
    desc: '历年题、笔记、老师重点',
    to: '/materials',
  },
  {
    icon: 'EditPen',
    name: '填写目标',
    desc: '一句话说清你的情况',
    to: '/analysis',
  },
  {
    icon: 'MagicStick',
    name: '生成计划',
    desc: 'AI 拆出每天的任务',
    to: '/analysis',
  },
  {
    icon: 'CircleCheck',
    name: '每日打卡',
    desc: '跟着计划稳步推进',
    to: '#board',
  },
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
const priorityItems = computed(() =>
  (top3.value?.items || []).filter((item) =>
    tasks.value.some((t) => t.id === item.task_id && !t.is_done),
  ),
)
const taskTabs = computed(() => [
  {
    key: 'today',
    label: '今日待办',
    count: tasks.value.filter((t) => !t.is_done && t.plan_date <= getToday())
      .length,
  },
  {
    key: 'next',
    label: '接下来',
    count: tasks.value.filter((t) => !t.is_done && t.plan_date > getToday())
      .length,
  },
  { key: 'done', label: '已完成', count: overall.value.done },
  { key: 'all', label: '全部', count: overall.value.total },
])
const visibleTasks = computed(() =>
  tasks.value
    .filter(
      (t) =>
        taskFilter.value === 'all' ||
        (taskFilter.value === 'done'
          ? t.is_done
          : !t.is_done &&
            (taskFilter.value === 'next'
              ? t.plan_date > getToday()
              : t.plan_date <= getToday())),
    )
    .sort(
      (a, b) =>
        a.plan_date.localeCompare(b.plan_date) || a.priority - b.priority,
    ),
)
const emptyTaskTitle = computed(
  () =>
    ({
      today: '今日待办已清空，做得不错',
      next: '还没有后续任务',
      done: '你的第一次打卡，从这里开始',
      all: '还没有复习任务',
    })[taskFilter.value],
)

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
  const targets = [pressure, mood, review, top3, timeslots]
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
    featureApi.review(),
    featureApi.top3(),
    featureApi.timeslots(),
  ])
  if (request === featureRequest) applyFeatures(results)
}

const load = async () => {
  if (refreshing.value) return
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
      review.value = structuredClone(mockReview)
      top3.value = structuredClone(mockTop3)
      timeslots.value = structuredClone(mockTimeslots)
      // 预览态：番茄钟用本地假数据
      focusData.value = {
        total_minutes: 75,
        goal_minutes: 120,
        achieved: false,
        session_count: 3,
        by_exam: [],
      }
      goalInput.value = 120
      weekFocus.value = data.extras.focus_minutes
    } else {
      // —— 真实接口 ——
      const [overview, allTasks, examDetails] = await Promise.all([
        dashboardApi.overview(),
        taskApi.list(),
        examApi.list(),
      ])
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
  if (route.hash === '#board') goStep('#board')
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

const saveGoal = async () => {
  if (USE_MOCK) {
    focusData.value.goal_minutes = goalInput.value
    focusData.value.achieved =
      goalInput.value > 0 && focusData.value.total_minutes >= goalInput.value
    ElMessage.success('目标已保存')
    return
  }
  await focusApi.setGoal({ target_minutes: goalInput.value })
  focusData.value = await focusApi.today()
  ElMessage.success('目标已保存')
}

const goStep = (to) => {
  if (to === '#board') {
    document
      .getElementById('board')
      ?.scrollIntoView({
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
  clearInterval(focusTimerId)
})
</script>

<style scoped>
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
.hero-footnote {
  display: flex;
  gap: 12px;
  align-items: center;
  color: #aab5a5;
  font-size: 10px;
  letter-spacing: 0.06em;
}
.hero-footnote i {
  width: 3px;
  height: 3px;
  background: #728172;
  border-radius: 50%;
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
.work-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  gap: 24px;
  align-items: start;
}
.work-main,
.work-aside {
  min-width: 0;
  display: grid;
  gap: 24px;
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
.section-note {
  max-width: 120px;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.7;
  text-align: right;
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
.priority-panel {
  border-bottom: 1px solid var(--line);
  padding: 0 0 22px;
}
.priority-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 10px;
}
.priority-list li {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 16px;
  background: #e8e5d8;
  border: 1px solid transparent;
  border-radius: 8px;
}
.priority-list li:first-child {
  border-color: #dfb9a5;
  background: #f3e0d3;
}
.priority-number {
  align-self: flex-start;
  font: 500 22px/1.3 var(--font-num);
  color: var(--coral-deep);
}
.priority-copy {
  flex: 1;
  min-width: 0;
}
.priority-copy b {
  font-size: 13px;
  line-height: 1.7;
}
.priority-copy p {
  margin: 5px 0 0;
  font-size: 10px;
  color: var(--ink-2);
  line-height: 1.7;
}
.priority-copy p span,
.priority-copy small {
  font-size: 10px;
  color: var(--muted);
}
.duration {
  display: grid;
  gap: 2px;
  text-align: right;
  font: 500 20px var(--font-num);
}
.duration small {
  font: 400 10px var(--font-sans);
  color: var(--muted);
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
.task-toolbar {
  border-bottom: 1px solid var(--line);
  margin-bottom: 8px;
}
.task-tabs {
  display: flex;
  gap: 20px;
  overflow-x: auto;
}
.task-tabs button {
  padding: 0 0 13px;
  border: 0;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  background: transparent;
  font: 500 12px var(--font-sans);
  white-space: nowrap;
  cursor: pointer;
}
.task-tabs button span {
  margin-left: 5px;
  font: 500 10px var(--font-num);
}
.task-tabs button.active {
  color: var(--ink-1);
  border-bottom-color: var(--coral);
  font-weight: 700;
}
.task-list {
  padding: 0;
  margin: 0;
  list-style: none;
  max-height: 590px;
  overflow-y: auto;
}
.task-list li {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 19px 0;
  border-bottom: 1px dashed var(--line);
}
.task-list li:last-child {
  border-bottom: 0;
}
.task-list .el-checkbox {
  height: 24px;
}
.task-copy {
  flex: 1;
  min-width: 0;
}
.task-copy b {
  font-size: 13px;
  line-height: 1.8;
  font-weight: 600;
}
.task-list .done .task-copy b {
  text-decoration: line-through;
  color: var(--muted);
}
.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 5px;
  font-size: 10px;
  line-height: 1.7;
  color: var(--muted);
}
.subject-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--ink-2);
}
.subject-label i,
.subject-progress i,
.exam-info i {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 2px;
  flex-shrink: 0;
}
.task-meta .overdue,
.task-meta .high-priority {
  color: var(--coral-deep);
}
.high-priority {
  padding: 0 4px;
  background: var(--coral-soft);
  border-radius: 2px;
}
.task-state {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--green);
  padding-top: 6px;
}
.task-footer {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  border-top: 1px solid var(--line);
  padding-top: 15px;
  margin-top: 5px;
  font-size: 10px;
  color: var(--muted);
}
.quiet-empty,
.task-empty {
  padding: 20px 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}
.task-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
  padding: 34px 10px;
}
.task-empty b {
  color: var(--ink-2);
}
.task-empty p {
  margin: 0;
  max-width: 280px;
}
#board {
  scroll-margin-top: 150px;
}
.overall-ring {
  width: 180px;
  margin: 0 auto;
}
.progress-number {
  font: 700 46px/1 var(--font-num);
  letter-spacing: -0.06em;
  font-variant-numeric: tabular-nums;
}
.progress-number small {
  font-size: 19px;
  margin-left: 4px;
}
.ring-caption {
  font-size: 10px;
  color: var(--muted);
  margin-top: 10px;
}
.progress-tally {
  text-align: center;
  font-size: 11px;
  color: var(--ink-2);
  margin: 6px 0 22px;
}
.progress-tally b {
  font: 700 15px var(--font-num);
}
.progress-tally span {
  color: var(--muted);
}
.subject-progress + .subject-progress {
  margin-top: 14px;
}
.subject-progress > div:first-child {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 10px;
  margin-bottom: 6px;
}
.subject-progress span {
  display: flex;
  align-items: center;
  gap: 6px;
}
.subject-progress b {
  font: 500 10px var(--font-num);
  color: var(--muted);
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
.goal-settings {
  margin-top: 14px;
  color: var(--muted);
  font-size: 10px;
}
.goal-settings summary {
  cursor: pointer;
}
.goal-settings > div {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.goal-settings > small {
  display: block;
  margin-top: 5px;
}
.focus-hint {
  font-size: 11px;
  color: var(--muted);
}
.streak-panel {
  padding: 0 4px;
}
.streak-panel > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.streak-panel b {
  font-size: 12px;
}
.streak-panel b .num {
  font-size: 18px;
  color: var(--coral-deep);
}
.streak-panel > div:first-child > span {
  font-size: 10px;
  color: var(--muted);
}
.week-dots {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
  margin-top: 18px;
}
.week-day {
  display: grid;
  gap: 9px;
  text-align: center;
  font-size: 10px;
  color: var(--muted);
}
.week-day i {
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  max-width: 30px;
  width: 100%;
  margin: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
  font-style: normal;
}
.week-day.on i {
  color: var(--bg-card);
  background: var(--green);
  border-color: var(--green);
}
.week-day.today i {
  outline: 1px solid var(--coral);
  outline-offset: 3px;
}
.week-day.future {
  opacity: 0.6;
}
.care-grid,
.resources-grid {
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
.review-list,
.slots-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.review-list li {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}
.review-list li:last-child,
.slots-list li:last-child {
  border: 0;
}
.review-order {
  font: 500 12px var(--font-num);
  color: var(--muted);
}
.review-list li > div {
  flex: 1;
  min-width: 0;
}
.review-list b {
  font-size: 12px;
}
.review-list p {
  margin: 4px 0 9px;
  font-size: 10px;
  line-height: 1.6;
  color: var(--muted);
}
.review-list strong {
  font-size: 20px;
}
.review-list small {
  font-size: 10px;
}
.review-bar {
  height: 3px;
  background: var(--bg-soft);
}
.review-bar i {
  display: block;
  height: 100%;
  background: var(--coral);
}
.reference-note {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.8;
  margin: 18px 0 0;
}
.slots-list li {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 20px;
  border-bottom: 1px solid var(--line);
  padding: 18px 0;
}
.slots-list b {
  display: block;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.7;
}
.slots-list span {
  display: block;
  font-size: 10px;
  color: var(--muted);
  line-height: 1.7;
  margin-top: 5px;
}
.slot-time span {
  font-family: var(--font-num);
}
.study-path {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-top: 1px solid var(--line);
  padding-top: 22px;
  gap: 22px;
}
.study-path a {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--ink-2);
  font-size: 12px;
  text-decoration: none;
}
.study-path a > .num {
  font-size: 23px;
  color: #a9ad9e;
}
.study-path small {
  display: block;
  font-size: 9px;
  color: var(--muted);
  margin-top: 4px;
  line-height: 1.6;
}
.study-path .el-icon {
  margin-left: auto;
  color: var(--muted);
}
.study-path a:hover {
  color: var(--coral-deep);
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
  .work-grid {
    grid-template-columns: minmax(0, 1fr) 280px;
    gap: 20px;
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
  .priority-list li {
    gap: 10px;
    padding: 14px 12px;
  }
  .task-tabs {
    gap: 12px;
  }
}
@media (max-width: 800px) {
  .work-grid {
    grid-template-columns: 1fr;
  }
  .work-aside {
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }
  .streak-panel {
    grid-column: 1 / -1;
  }
  .week-dots {
    max-width: 360px;
  }
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
  .hero-footnote {
    font-size: 9px;
    gap: 8px;
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
  .care-grid,
  .resources-grid {
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
  .study-path {
    grid-template-columns: 1fr 1fr;
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
  .hero-footnote {
    font-size: 9px;
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
  .work-aside,
  .care-grid,
  .resources-grid {
    grid-template-columns: 1fr;
  }
  .streak-panel {
    grid-column: auto;
    padding: 6px 2px;
  }
  .panel {
    padding: 20px 18px;
    border-radius: 10px;
  }
  .section-head h2 {
    font-size: 17px;
  }
  .section-note {
    max-width: 100px;
    font-size: 9px;
  }
  .priority-copy p span {
    display: block;
  }
  .priority-copy b {
    font-size: 12px;
  }
  .priority-number {
    font-size: 20px;
  }
  .duration {
    font-size: 18px;
  }
  .priority-check.el-button {
    width: 26px;
    height: 26px;
  }
  .priority-list li {
    gap: 10px;
    padding: 15px 12px;
  }
  .task-tabs {
    justify-content: space-between;
    gap: 8px;
  }
  .task-tabs button {
    font-size: 11px;
  }
  .task-copy b {
    font-size: 12px;
  }
  .task-state {
    display: none;
  }
  .task-meta {
    gap: 5px 10px;
  }
  .task-footer {
    font-size: 9px;
  }
  .focus-clock {
    margin: 24px 0;
    font-size: 60px;
  }
  .overall-ring {
    width: 190px;
  }
  .study-path {
    gap: 24px 16px;
  }
  .study-path a {
    gap: 8px;
    font-size: 11px;
  }
  .study-path a > .num {
    font-size: 20px;
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
  .slots-list li {
    grid-template-columns: 85px 1fr;
    gap: 12px;
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
</style>
