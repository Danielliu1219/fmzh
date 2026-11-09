<template>
  <div class="markdown-content" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { renderMarkdown } from '../utils/markdown'
import 'katex/dist/katex.min.css'

const props = defineProps({ content: { type: String, default: '' } })
const html = computed(() => DOMPurify.sanitize(renderMarkdown(props.content)))
</script>

<style scoped>
.markdown-content { min-width:0; line-height:1.85; overflow-wrap:anywhere; }
.markdown-content :deep(> :first-child) { margin-top:0; }
.markdown-content :deep(> :last-child) { margin-bottom:0; }
.markdown-content :deep(h1), .markdown-content :deep(h2), .markdown-content :deep(h3), .markdown-content :deep(h4) { line-height:1.5; margin:1.4em 0 .6em; font-size:1.15em; color:var(--ink-1); }
.markdown-content :deep(p) { margin:.7em 0; }
.markdown-content :deep(ul), .markdown-content :deep(ol) { padding-left:1.6em; }
.markdown-content :deep(li) { margin:.4em 0; }
.markdown-content :deep(blockquote) { margin:1em 0; padding:.2em 1em; border-left:3px solid var(--line); color:var(--ink-3); }
.markdown-content :deep(pre) { overflow-x:auto; padding:14px; background:var(--bg-card); white-space:pre; line-height:1.6; }
.markdown-content :deep(code) { font-family:Consolas,monospace; font-size:.9em; }
.markdown-content :deep(table) { display:block; max-width:100%; overflow-x:auto; border-collapse:collapse; }
.markdown-content :deep(th), .markdown-content :deep(td) { border:1px solid var(--line); padding:8px 12px; text-align:left; }
.markdown-content :deep(.katex-display) { overflow-x:auto; overflow-y:hidden; padding:8px 0; margin:1em 0; }
.markdown-content :deep(eq) { display:inline-block; max-width:100%; }
.markdown-content :deep(eq), .markdown-content :deep(eqn) { overflow-wrap:normal; }
.markdown-content :deep(img) { max-width:100%; }
.markdown-content :deep(a) { color:var(--coral-deep); text-decoration:underline; text-underline-offset:3px; }
</style>
