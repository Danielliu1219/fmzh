<template>
  <el-tour
    :model-value="modelValue"
    :current="current"
    class="onboarding-tour"
    :role="modelValue ? 'dialog' : undefined"
    :aria-modal="modelValue ? 'true' : undefined"
    :aria-label="modelValue ? '新手教程' : undefined"
    :class="{ 'is-moving': moving }"
    :mask="{ color: 'rgba(8, 19, 16, 0.72)' }"
    :gap="{ offset: 8, radius: 8 }"
    :target-area-clickable="false"
    :show-close="true"
    :show-arrow="false"
    :scroll-into-view-options="{ behavior: 'instant', block: 'center' }"
    :content-style="{ width: 'min(380px, calc(100vw - 32px))' }"
    @update:model-value="$emit('update:modelValue', $event)"
    @update:current="moveTo"
    @close="close"
  >
    <template #indicators="{ current: index, total }">
      <span class="onboarding-count">{{ index + 1 }} / {{ total }}</span>
      <el-button text size="small" class="onboarding-skip" @click="close"
        >跳过教程</el-button
      >
    </template>
    <el-tour-step
      v-for="(step, index) in steps"
      :key="step.title"
      :target="moving ? null : step.target"
      :title="step.title"
      placement="bottom"
      :prev-button-props="{ children: '上一步', disabled: moving }"
      :next-button-props="{
        children:
          index === steps.length - 1
            ? '完成，进入首页'
            : index === 0
              ? '开始了解'
              : '下一步',
        disabled: moving,
      }"
    >
      <p class="onboarding-kicker">{{ step.label }}</p>
      <p class="onboarding-copy">{{ step.description }}</p>
      <p v-if="index === 0" class="onboarding-note">
        约 1 分钟 · 随时可跳过 · 不会修改你的考试或任务
      </p>
    </el-tour-step>
  </el-tour>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'closed'])
const current = ref(0),
  moving = ref(false)
let moveVersion = 0
let restoreBackground = null
function blockBackgroundScroll(event) {
  const card = event.target.closest?.('.el-tour__content')
  if (!card || card.scrollHeight <= card.clientHeight) event.preventDefault()
}
function blockPageKeys(event) {
  if (
    ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'].includes(
      event.key,
    ) ||
    (event.key === ' ' && !event.target.closest?.('button'))
  )
    blockBackgroundScroll(event)
}
const visibleTarget =
  (...names) =>
  () =>
    names
      .map((name) => document.querySelector(`[data-tour="${name}"]`))
      .find(
        (el) =>
          el &&
          el.getBoundingClientRect().width > 0 &&
          el.getBoundingClientRect().height > 0,
      ) || null

const steps = [
  {
    title: '先用一分钟，认识你的复习工作台',
    label: '欢迎来到「期末周别慌」',
    description:
      '先把所有考试和复习资料放到一起，再把每天的时间分给各科。接下来带你找到最常用的几个入口。',
  },
  {
    title: '第一步，录入所有考试',
    label: '先看清全局',
    target: visibleTarget('exams'),
    description:
      '在课程管理里添加每一门考试的日期。系统会结合全部考试安排复习，而不是一天只考虑一科。',
  },
  {
    title: '把资料变成可以执行的计划',
    label: '资料 → AI 分析 → 任务',
    target: visibleTarget('analysis'),
    description:
      '先到「复习资料」按科目上传文件，再进入 AI 复习分析，填写这门课的目标与基础，生成考点、计划和自测题。',
  },
  {
    title: '每天的可用时间，由所有科目共享',
    label: '设置全科预算',
    target: visibleTarget('budget'),
    description:
      '例如每天有 4 小时，就是各科合计 4 小时。这里可以保存时间预算，先预览各科分配，再确认重排。',
  },
  {
    title: '每天回来，先从任务清单开始',
    label: '今日复习的主区',
    target: visibleTarget('tasks', 'tasks-mobile'),
    description:
      '上方三个方向帮你抓重点，任务清单才是每天的执行入口。可以筛选、选中任务、勾选完成；任务多时只滚动清单。',
  },
  {
    title: '选一件事，专心学一会儿',
    label: '任务 → 专注 → 打卡',
    target: visibleTarget('focus', 'focus-mobile'),
    description:
      '选中任务后开启番茄钟，实际专注时间会累计到今日目标。学完再勾选任务；手机上点击「番茄钟与资料」切换到专注区。',
  },
  {
    title: '重要的事，交给站内提醒',
    label: '准备好了，开始你的第一天',
    target: visibleTarget('notifications'),
    description:
      '点铃铛打开通知中心，为考试或任务设置提醒时间。打开或刷新页面时检查到期提醒。以后想再看教程，首页最下方就有入口。',
  },
]

function close() {
  moveVersion++
  moving.value = false
  emit('update:modelValue', false)
  emit('closed')
}

async function moveTo(index) {
  if (moving.value || !props.modelValue) return
  const version = ++moveVersion
  const target = steps[index]?.target?.()
  if (target && !target.closest('.header')) {
    const rect = target.getBoundingClientRect()
    const headerBottom =
      document.querySelector('.header')?.getBoundingClientRect().bottom || 0
    if (rect.top < headerBottom + 16 || rect.bottom > innerHeight - 160) {
      moving.value = true
      const top = Math.max(
        0,
        scrollY + rect.top - Math.max(headerBottom + 24, innerHeight * 0.4),
      )
      const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
      window.scrollTo({ top, behavior: reduce ? 'instant' : 'smooth' })
      if (!reduce) await waitForScroll(version)
    }
  }
  if (version !== moveVersion || !props.modelValue) return
  current.value = index
  moving.value = false
}

function waitForScroll(version) {
  return new Promise((resolve) => {
    const start = performance.now()
    let previous = scrollY,
      stable = 0
    function frame() {
      stable = Math.abs(scrollY - previous) < 1 ? stable + 1 : 0
      previous = scrollY
      if (
        version !== moveVersion ||
        stable >= 4 ||
        performance.now() - start > 1400
      )
        return resolve()
      requestAnimationFrame(frame)
    }
    requestAnimationFrame(frame)
  })
}

watch(
  () => props.modelValue,
  (open) => {
    moveVersion++
    moving.value = false
    if (open) {
      current.value = 0
      const background = document.querySelector('.layout')
      const oldInert = background?.hasAttribute('inert') || false
      if (background) background.setAttribute('inert', '')
      document.addEventListener('wheel', blockBackgroundScroll, {
        passive: false,
        capture: true,
      })
      document.addEventListener('touchmove', blockBackgroundScroll, {
        passive: false,
        capture: true,
      })
      document.addEventListener('keydown', blockPageKeys, true)
      restoreBackground = () => {
        if (background) background.toggleAttribute('inert', oldInert)
        document.removeEventListener('wheel', blockBackgroundScroll, true)
        document.removeEventListener('touchmove', blockBackgroundScroll, true)
        document.removeEventListener('keydown', blockPageKeys, true)
      }
    } else {
      restoreBackground?.()
      restoreBackground = null
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  moveVersion++
  restoreBackground?.()
})
</script>

<style>
.onboarding-tour .el-tour__content {
  --el-tour-padding-primary: 24px;
  background: var(--bg-card);
  color: var(--ink-1);
  border: 1.5px solid var(--ink-1);
  border-radius: 12px;
  box-shadow: 5px 5px 0 rgba(8, 19, 16, 0.28);
  transition: opacity 0.18s ease;
  max-height: calc(100dvh - 32px);
  overflow-y: auto;
  overscroll-behavior: contain;
}
.onboarding-tour.is-moving .el-tour__content {
  opacity: 0;
  pointer-events: none;
}
.onboarding-tour .el-tour__title {
  font-family: var(--font-serif);
  font-size: 23px;
  line-height: 1.45;
  font-weight: 900;
}
.onboarding-tour .el-tour__header {
  margin-bottom: 18px;
  padding-bottom: 0;
}
.onboarding-tour .el-tour__arrow {
  background: var(--bg-card);
}
.onboarding-kicker {
  color: var(--coral-deep);
  font-size: 11px;
  letter-spacing: 1px;
  font-weight: 700;
  margin-bottom: 10px;
}
.onboarding-copy {
  font-size: 14px;
  line-height: 1.85;
  text-wrap: pretty;
}
.onboarding-note {
  color: var(--ink-2);
  font-size: 11px;
  line-height: 1.7;
  margin-top: 14px;
}
.onboarding-tour .el-tour__footer {
  margin-top: 24px;
  padding-top: 0;
  gap: 8px;
  flex-wrap: wrap;
}
.onboarding-tour .el-tour-indicators {
  display: flex;
  align-items: center;
  gap: 10px;
}
.onboarding-count {
  color: var(--ink-2);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.onboarding-tour .onboarding-skip {
  color: var(--ink-2);
  margin: 0;
  padding-inline: 4px;
}
.onboarding-tour .el-tour-buttons .el-button {
  padding-inline: 12px;
  min-height: 32px;
}
@media (max-width: 480px) {
  .onboarding-tour .el-tour__content {
    --el-tour-padding-primary: 20px;
  }
  .onboarding-tour .el-tour__title {
    font-size: 21px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .onboarding-tour .el-tour__content,
  .onboarding-tour .el-tour__hollow {
    transition: none;
  }
}
</style>
