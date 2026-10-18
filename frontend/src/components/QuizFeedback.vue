<template>
  <div class="quiz-feedback">
    <p v-if="item.subject || item.knowledge_point" class="feedback-context">{{ item.subject }}<span v-if="item.knowledge_point"> · {{ item.knowledge_point }}</span></p>
    <ul v-if="item.options?.length" class="feedback-options">
      <li v-for="(option, index) in item.options" :key="index">{{ typeof option === 'string' ? option : `${option.value}. ${option.label}` }}</li>
    </ul>
    <div v-if="item.answer != null" class="feedback-answers">
      <span>你的答案 <b>{{ answerLabel(item.submitted_answer, item) }}</b></span>
      <span>参考答案 <b>{{ answerLabel(item.answer, item) }}</b></span>
    </div>
    <p class="feedback-explanation">{{ item.analysis || item.raw || '暂无解析，可结合教材核对，或重新生成一轮自测。' }}</p>
  </div>
</template>
<script setup>
import { answerLabel } from '../utils/quiz'
defineProps({ item: { type: Object, required: true } })
</script>
<style scoped>
.quiz-feedback { font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; }
.feedback-context { color: var(--ink-3); margin: 0 0 12px; }
.feedback-options { padding-left: 20px; margin: 0 0 16px; color: var(--ink-2); }
.feedback-answers { display: flex; flex-wrap: wrap; gap: 10px 28px; padding: 12px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.feedback-answers b { color: var(--green, #35554c); margin-left: 8px; }
.feedback-explanation { color: var(--ink-2); white-space: pre-wrap; }
</style>
