<template>
  <div class="stats-page">
    <div class="page-head">
      <h2>学习统计</h2>
      <span class="head-sub">各科学习时长、任务完成率与历史学习记录（时长来自番茄钟专注打卡）</span>
      <el-radio-group v-model="rangeDays" :disabled="loading" @change="load">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="14">近 14 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
      </el-radio-group>
    </div>

    <!-- ===== 加载骨架 ===== -->
    <template v-if="loading">
      <div class="sk-tiles">
        <div v-for="i in 4" :key="i" class="sk-tile"><el-skeleton animated :rows="2" /></div>
      </div>
      <div class="sk-grid">
        <div class="sk-box"><el-skeleton animated :rows="6" /></div>
        <div class="sk-box"><el-skeleton animated :rows="6" /></div>
      </div>
      <div class="sk-box"><el-skeleton animated :rows="4" /></div>
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

      <!-- ===== 空状态 ===== -->
      <div v-if="!data.subjects.length" class="panel empty-box">
        <span class="empty-icon"><el-icon :size="26"><DataLine /></el-icon></span>
        <div class="empty-title">还没有学习记录</div>
        <div class="empty-sub">去首页用番茄钟专注一次，这里就会长出统计啦</div>
      </div>

      <template v-else>
        <section class="chart-row">
          <div class="panel chart-card">
            <div class="panel-head"><h2>各科学习时长</h2></div>
            <div ref="barRef" class="chart"></div>
          </div>
          <div class="panel chart-card">
            <div class="panel-head">
              <h2>学习时长趋势</h2>
              <span class="panel-sub">近 {{ data.range_days }} 天</span>
            </div>
            <div ref="trendRef" class="chart"></div>
          </div>
        </section>

        <section class="panel chart-card">
          <div class="panel-head"><h2>各科任务完成率</h2></div>
          <div ref="rateRef" class="chart chart-short"></div>
        </section>
      </template>

      <!-- ===== 历史学习记录报表 ===== -->
      <section class="panel">
        <div class="panel-head">
          <h2>历史学习记录</h2>
          <span class="panel-sub">{{ data.start_date }} ~ {{ data.end_date }}</span>
        </div>
        <el-table :data="reportRows" empty-text="该区间暂无学习记录" style="width: 100%">
          <el-table-column prop="date" label="日期" min-width="130" />
          <el-table-column label="学习时长" min-width="130">
            <template #default="{ row }"><span class="num">{{ row.minutes }}</span> 分钟</template>
          </el-table-column>
          <el-table-column label="任务（完成 / 计划）" min-width="150">
            <template #default="{ row }">{{ row.done }} / {{ row.total }}</template>
          </el-table-column>
          <el-table-column label="完成率" min-width="200">
            <template #default="{ row }">
              <el-progress :percentage="Math.round(row.rate * 100)" :stroke-width="10" color="#e66348" />
            </template>
          </el-table-column>
        </el-table>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { dashboardApi } from '../api'
import { USE_MOCK } from '../mock/dashboard'
import { mockStatsOverview } from '../mock/pages'

const CORAL = '#e66348'
const AXIS = '#8b9084'
const LINE = '#d9d4c3'
const TRACK = '#e4dfd0'

const loading = ref(true)
const error = ref('')
const rangeDays = ref(7)
const data = ref({
  range_days: 7,
  start_date: '',
  end_date: '',
  total_minutes: 0,
  total_tasks: 0,
  done_tasks: 0,
  rate: 0,
  subjects: [],
  days: [],
})

const barRef = ref(null)
const trendRef = ref(null)
const rateRef = ref(null)
let barChart = null
let trendChart = null
let rateChart = null

const kpiTiles = computed(() => {
  const d = data.value
  return [
    { label: '学习时长', value: `${d.total_minutes} 分`, sub: '窗口内总专注分钟', icon: 'Timer', color: 'var(--coral-deep)', soft: 'var(--coral-soft)' },
    { label: '任务完成', value: `${d.done_tasks} / ${d.total_tasks}`, sub: '已完成 / 全部任务', icon: 'CircleCheck', color: 'var(--green)', soft: 'var(--green-soft)' },
    { label: '任务完成率', value: `${Math.round(d.rate * 100)}%`, sub: '全部任务口径', icon: 'TrendCharts', color: 'var(--teal)', soft: 'var(--teal-soft)' },
    { label: '覆盖科目', value: `${d.subjects.length} 科`, sub: '有记录或任务', icon: 'Collection', color: 'var(--amber)', soft: 'var(--amber-soft)' },
  ]
})

// 最近在前
const reportRows = computed(() => [...data.value.days].reverse())

const renderBar = (subjects) => {
  if (!barRef.value) {
    barChart?.dispose()
    barChart = null
    return
  }
  if (!barChart) barChart = echarts.init(barRef.value)
  barChart.setOption(
    {
      grid: { left: 8, right: 32, top: 12, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${v} 分钟` },
      xAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: LINE } },
        splitLine: { lineStyle: { color: LINE } },
        axisLabel: { color: AXIS },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: subjects.map((s) => s.subject),
        axisLine: { lineStyle: { color: LINE } },
        axisTick: { show: false },
        axisLabel: { color: AXIS },
      },
      series: [
        {
          type: 'bar',
          barWidth: 16,
          itemStyle: { color: CORAL, borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', color: AXIS, formatter: '{c}' },
          data: subjects.map((s) => s.minutes),
        },
      ],
    },
    true,
  )
}

const renderTrend = (days) => {
  if (!trendRef.value) {
    trendChart?.dispose()
    trendChart = null
    return
  }
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  trendChart.setOption(
    {
      grid: { left: 8, right: 16, top: 12, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', valueFormatter: (v) => `${v} 分钟` },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: days.map((d) => d.date.slice(5)),
        axisLine: { lineStyle: { color: LINE } },
        axisLabel: { color: AXIS },
      },
      yAxis: {
        type: 'value',
        axisLine: { lineStyle: { color: LINE } },
        splitLine: { lineStyle: { color: LINE } },
        axisLabel: { color: AXIS },
      },
      series: [
        {
          type: 'line',
          smooth: true,
          symbolSize: 6,
          data: days.map((d) => d.minutes),
          lineStyle: { color: CORAL, width: 2 },
          itemStyle: { color: CORAL },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(230, 99, 72, 0.28)' },
              { offset: 1, color: 'rgba(230, 99, 72, 0)' },
            ]),
          },
        },
      ],
    },
    true,
  )
}

const renderRate = (subjects) => {
  if (!rateRef.value) {
    rateChart?.dispose()
    rateChart = null
    return
  }
  if (!rateChart) rateChart = echarts.init(rateRef.value)
  rateChart.setOption(
    {
      grid: { left: 8, right: 32, top: 12, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${v}%` },
      xAxis: {
        type: 'value',
        max: 100,
        axisLine: { lineStyle: { color: LINE } },
        splitLine: { lineStyle: { color: LINE } },
        axisLabel: { color: AXIS, formatter: '{value}%' },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: subjects.map((s) => s.subject),
        axisLine: { lineStyle: { color: LINE } },
        axisTick: { show: false },
        axisLabel: { color: AXIS },
      },
      series: [
        {
          type: 'bar',
          barWidth: 16,
          showBackground: true,
          backgroundStyle: { color: TRACK },
          itemStyle: { color: CORAL, borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', color: AXIS, formatter: '{c}%' },
          data: subjects.map((s) => Math.round(s.rate * 100)),
        },
      ],
    },
    true,
  )
}

const renderAll = () => {
  renderBar(data.value.subjects)
  renderTrend(data.value.days)
  renderRate(data.value.subjects)
}

// 重新加载会切回骨架屏，图表容器被销毁重建；旧实例必须一并丢弃，
// 否则 setOption 作用在已脱离文档的旧容器上，新容器一片空白。
const disposeCharts = () => {
  barChart?.dispose()
  trendChart?.dispose()
  rateChart?.dispose()
  barChart = trendChart = rateChart = null
}

const load = async () => {
  disposeCharts()
  loading.value = true
  error.value = ''
  try {
    if (USE_MOCK) {
      data.value = await mockStatsOverview(rangeDays.value)
    } else {
      data.value = await dashboardApi.statsOverview(rangeDays.value)
    }
  } catch (e) {
    error.value = e?.message || '网络异常，请稍后重试'
  } finally {
    loading.value = false
  }
  if (error.value) return
  // 等 v-else 分支把图表容器渲染出来后再 init
  await nextTick()
  renderAll()
}

const onResize = () => {
  barChart?.resize()
  trendChart?.resize()
  rateChart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.page-head h2 {
  margin: 0;
}
.head-sub {
  flex: 1;
  font-size: 13px;
  color: var(--ink-3);
}

/* —— 通用面板（纸片 + 墨线 + 硬阴影） —— */
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
  margin-top: 2px;
  font-size: 11px;
  color: var(--ink-3);
}

/* —— 图表 —— */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.chart-card {
  margin-bottom: 16px;
}
.chart {
  height: 300px;
  width: 100%;
}
.chart-short {
  height: 220px;
}

/* —— 空状态 —— */
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
  .chart-row,
  .sk-grid {
    grid-template-columns: 1fr;
  }
}
</style>
