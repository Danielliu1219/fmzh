<template>
  <div class="mindmap">
    <div class="mindmap-tools">
      <span>点击节点展开或收起；较宽的导图可横向滚动</span>
      <button type="button" @click="collapsed = new Set()">全部展开</button>
      <button type="button" @click="collapsed = mindmapDetailBranches(data)">收起依据</button>
    </div>
    <div ref="viewport" class="mindmap-viewport" role="region" aria-label="复习思维导图，可横向滚动" tabindex="0">
      <div class="mindmap-canvas" :style="{ width: `${layout.width}px`, height: `${layout.height}px` }">
        <svg class="mindmap-links" :width="layout.width" :height="layout.height" aria-hidden="true">
          <path v-for="link in layout.links" :key="link.id" :d="link.path" />
        </svg>
        <component :is="node.expandable ? 'button' : 'div'" v-for="node in layout.nodes" :key="node.id"
          class="mindmap-node" :class="{ 'is-heading': node.depth < 2, 'is-expandable': node.expandable }"
          :style="{ left: `${node.x}px`, top: `${node.y}px`, width: `${node.width}px`, height: `${node.height}px` }"
          :type="node.expandable ? 'button' : undefined"
          :aria-expanded="node.expandable ? node.expanded : undefined"
          @click="node.expandable && toggle(node.id)">
          <span class="mindmap-dot" aria-hidden="true"></span>
          <span class="mindmap-label">{{ node.lines.join('\n') }}</span>
          <span v-if="node.expandable" class="mindmap-toggle" aria-hidden="true">{{ node.expanded ? '−' : '+' }}</span>
        </component>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { layoutMindmap, mindmapDetailBranches } from '../utils/mindmapLayout.js'

const props = defineProps({ data: { type: Object, default: null } })
const viewport = ref(null), width = ref(1100), fontRevision = ref(0), collapsed = ref(new Set())
let observer, context, resizeFrame, fontFamily = 'sans-serif', disposed = false
const measure = (text, depth) => {
  if (!context) return Array.from(text).reduce((sum, char) => sum + (/[^\u0000-\u00ff]/.test(char) ? 13 : 7.8), 0)
  context.font = `${depth < 2 ? 600 : 400} 13px ${fontFamily}`
  return context.measureText(text).width
}
const layout = computed(() => {
  void fontRevision.value
  return layoutMindmap(props.data, { width: width.value, collapsed: collapsed.value, measure })
})
const toggle = id => {
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsed.value = next
}
watch(() => props.data, () => { collapsed.value = new Set() })
onMounted(() => {
  context = document.createElement('canvas').getContext('2d')
  fontFamily = getComputedStyle(viewport.value).fontFamily
  width.value = Math.max(1, viewport.value.clientWidth)
  fontRevision.value++
  observer = new ResizeObserver(entries => {
    const nextWidth = Math.max(1, entries[0].contentRect.width)
    if (Math.abs(nextWidth - width.value) < 1) return
    cancelAnimationFrame(resizeFrame)
    // 下一帧再写入尺寸，避免在observer交付时改变布局而触发循环警告。
    resizeFrame = requestAnimationFrame(() => { if (!disposed) width.value = nextWidth })
  })
  observer.observe(viewport.value)
  document.fonts?.ready.then(() => { if (!disposed) fontRevision.value++ })
})
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); cancelAnimationFrame(resizeFrame) })
</script>

<style scoped>
.mindmap { min-width: 0; }
.mindmap-tools { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin-bottom: 12px; font-size: 12px; color: var(--text-low, #68716a); }
.mindmap-tools span { flex: 1 1 240px; }
.mindmap-tools button { border: 1px solid var(--line, #d9d4c3); border-radius: 6px; padding: 5px 10px; background: transparent; color: var(--text-hi, #0c1614); font: inherit; cursor: pointer; }
.mindmap-viewport { width: 100%; min-width: 0; overflow-x: auto; overflow-y: hidden; font: 13px/20px var(--font-sans, sans-serif); }
.mindmap-canvas { position: relative; }
.mindmap-links { position: absolute; inset: 0; display: block; pointer-events: none; }
.mindmap-links path { fill: none; stroke: var(--line, #d9d4c3); stroke-width: 1.4; }
.mindmap-node { position: absolute; display: flex; align-items: center; gap: 10px; box-sizing: border-box; padding: 6px; border: 0; background: transparent; color: var(--text-hi, #0c1614); text-align: left; font: inherit; }
.mindmap-node.is-heading { font-weight: 600; }
.mindmap-node.is-expandable { cursor: pointer; border-radius: 6px; }
.mindmap-node.is-expandable:hover { background: var(--coral-soft, #fbeee8); }
.mindmap-dot { flex: 0 0 8px; height: 8px; border-radius: 50%; background: var(--coral, #e66348); }
.mindmap-label { flex: 1; min-width: 0; white-space: pre; line-height: 20px; }
.mindmap-toggle { flex: 0 0 14px; font: 16px/20px sans-serif; color: var(--text-low, #68716a); }
.mindmap-tools button:focus-visible, .mindmap-node:focus-visible, .mindmap-viewport:focus-visible { outline: 2px solid var(--coral-deep, #ba4d39); outline-offset: 2px; }
</style>
