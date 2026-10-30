<template>
  <div class="pressure-records">
    <p>上方为当前实时值，随任务和考试安排更新。</p>
    <div v-if="pressure.daily_snapshot" class="daily-pressure" aria-label="今日自动压力记录">
      <span>今日自动记录 <b>{{ pressure.daily_snapshot.score }}</b> / 100</span>
      <small>{{ clock(pressure.daily_snapshot.computed_at) }} · {{ sourceName(pressure.daily_snapshot.source) }}</small>
    </div>
    <p v-else role="status">今日自动记录尚未生成。后台每分钟检查，00:05 后自动记录，启动会补当天缺失记录。</p>
    <button class="pressure-record-link" @click="openHistory">查看近7日记录 ↗</button>
    <el-dialog v-model="visible" title="每日压力记录" width="min(640px, calc(100vw - 32px))" align-center>
      <p class="record-note">北京时间每天00:05后自动记录，无需打开页面。每日记录保留计算当时的状态，当前实时值可能不同。</p>
      <p v-if="USE_MOCK" class="record-note">当前为示例记录，刷新恢复；真实模式由后端自动保存。</p>
      <p v-if="loading" role="status">正在读取每日记录…</p>
      <div v-else-if="error" role="alert"><p>{{ error }}</p><el-button @click="loadHistory">重试读取</el-button></div>
      <template v-else-if="history">
        <div v-if="history.items.length" class="record-table">
          <table><thead><tr><th>日期</th><th>压力</th><th>记录时间 / 来源</th></tr></thead>
            <tbody><tr v-for="record in history.items" :key="record.record_date"><td>{{ record.record_date }}</td><td><b>{{ record.score }}</b> · {{ record.level }}</td><td>{{ clock(record.computed_at) }}<br /><small>{{ sourceName(record.source) }}</small></td></tr></tbody>
          </table>
        </div>
        <p v-else>近7天尚无自动记录，后台运行后会自动保存。</p>
        <p v-if="history.missing_dates.length" class="record-note">以下日期无记录：{{ history.missing_dates.join('、') }}。停机或开始使用前的日期不会用当前状态补造历史分数。</p>
        <p class="record-note">{{ history.note }}</p>
      </template>
      <template #footer><el-button @click="visible = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { featureApi } from '../api'
import { USE_MOCK, mockPressureHistory } from '../mock/dashboard'

defineProps({pressure:{type:Object,required:true}})
const visible=ref(false), loading=ref(false), error=ref(''), history=ref(null)
let request=0
const sourceName=value=>value==='startup'?'启动补记':'每日自动'
const clock=value=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})
async function loadHistory(){
  const current=++request
  loading.value=true;error.value='';history.value=null
  try {
    const result=USE_MOCK?structuredClone(mockPressureHistory):await featureApi.pressureHistory({days:7})
    if(current===request)history.value=result
  } catch {if(current===request)error.value='每日记录暂时无法读取，请重试。'}
  finally {if(current===request)loading.value=false}
}
function openHistory(){visible.value=true;loadHistory()}
onBeforeUnmount(()=>{request++})
</script>

<style scoped>
.pressure-records { padding:14px 0 8px; border-top:1px solid var(--line); margin-top:14px; font-size:12px; }
.pressure-records p { line-height:1.8; color:var(--ink-3); margin:0 0 10px; }
.daily-pressure { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:6px 14px; margin-bottom:10px; }
.daily-pressure small { color:var(--ink-3); }
.daily-pressure b { font-family:var(--font-num); color:var(--ink-1); }
.pressure-record-link { font:inherit; padding:0; border:0; color:var(--coral-deep); background:none; cursor:pointer; text-decoration:underline; text-underline-offset:4px; }
.record-table { overflow:auto; max-height:45vh; }
table { width:100%; border-collapse:collapse; font-size:12px; text-align:left; }
th, td { padding:12px 6px; border-bottom:1px solid var(--line); }
td:first-child { white-space:nowrap; font-variant-numeric:tabular-nums; }
td small { color:var(--ink-3); }
.pressure-records .record-note { font-size:12px; line-height:1.8; color:var(--ink-3); margin:10px 0; overflow-wrap:anywhere; }
</style>
