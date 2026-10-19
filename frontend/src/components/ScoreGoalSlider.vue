<template>
  <div class="score-goal" :class="{ 'is-disabled': disabled }">
    <div class="score-readout" aria-live="polite">
      <div><span class="score-caption">目标分数区间</span><strong>{{ band.range }}</strong></div>
      <div class="gpa-readout"><span>对应绩点</span><strong>{{ band.gpa }}</strong><small>{{ band.id }}</small></div>
    </div>
    <input
      class="score-range"
      type="range"
      min="0"
      :max="SCORE_BANDS.length - 1"
      step="1"
      :value="index"
      :disabled="disabled"
      aria-label="目标分数区间"
      :aria-valuetext="scoreBandText(band.id)"
      :style="{ '--goal-progress': `${index / (SCORE_BANDS.length - 1) * 100}%` }"
      @input="$emit('update:modelValue', SCORE_BANDS[Number($event.target.value)].id)"
    />
    <div class="score-ticks" aria-label="可选分数档位">
      <button v-for="item in SCORE_BANDS" :key="item.id" type="button" :disabled="disabled"
        :class="{ selected: item.id === band.id }" :aria-label="scoreBandText(item.id)"
        :aria-pressed="item.id === band.id" @click="$emit('update:modelValue', item.id)">
        <span>{{ item.threshold }}</span><small>{{ item.gpa }}</small>
      </button>
    </div>
    <div class="score-footnote"><span>拖动滑条或点击档位选择，按区间吸附</span><a href="https://jwc.scu.edu.cn/info/1066/3444.htm" target="_blank" rel="noopener noreferrer">川大本科绩点标准 ↗</a></div>
    <p class="score-hint">{{ scoreGoalHint(band.id) }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { SCORE_BANDS, scoreBandText, scoreGoalHint } from '../utils/scoreTargets'
const props = defineProps({ modelValue: { type: String, default: 'D' }, disabled: Boolean })
defineEmits(['update:modelValue'])
const index = computed(() => Math.max(0, SCORE_BANDS.findIndex((item) => item.id === props.modelValue)))
const band = computed(() => SCORE_BANDS[index.value])
</script>

<style scoped>
.score-goal { width: 100%; min-width: 0; }
.score-readout { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
.score-readout > div { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 12px; }
.score-readout > div:first-child { flex-direction: column; }
.score-caption, .gpa-readout > span { font-size: 12px; color: var(--ink-3); }
.score-readout strong { font: 500 29px/1.2 var(--font-num), var(--font-sans); color: var(--ink-1); font-variant-numeric: tabular-nums; }
.gpa-readout strong { color: var(--coral-deep); font-size: 34px; }
.gpa-readout small { color: var(--ink-3); font-family: var(--font-num); }
.score-range { display: block; appearance: none; -webkit-appearance: none; width: 100%; height: 32px; margin: 0; background: transparent; cursor: pointer; touch-action: pan-y; }
.score-range::-webkit-slider-runnable-track { height: 8px; border-radius: 4px; background: linear-gradient(to right, var(--coral) var(--goal-progress), var(--line) var(--goal-progress)); }
.score-range::-moz-range-track { height: 8px; border-radius: 4px; background: var(--line); }
.score-range::-moz-range-progress { height: 8px; border-radius: 4px; background: var(--coral); }
.score-range::-webkit-slider-thumb { appearance: none; -webkit-appearance: none; width: 24px; height: 24px; border: 3px solid var(--coral-deep); border-radius: 50%; background: var(--bg-card); margin-top: -8px; box-shadow: 0 0 0 5px var(--coral-soft); }
.score-range::-moz-range-thumb { width: 18px; height: 18px; border: 3px solid var(--coral-deep); border-radius: 50%; background: var(--bg-card); }
.score-range:focus-visible { outline: 2px solid var(--coral-deep); outline-offset: 5px; border-radius: 5px; }
.score-ticks { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: 3px; margin-top: 8px; }
.score-ticks button { display: flex; flex-direction: column; gap: 5px; align-items: center; border: 0; border-radius: 5px; background: transparent; padding: 8px 0; color: var(--ink-3); cursor: pointer; font: 12px var(--font-num), var(--font-sans); transition: background 160ms, color 160ms; }
.score-ticks small { font-size: 11px; }
.score-ticks button:hover, .score-ticks button.selected { color: var(--coral-deep); background: var(--coral-soft); }
.score-ticks button:focus-visible { outline: 2px solid var(--coral-deep); }
.score-footnote { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-top: 14px; color: var(--ink-3); font-size: 11px; line-height: 1.7; }
.score-footnote a { color: var(--ink-3); text-underline-offset: 3px; }
.score-hint { margin: 16px 0 0; font-size: 12px; line-height: 1.8; color: var(--ink-2); }
.is-disabled { opacity: .6; }
@media (max-width: 680px) {
  .score-readout { gap: 10px; }
  .score-readout strong { font-size: 24px; }
  .gpa-readout { justify-content: flex-end; }
  .gpa-readout > span { width: 100%; text-align: right; }
  .gpa-readout strong { font-size: 28px; }
  .score-ticks { grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; }
  .score-ticks button { flex-direction: row; justify-content: center; min-height: 38px; gap: 7px; }
}
</style>
