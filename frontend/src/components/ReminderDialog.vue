<template>
  <el-dialog
    :model-value="modelValue"
    title="设置站内提醒"
    width="460px"
    :before-close="reminderDraft.beforeClose"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading">
      <template v-if="detail">
        <p class="reminder-title">{{ detail.title }}</p>
        <p class="reminder-date">{{ detail.event_date }} · 北京时间（UTC+8）</p>
        <el-form label-position="top" class="reminder-form">
          <el-form-item
            ><el-switch
              v-model="form.enabled"
              aria-label="启用此项提醒"
              active-text="启用此项提醒"
          /></el-form-item>
          <el-form-item label="当天的提醒基准时刻">
            <el-time-select
              v-model="form.event_time"
              start="00:00"
              end="23:45"
              step="00:15"
              aria-label="提醒基准时刻"
              :clearable="false"
            />
            <p class="reminder-help">
              用于计算提醒，不修改考试或任务安排。事项改期后，提醒日期自动跟随。
            </p>
          </el-form-item>
          <el-form-item label="提前多少分钟">
            <el-input-number
              v-model="form.advance_minutes"
              :min="0"
              :max="43200"
              :step="15"
              aria-label="提前分钟数"
            />
            <p class="reminder-help">
              0 为该时刻提醒；60 为提前 1 小时，1440 为提前 1 天。
            </p>
          </el-form-item>
        </el-form>
        <p class="reminder-result">
          {{ form.enabled ? `提醒时间：${dueLabel}` : '此项提醒已关闭' }}
        </p>
        <p class="reminder-help">
          仅在打开页面或点击刷新时检查；关闭网页期间不会主动推送。通知总开关也需开启。
        </p>
      </template>
      <el-alert
        v-else-if="error"
        :title="error"
        type="error"
        :closable="false"
      />
    </div>
    <template #footer>
      <el-button :disabled="saving" @click="reminderDraft.close">取消</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!detail || !form.event_time || form.advance_minutes == null"
        @click="save"
        >保存提醒</el-button
      >
    </template>
  </el-dialog>
</template>
<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useDialogDraft } from '../composables/usePendingWork'
import { ElMessage } from 'element-plus'
import {
  notifications,
  notificationTime,
  reminderDate,
} from '../services/notifications'
import { useNotificationStore } from '../stores/notifications'
const props = defineProps({
  modelValue: Boolean,
  kind: String,
  targetId: Number,
})
const emit = defineEmits(['update:modelValue', 'saved'])
const store = useNotificationStore()
const detail = ref(null),
  loading = ref(false),
  saving = ref(false),
  error = ref('')
let requestId = 0
const form = reactive({
  enabled: true,
  event_time: '09:00',
  advance_minutes: 15,
})
const reminderVisible = computed({get:() => props.modelValue,set:value => emit('update:modelValue',value)})
const reminderDraft = useDialogDraft(form,reminderVisible,saving,'提醒设置')
const dueLabel = computed(() =>
  detail.value && form.event_time && form.advance_minutes != null
    ? notificationTime(
        reminderDate(
          detail.value.event_date,
          form.event_time,
          form.advance_minutes,
        ),
      )
    : '请填写完整',
)
watch(
  () => [props.modelValue, props.kind, props.targetId],
  async ([open]) => {
    const id = ++requestId
    if (!open) return
    const kind = props.kind,
      targetId = props.targetId
    detail.value = null
    error.value = ''
    loading.value = true
    try {
      const result = await notifications.reminder(kind, targetId)
      if (id === requestId) {
        detail.value = result
        Object.assign(form, result)
        reminderDraft.capture()
      }
    } catch (e) {
      if (id === requestId) error.value = e.message || '提醒设置加载失败'
    } finally {
      if (id === requestId) loading.value = false
    }
  },
)
async function save() {
  if(saving.value) return
  saving.value = true
  try {
    await notifications.saveReminder(props.kind, props.targetId, {
      enabled: form.enabled,
      event_time: form.event_time,
      advance_minutes: form.advance_minutes,
    })
    await store.refresh()
    ElMessage.success('提醒设置已保存')
    emit('saved')
    emit('update:modelValue', false)
  } catch {
    ElMessage.error('保存失败，请重试')
  } finally {
    saving.value = false
  }
}
</script>
<style scoped>
.reminder-title {
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.reminder-date,
.reminder-help {
  color: var(--ink-2);
  font-size: 12px;
  line-height: 1.8;
}
.reminder-date {
  margin: 8px 0 20px;
}
.reminder-help {
  width: 100%;
  margin-top: 8px;
}
.reminder-result {
  padding: 12px;
  background: var(--bg-soft);
  border-left: 3px solid var(--coral);
  font-weight: 700;
}
</style>
