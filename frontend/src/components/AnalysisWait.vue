<template>
  <div class="analysis-wait">
    <div class="activity-track" role="progressbar" :aria-label="statusText"><span /></div>
    <p class="wait-status" role="status">{{ statusText }}</p>
    <p class="wait-clock">已等待 <strong>{{ elapsedText }}</strong></p>
    <p class="wait-note">{{ elapsedSeconds >= 60 ? '仍在处理中，思考与生成完整方案可能需要数分钟。' : '处理期间会持续查询后台状态，请勿重复提交。' }}</p>
    <p v-if="job?.updatedAt" class="wait-heartbeat">最近一次状态更新：{{ heartbeatSeconds === 0 ? '刚刚' : `${heartbeatSeconds} 秒前` }}</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
const props = defineProps({ job: Object })
const now = ref(Date.now())
const timer = setInterval(() => { now.value = Date.now() }, 1000)
onBeforeUnmount(() => clearInterval(timer))
const elapsedSeconds = computed(() => Math.max(0, Math.floor((now.value - (props.job?.startedAt ?? now.value)) / 1000)))
const heartbeatSeconds = computed(() => Math.max(0, Math.floor((now.value - props.job.updatedAt) / 1000)))
const elapsedText = computed(() => elapsedSeconds.value < 60 ? `${elapsedSeconds.value} 秒` : `${Math.floor(elapsedSeconds.value / 60)} 分 ${elapsedSeconds.value % 60} 秒`)
const statusText = computed(() => ({ submitting: '正在提交分析任务', queued: '任务已提交，正在排队', running: '后台正在处理，等待模型生成完整方案', succeeded: '方案已返回，正在整理结果' })[props.job?.status] || '正在获取分析状态')
</script>

<style scoped>
.analysis-wait { width: min(520px, 75vw); margin: 0 auto; }
.activity-track { height: 6px; overflow: hidden; background: var(--border, #d9d4c3); border-radius: 4px; }
.activity-track span { display: block; width: 35%; height: 100%; background: var(--ink-1, #35554c); animation: waiting 1.8s ease-in-out infinite alternate; }
.wait-status { margin: 20px 0 10px; }
.wait-clock { margin: 10px 0; font-variant-numeric: tabular-nums; }
.wait-clock strong { font-size: 24px; }
.wait-note, .wait-heartbeat { color: var(--text-muted, #626b66); font-size: 13px; line-height: 1.7; }
.wait-heartbeat { font-size: 12px; }
@keyframes waiting { from { transform: translateX(-30%); } to { transform: translateX(215%); } }
@media (prefers-reduced-motion: reduce) { .activity-track span { animation: none; width: 100%; opacity: .45; } }
</style>
