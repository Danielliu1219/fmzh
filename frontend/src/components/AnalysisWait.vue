<template>
  <div class="analysis-wait">
    <div class="activity-track" role="progressbar" :aria-label="statusText"><span /></div>
    <p class="wait-status" role="status">{{ statusText }}</p>
    <p class="wait-clock">已等待 <strong>{{ elapsedText }}</strong></p>
    <p class="wait-note">{{ kind === 'qa' ? '正文返回后逐步显示，完整回答会自动保存。' : '完整结果校验通过后自动保存。' }}</p>
    <p v-if="job?.progress?.first_content_seconds != null" class="wait-heartbeat">模型首段正文用时 {{ job.progress.first_content_seconds }} 秒<span v-if="job.progress.queue_seconds"> · 排队 {{ job.progress.queue_seconds }} 秒</span></p>
    <p v-if="job?.updatedAt" class="wait-heartbeat">最近一次状态更新：{{ heartbeatSeconds === 0 ? '刚刚' : `${heartbeatSeconds} 秒前` }}</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
const props = defineProps({ job: Object, kind: { type: String, default: 'analysis' } })
const now = ref(Date.now())
const timer = setInterval(() => { now.value = Date.now() }, 1000)
onBeforeUnmount(() => clearInterval(timer))
const elapsedSeconds = computed(() => Math.max(0, Math.floor((now.value - (props.job?.startedAt ?? now.value)) / 1000)))
const heartbeatSeconds = computed(() => Math.max(0, Math.floor((now.value - props.job.updatedAt) / 1000)))
const elapsedText = computed(() => elapsedSeconds.value < 60 ? `${elapsedSeconds.value} 秒` : `${Math.floor(elapsedSeconds.value / 60)} 分 ${elapsedSeconds.value % 60} 秒`)
const statusText = computed(() => {
  if (props.job?.status === 'running') {
    return ({ preparing: '正在准备本次输入', connecting: '正在连接模型服务', waiting: '上游已响应，等待模型输出', thinking: '模型正在思考', answering: '正在接收模型正文', finalizing: '正文已返回，正在校验并保存' })[props.job.progress?.stage] || '后台正在处理'
  }
  return ({ submitting: '正在提交任务', queued: '任务已提交，正在排队', succeeded: '结果已保存' })[props.job?.status] || '正在获取任务状态'
})
</script>

<style scoped>
.analysis-wait { width: min(520px, 75vw); max-width:100%; margin: 0 auto; }
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
