<template>
  <section
    id="board"
    class="workspace"
    :class="`pane-${pane}`"
    aria-labelledby="workspace-title"
    tabindex="-1"
  >
    <header class="workspace-head">
      <div class="workspace-title">
        <span class="eyebrow">TODAY / 从一件事开始</span>
        <h2 id="workspace-title">今日复习</h2>
      </div>
      <div class="daily-stat">
        <b
          >{{ doneToday }}<small> / {{ allToday.length }}</small></b
        ><span>今日任务完成</span>
      </div>
      <div class="daily-stat">
        <b
          >{{ hours(focus.total_minutes)
          }}<small> / {{ hours(focus.goal_minutes) }} h</small></b
        ><span>今日专注 · 全科累计</span>
      </div>
      <div class="daily-stat streak-stat">
        <b>{{ history.streak }}<small> 天</small></b
        ><span
          >连续打卡
          <i
            v-for="day in history.week"
            :key="day.date"
            :class="{ checked: day.done }"
            :title="`${day.date} ${day.done ? '已打卡' : '无打卡'}`"
          ></i
        ></span>
      </div>
      <button class="text-button budget-button" data-tour="budget" @click="$emit('budget')">
        时间与排程 <span>↗</span>
      </button>
    </header>
    <div class="direction-strip" aria-label="今日重点方向">
      <span class="direction-label">今日方向</span>
      <button
        v-for="(item, index) in directions"
        :key="item.id"
        @click="$emit('select', item)"
        :title="item.title"
      >
        <b>0{{ index + 1 }}</b
        ><span>{{ item.exam }} · {{ item.title }}</span>
      </button>
      <span v-if="!directions.length" class="quiet">{{
        tasks.length
          ? '今天的任务已完成，给自己留一点休息时间。'
          : '先录入考试，再生成你的复习计划。'
      }}</span>
    </div>
    <nav class="mobile-panes" aria-label="学习区切换">
      <button data-tour="tasks-mobile" :aria-pressed="pane === 'tasks'" @click="switchPane('tasks')">
        任务清单 · {{ due.length }}</button
      ><button data-tour="focus-mobile" :aria-pressed="pane === 'focus'" @click="switchPane('focus')">
        {{ running ? `专注中 ${clock}` : '番茄钟与资料' }}
      </button>
    </nav>
    <div class="workspace-body">
      <section class="task-workbench" aria-label="复习任务清单">
        <div class="task-tools" data-tour="tasks">
          <h3>
            任务清单 <small>{{ visible.length }}</small>
          </h3>
          <div class="task-filters" role="group" aria-label="任务范围">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              :aria-pressed="filter === tab.key"
              @click="filter = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>
        <div class="allocation" aria-label="今日各科计划时间">
          <div class="allocation-caption">
            <span
              >今日计划 {{ duration(planned) }}
              <small>／全科预算 {{ duration(budget) }}</small></span
            ><strong :class="{ over: planned > budget }">{{
              planned > budget
                ? `超出 ${duration(planned - budget)}`
                : '各科一起安排'
            }}</strong>
          </div>
          <div class="allocation-bar">
            <span
              v-for="subject in allocation"
              :key="subject.id"
              :style="{ flex: subject.minutes, background: color(subject.id) }"
              :title="`${subject.name} ${duration(subject.minutes)}`"
            ></span
            ><span
              v-if="planned < budget"
              class="free-time"
              :style="{ flex: budget - planned }"
              title="可用余量"
            ></span>
          </div>
          <div class="allocation-legend">
            <span v-for="subject in allocation" :key="subject.id"
              ><i :style="{ background: color(subject.id) }"></i
              >{{ subject.name }} {{ duration(subject.minutes) }}</span
            ><button
              v-if="planned > budget"
              class="text-button"
              @click="$emit('budget')"
            >
              调整全科计划 ↗
            </button>
          </div>
        </div>
        <div
          class="task-scroll"
          tabindex="0"
          aria-label="任务列表，可在此区域滚动"
        >
          <div v-if="!visible.length" class="empty-tasks">
            <el-icon :size="34"><CircleCheck /></el-icon>
            <h3>
              {{
                filter === 'done'
                  ? '还没有完成记录'
                  : filter === 'next'
                    ? '没有后续任务'
                    : due.length
                      ? '此范围没有任务'
                      : tasks.length
                        ? '今天的任务已完成'
                        : '从第一门考试开始'
              }}
            </h3>
            <p>
              {{
                tasks.length
                  ? '可以查看其他范围，或去课程管理补充任务。'
                  : '录入全部考试、设置每天的总时间，再上传各科资料。'
              }}
            </p>
            <router-link :to="tasks.length ? '/exams' : '/analysis'"
              >{{
                tasks.length ? '管理课程与任务' : '生成复习计划'
              }}
              ↗</router-link
            >
          </div>
          <ul v-else class="work-task-list">
            <li
              v-for="task in visible"
              :key="task.id"
              :class="{
                selected: selected?.id === task.id,
                done: task.is_done,
              }"
            >
              <el-checkbox
                :model-value="task.is_done"
                :disabled="pendingIds.has(task.id)"
                :aria-label="`${task.is_done ? '撤销' : '完成'}${task.title}`"
                @change="$emit('toggle', task)"
              />
              <button class="task-select" @click="$emit('select', task)">
                <strong>{{ task.title }}</strong
                ><span
                  ><i :style="{ background: color(task.exam_id) }"></i
                  >{{ task.exam }}<em>{{ duration(task.estimated_minutes) }}</em
                  ><small
                    :class="{ late: task.plan_date < today && !task.is_done }"
                    >{{
                      task.plan_date < today
                        ? '逾期待处理'
                        : task.plan_date === today
                          ? '今天'
                          : task.plan_date.slice(5)
                    }}</small
                  ><small>{{ deadline(task.exam_id) }}</small></span
                >
              </button>
              <span v-if="pendingIds.has(task.id)" class="task-saving"
                >保存中</span
              ><button
                v-else-if="!task.is_done"
                class="row-focus"
                :aria-label="`专注复习${task.title}`"
                @click="start(task)"
              >
                <el-icon><VideoPlay /></el-icon><span>专注</span></button
              ><span v-else class="task-saving">已完成</span>
            </li>
          </ul>
        </div>
        <footer class="list-footer">
          <span>{{ due.length }} 项待办 · 预计 {{ duration(remaining) }}</span
          ><span>勾选完成，点击任务查看复习入口</span>
        </footer>
      </section>
      <aside class="focus-workbench" aria-label="专注与当前任务">
        <div class="current-task">
          <span class="eyebrow">{{ running ? '正在专注' : '当前选择' }}</span>
          <h3>{{ selected?.title || '选择一个任务，开始专注' }}</h3>
          <p>
            {{
              selected
                ? `${selected.exam} · ${deadline(selected.exam_id)}`
                : '从左侧任务清单选择，也可以自由计时。'
            }}
          </p>
        </div>
        <slot name="focus"></slot>
        <div class="task-resources">
          <router-link
            :to="{
              path: '/materials',
              query: selected ? { exam: selected.exam_id } : {},
            }"
            ><el-icon><FolderOpened /></el-icon>复习资料 ↗</router-link
          ><router-link
            :to="{
              path: '/analysis',
              query: selected ? { exam: selected.exam_id } : {},
            }"
            ><el-icon><Reading /></el-icon>考点与自测 ↗</router-link
          >
        </div>
        <p class="workspace-note">专注计入学习时长，任务完成后再打卡。</p>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { examColor } from '../utils/subjectColor'
import { daysUntil } from '../utils/studyProgress'
const props = defineProps({
  tasks: Array,
  exams: Array,
  priorities: Array,
  today: String,
  history: Object,
  focus: Object,
  budget: Number,
  selected: Object,
  pendingIds: Set,
  running: Boolean,
  clock: String,
})
const emit = defineEmits(['select', 'start', 'toggle', 'budget', 'enter'])
const filter = ref('today'),
  pane = ref('tasks')
const due = computed(() =>
  props.tasks.filter((t) => !t.is_done && t.plan_date <= props.today),
)
const allToday = computed(() =>
  props.tasks.filter((t) => t.plan_date === props.today),
)
const doneToday = computed(() => allToday.value.filter((t) => t.is_done).length)
const planned = computed(() =>
  props.tasks
    .filter(
      (t) =>
        t.plan_date === props.today ||
        (!t.is_done && t.plan_date < props.today),
    )
    .reduce((n, t) => n + t.estimated_minutes, 0),
)
const remaining = computed(() =>
  due.value.reduce((n, t) => n + t.estimated_minutes, 0),
)
const tabs = [
  { key: 'today', label: '今日待办' },
  { key: 'next', label: '接下来' },
  { key: 'done', label: '已完成' },
  { key: 'all', label: '全部' },
]
const visible = computed(() =>
  props.tasks
    .filter(
      (t) =>
        filter.value === 'all' ||
        (filter.value === 'done'
          ? t.is_done
          : !t.is_done &&
            (filter.value === 'next'
              ? t.plan_date > props.today
              : t.plan_date <= props.today)),
    )
    .sort(
      (a, b) =>
        Number(a.is_done) - Number(b.is_done) ||
        a.plan_date.localeCompare(b.plan_date) ||
        a.priority - b.priority,
    ),
)
const directions = computed(() => {
  const order = props.priorities?.map((p) => p.task_id) || []
  return [...due.value]
    .sort((a, b) => {
      const ai = order.indexOf(a.id),
        bi = order.indexOf(b.id)
      return (
        (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi) || a.priority - b.priority
      )
    })
    .slice(0, 3)
})
const allocation = computed(() => {
  const map = new Map()
  props.tasks
    .filter(
      (t) =>
        t.plan_date === props.today ||
        (!t.is_done && t.plan_date < props.today),
    )
    .forEach((t) => {
      const row = map.get(t.exam_id) || {
        id: t.exam_id,
        name: t.exam,
        minutes: 0,
      }
      row.minutes += t.estimated_minutes
      map.set(t.exam_id, row)
    })
  return [...map.values()]
})
const color = (id) => examColor(props.exams.find((e) => e.id === id)).color
const hours = (minutes) => Number(((minutes || 0) / 60).toFixed(2))
const duration = (minutes) =>
  minutes >= 60
    ? `${Math.floor(minutes / 60)}小时${minutes % 60 ? `${minutes % 60}分` : ''}`
    : `${minutes}分钟`
const deadline = (id) => {
  const exam = props.exams.find((e) => e.id === id)
  if (!exam) return '考试待设置'
  const n = daysUntil(exam.exam_date, props.today)
  return n < 0 ? '考试已结束' : n === 0 ? '今天考试' : `${n}天后考试`
}
const start = (task) => {
  emit('start', task)
  pane.value = 'focus'
  emit('enter')
}
const switchPane = (value) => {
  pane.value = value
  emit('enter')
}
watch(
  () => props.running,
  (value) => {
    if (value) pane.value = 'focus'
  },
)
</script>

<style scoped>
.workspace {
  --workspace-offset: 100px;
  scroll-margin-top: var(--workspace-offset);
  height: calc(100dvh - var(--workspace-offset) - 18px);
  max-height: 850px;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1.5px solid var(--ink-1);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 4px 4px 0 rgba(12, 22, 20, 0.09);
  outline: none;
}
.workspace:focus-visible {
  outline: 3px solid var(--coral);
}
.workspace-head {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.eyebrow {
  font-size: 9px;
  letter-spacing: 0.08em;
  color: var(--ink-3);
}
h2,
h3,
p {
  margin: 0;
}
.workspace-title {
  margin-right: auto;
}
h2 {
  font-size: 25px;
  margin-top: 3px;
}
.daily-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  white-space: nowrap;
}
.daily-stat b {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 25px;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.daily-stat small {
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-3);
}
.daily-stat > span {
  font-size: 10px;
  color: var(--ink-3);
}
.streak-stat i {
  display: inline-block;
  width: 5px;
  height: 5px;
  margin: 0 1px;
  background: var(--line);
  border-radius: 2px;
  vertical-align: middle;
}
.streak-stat i.checked {
  background: #35554c;
}
.text-button {
  border: 0;
  background: transparent;
  color: var(--coral-deep);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  padding: 3px;
}
.budget-button {
  padding-left: 12px;
  border-left: 1px solid var(--line);
}
button {
  font-family: inherit;
}
button:focus-visible,
a:focus-visible {
  outline: 2px solid var(--coral-deep);
  outline-offset: 3px;
}
.direction-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 22px;
  background: #edece1;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  min-height: 45px;
}
.direction-label {
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}
.direction-strip button {
  min-width: 0;
  flex: 1;
  text-align: left;
  border: 0;
  background: transparent;
  display: flex;
  gap: 7px;
  align-items: center;
  font-size: 10px;
  color: var(--ink-2);
  cursor: pointer;
  padding: 3px 6px;
  border-left: 1px solid #d0d2c6;
}
.direction-strip button:hover {
  color: var(--coral-deep);
}
.direction-strip button b {
  font-family: 'Space Grotesk';
  color: var(--coral-deep);
}
.direction-strip button span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.quiet {
  font-size: 11px;
  color: var(--ink-3);
}
.workspace-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 278px;
  flex: 1;
  min-height: 0;
}
.task-workbench {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.task-tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 17px 20px 12px;
  gap: 12px;
}
.task-tools h3 {
  font-size: 17px;
  white-space: nowrap;
}
.task-tools h3 small {
  font-size: 11px;
  color: var(--ink-3);
  margin-left: 4px;
}
.task-filters {
  display: flex;
  gap: 3px;
}
.task-filters button {
  font-size: 10px;
  border: 0;
  background: transparent;
  color: var(--ink-3);
  padding: 6px 9px;
  border-radius: 5px;
  cursor: pointer;
  white-space: nowrap;
}
.task-filters button[aria-pressed='true'] {
  background: var(--ink-1);
  color: var(--bg-card);
}
.allocation {
  margin: 0 20px 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}
.allocation-caption {
  display: flex;
  gap: 8px;
  justify-content: space-between;
  font-size: 10px;
}
.allocation-caption small {
  color: var(--ink-3);
}
.allocation-caption strong {
  font-size: 9px;
  color: #35554c;
  font-weight: 500;
}
.allocation-caption strong.over {
  color: var(--coral-deep);
}
.allocation-bar {
  display: flex;
  gap: 3px;
  height: 5px;
  margin: 9px 0 7px;
  overflow: hidden;
  border-radius: 3px;
}
.allocation-bar > span {
  min-width: 0;
}
.allocation-bar .free-time {
  background: #e6e4d9;
}
.allocation-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 12px;
  font-size: 9px;
  color: var(--ink-3);
}
.allocation-legend i,
.task-select i {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 2px;
  margin-right: 4px;
}
.allocation-legend .text-button {
  font-size: 9px;
  padding: 0;
}
.task-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #b8beb3 transparent;
  padding: 0 12px 10px;
}
.task-scroll:focus-visible {
  outline: 2px solid var(--coral-deep);
  outline-offset: -3px;
}
.work-task-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.work-task-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid transparent;
  border-bottom-color: var(--line);
  padding: 14px 10px;
  transition:
    background 0.15s,
    border-color 0.15s;
}
.work-task-list li:hover {
  background: #efeee4;
}
.work-task-list li.selected {
  background: #e8eddf;
  border-color: #aab9a3;
  border-radius: 6px;
}
.task-select {
  flex: 1;
  min-width: 0;
  cursor: pointer;
  text-align: left;
  border: 0;
  background: transparent;
  padding: 2px 0;
  color: var(--ink-1);
}
.task-select strong {
  display: block;
  font-size: 15px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.task-select > span {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px 8px;
  margin-top: 5px;
  font-size: 11px;
  color: var(--ink-3);
}
.task-select i {
  margin-right: -4px;
}
.task-select em {
  font-style: normal;
}
.task-select small {
  font-size: 9px;
}
.task-select small.late {
  color: var(--coral-deep);
}
.work-task-list li.done strong {
  text-decoration: line-through;
  color: var(--ink-3);
}
.row-focus {
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 6px 9px;
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-card);
  color: var(--ink-2);
  font-size: 10px;
  cursor: pointer;
}
.row-focus:hover {
  border-color: var(--coral-deep);
  color: var(--coral-deep);
}
.task-saving {
  font-size: 10px;
  color: var(--ink-3);
}
.list-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 20px;
  border-top: 1px solid var(--line);
  font-size: 9px;
  color: var(--ink-3);
  flex-shrink: 0;
}
.empty-tasks {
  height: 100%;
  min-height: 150px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #35554c;
  text-align: center;
  padding: 24px;
}
.empty-tasks h3 {
  font-size: 17px;
}
.empty-tasks p,
.empty-tasks a {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.8;
}
.empty-tasks a {
  color: var(--coral-deep);
}
.focus-workbench {
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: thin;
  border-left: 1px solid var(--line);
  background: #eeeee3;
  padding: 18px;
  display: flex;
  flex-direction: column;
}
.current-task {
  padding-bottom: 10px;
}
.current-task h3 {
  font-size: 14px;
  line-height: 1.6;
  margin: 6px 0;
  overflow-wrap: anywhere;
}
.current-task p {
  font-size: 10px;
  color: var(--ink-3);
}
.task-resources {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: auto;
  padding-top: 14px;
}
.task-resources a {
  font-size: 10px;
  display: flex;
  gap: 5px;
  align-items: center;
  color: var(--ink-2);
  text-decoration: none;
  padding: 10px 0;
  border-top: 1px solid #ced3c4;
}
.task-resources a:hover {
  color: var(--coral-deep);
}
.workspace-note {
  font-size: 9px;
  color: var(--ink-3);
  margin-top: 8px;
  line-height: 1.7;
}
.mobile-panes {
  display: none;
}
@media (min-width: 761px) and (max-height: 650px) {
  .workspace {
    height: 560px;
  }
}
@media (max-width: 1100px) {
  .workspace {
    --workspace-offset: 140px;
  }
}
@media (max-width: 1000px) {
  .workspace-head {
    gap: 18px;
    padding: 16px;
  }
  .workspace-body {
    grid-template-columns: minmax(0, 1fr) 250px;
  }
  .task-tools {
    flex-wrap: wrap;
  }
  .daily-stat b {
    font-size: 22px;
  }
  .budget-button {
    font-size: 10px;
  }
  .workspace-title .eyebrow {
    display: none;
  }
}
@media (max-width: 760px) {
  .workspace {
    --workspace-offset: 139px;
    height: calc(100dvh - 154px);
    max-height: 820px;
    min-height: 460px;
  }
  .workspace-head {
    padding: 13px;
    gap: 12px;
    flex-wrap: wrap;
  }
  .workspace-title {
    flex: 1;
  }
  .workspace-title h2 {
    font-size: 21px;
  }
  .daily-stat {
    gap: 3px;
  }
  .daily-stat b {
    font-size: 19px;
  }
  .daily-stat small {
    font-size: 10px;
  }
  .daily-stat > span {
    font-size: 8px;
  }
  .streak-stat {
    display: flex;
  }
  .budget-button {
    order: 1;
    flex: 0 0 40%;
    padding: 0;
    text-align: right;
    border: 0;
    margin: 0;
  }
  .workspace-title {
    flex: 0 0 50%;
  }
  .daily-stat {
    order: 2;
    flex: 1;
  }
  .direction-strip {
    padding: 8px 12px;
    gap: 7px;
    min-height: 37px;
  }
  .direction-strip button {
    font-size: 9px;
  }
  .direction-strip button:nth-of-type(n + 3) {
    display: flex;
  }
  .direction-strip {
    overflow-x: auto;
    scrollbar-width: thin;
  }
  .direction-strip button {
    flex: 0 0 132px;
  }
  .direction-label {
    position: sticky;
    left: 0;
    background: #edece1;
  }
  .direction-label {
    font-size: 9px;
  }
  .mobile-panes {
    display: flex;
    padding: 8px 12px;
    gap: 8px;
    background: #eeeee3;
    border-bottom: 1px solid var(--line);
  }
  .mobile-panes button {
    flex: 1;
    padding: 8px;
    border: 0;
    background: transparent;
    font-size: 11px;
    border-radius: 5px;
    cursor: pointer;
  }
  .mobile-panes button[aria-pressed='true'] {
    background: var(--ink-1);
    color: var(--bg-card);
  }
  .workspace-body {
    display: flex;
    flex: 1;
    min-height: 0;
  }
  .task-workbench,
  .focus-workbench {
    width: 100%;
  }
  .pane-tasks .focus-workbench,
  .pane-focus .task-workbench {
    display: none;
  }
  .focus-workbench {
    border: 0;
    padding: 14px 20px;
  }
  .task-tools {
    padding: 12px 14px 9px;
    flex-wrap: nowrap;
  }
  .task-tools h3 {
    font-size: 14px;
  }
  .task-filters button {
    padding: 6px;
    font-size: 9px;
  }
  .allocation {
    margin: 0 14px 7px;
  }
  .task-scroll {
    padding: 0 6px 8px;
  }
  .work-task-list li {
    padding: 11px 8px;
    gap: 9px;
  }
  .task-select strong {
    font-size: 14px;
  }
  .task-select > span {
    font-size: 9px;
  }
  .row-focus {
    padding: 6px;
  }
  .row-focus span {
    display: none;
  }
  .list-footer {
    padding: 11px 14px;
    font-size: 9px;
  }
  .list-footer > span:last-child {
    display: none;
  }
  .current-task h3 {
    font-size: 13px;
  }
  .direction-strip button span {
    max-width: 100%;
  }
}
@media (prefers-reduced-motion: reduce) {
  * {
    scroll-behavior: auto !important;
    transition: none !important;
  }
}
</style>
