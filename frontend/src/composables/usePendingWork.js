import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { pendingWork } from '../utils/pendingWork'

export async function confirmAction(message, title='确认操作', options={}) {
  try {
    await ElMessageBox.confirm(message,title,{type:'warning',confirmButtonText:'确认',cancelButtonText:'取消',distinguishCancelAndClose:true,...options})
    return true
  } catch {return false}
}

export function usePendingWork(read, prepare) {
  let unregister
  onMounted(() => {unregister = pendingWork.register(read, prepare)})
  onBeforeUnmount(() => unregister?.())
}

export async function confirmPageLeave() {
  const state = pendingWork.state()
  if(state.busy.length) {ElMessage.warning(`请等待${state.busy.join('、')}完成后再离开`);return false}
  if(state.warnings.length && !await confirmAction(state.warnings.join('\n\n'),'离开当前页面',{confirmButtonText:'确认离开',cancelButtonText:'继续编辑'})) return false
  if(pendingWork.state().busy.length) return false
  try {return await pendingWork.prepare()} catch {ElMessage.warning('当前内容尚未保存，请重试后再离开');return false}
}

export function protectBrowserClose(event) {
  const state = pendingWork.state()
  if(state.busy.length || state.warnings.length) {event.preventDefault();event.returnValue = ''}
}

// 弹窗取消、右上角关闭、遮罩及Esc使用相同的未保存检查；成功保存可直接关闭。
export function useDialogDraft(model, visible, busy, label) {
  const baseline = ref('')
  const snapshot = () => JSON.stringify(typeof model === 'function' ? model() : model)
  const dirty = computed(() => visible.value && baseline.value !== snapshot())
  watch(visible, value => {if(value) baseline.value = snapshot()}, {flush:'sync',immediate:true})
  usePendingWork(() => ({busy:busy.value ? `${label}保存` : '',warning:dirty.value ? `${label}有未保存的修改，离开会丢弃这些修改。` : ''}))
  const allowClose = async () => {
    if(busy.value) return false
    const approved = !dirty.value || await confirmAction(`${label}尚未保存，确认放弃这些修改？`,'放弃修改',{confirmButtonText:'放弃修改',cancelButtonText:'继续编辑'})
    return approved && !busy.value
  }
  return {dirty, capture:() => {baseline.value=snapshot()}, close:async () => {if(await allowClose()) visible.value=false}, beforeClose:async done => {if(await allowClose()) done()}}
}

export function useActionLock(label) {
  const busy = ref(false)
  usePendingWork(() => ({busy:busy.value ? label : ''}))
  return {busy, run:async action => {
    if(busy.value) return false
    busy.value=true
    try {return await action()} catch {return false} finally {busy.value=false}
  }}
}
