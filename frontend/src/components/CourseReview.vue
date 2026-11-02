<template>
  <div v-loading="loading" class="course-review">
    <p v-if="error" role="alert">{{ error }} <el-button text @click="load">重试</el-button></p>
    <p v-if="review?.note">{{ review.note }}</p>
    <ol v-if="review?.items?.length">
      <li v-for="(item,i) in review.items" :key="`${item.kind}-${item.collection_id||i}`">
        <el-tag size="small">{{ item.source || '知识点' }}</el-tag> <b>{{ item.name }}</b>
        <span v-if="item.kind === 'knowledge'"> · 权重 {{ (item.weight*100).toFixed(0) }}%</span>
        <p>{{ item.basis }}</p>
      </li>
    </ol>
    <section v-if="review?.unassigned?.length"><h3>未分类题目</h3><p>这些题目没有科目记录，单独列出供你核对。</p>
      <ul><li v-for="item in review.unassigned" :key="item.collection_id"><b>{{ item.name }}</b><p>{{ item.basis }}</p></li></ul>
    </section>
    <router-link to="/materials">查看资料与错题本 ↗</router-link>
    <p class="reference-note">分析知识点仅供复习参考，请结合教材和课堂要求判断。</p>
  </div>
</template>
<script setup>
import { ref, watch } from 'vue'
import { featureApi } from '../api'
import { USE_MOCK, mockReview } from '../mock/dashboard'
const props=defineProps({examId:{type:Number,required:true}})
const loading=ref(false), review=ref(null), error=ref('')
async function load(){
  const id=props.examId
  loading.value=true;error.value=''
  try { const result=USE_MOCK ? structuredClone(mockReview) : await featureApi.review({exam_id:id});if(id===props.examId) review.value=result }
  catch { if(id===props.examId) error.value='回顾内容加载失败，请重试。' }
  finally { if(id===props.examId) loading.value=false }
}
watch(()=>props.examId,load,{immediate:true})
</script>
<style scoped>
.course-review{min-height:100px;max-height:65vh;overflow:auto;overflow-wrap:anywhere}.course-review ol,.course-review ul{padding-left:24px}.course-review li{padding:12px 0;border-bottom:1px solid var(--line)}.course-review p{white-space:pre-wrap;line-height:1.7}.reference-note{font-size:12px;color:var(--ink-3)}
</style>
