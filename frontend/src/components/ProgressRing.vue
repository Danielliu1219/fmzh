<template>
  <div
    class="progress-ring"
    role="progressbar"
    :aria-label="label"
    :aria-valuenow="percentage"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle class="track" cx="60" cy="60" r="51" />
      <circle
        class="fill"
        cx="60"
        cy="60"
        r="51"
        pathLength="100"
        :stroke-dasharray="`${percentage} 100`"
        :class="{ empty: percentage === 0 }"
      />
    </svg>
    <div class="ring-content">
      <slot
        ><strong>{{ percentage }}<small>%</small></strong></slot
      >
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  value: { type: Number, default: 0 },
  label: { type: String, default: '任务完成率' },
})
const percentage = computed(() =>
  Math.round(Math.min(100, Math.max(0, Number(props.value) || 0))),
)
</script>

<style scoped>
.progress-ring {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
}
svg {
  display: block;
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
  overflow: visible;
}
circle {
  fill: none;
  stroke-width: 8;
}
.track {
  stroke: var(--ring-track, var(--bg-soft));
}
.fill {
  stroke: var(--ring-color, var(--coral));
  stroke-linecap: round;
  transition: stroke-dasharray 600ms cubic-bezier(0.22, 1, 0.36, 1);
}
.fill.empty {
  stroke: transparent;
}
.ring-content {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
strong {
  font: 700 48px/1 var(--font-num);
  letter-spacing: -0.06em;
}
small {
  font-size: 0.38em;
  margin-left: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .fill {
    transition: none;
  }
}
</style>
