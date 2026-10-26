<template>
  <article class="source-excerpt">
    <h3>{{ reference.material_title || '原引用资料' }}</h3>
    <p v-if="reference.status === 'available'" class="source-meta">
      {{ reference.source_type }} · {{ reference.file_type?.toUpperCase() }} · {{ reference.location }}
    </p>
    <el-alert v-if="reference.status !== 'available'" :title="reference.note" type="warning" :closable="false" show-icon />
    <template v-else>
      <p class="source-method">{{ reference.note }}</p>
      <blockquote class="source-text"><span>{{ parts[0] }}</span><mark>{{ parts[1] }}</mark><span>{{ parts[2] }}</span></blockquote>
      <slot />
    </template>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { excerptParts } from '../utils/sourceEvidence.js'
const props = defineProps({ reference: { type: Object, required: true } })
const parts = computed(() => excerptParts(props.reference))
</script>

<style scoped>
.source-excerpt { padding: 16px 0; border-bottom: 1px solid var(--line); }
.source-excerpt h3 { font-size: 16px; line-height: 1.7; margin: 0; overflow-wrap: anywhere; }
.source-meta,.source-method { font-size: 12px; line-height: 1.8; color: var(--ink-3); }
.source-text { margin: 14px 0; padding: 16px; max-height: 360px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.9; border-left: 3px solid var(--coral); background: var(--bg-page); color: var(--ink-2); }
.source-text mark { color: var(--ink-1); background: #f7dfb6; padding: 2px 0; }
</style>
