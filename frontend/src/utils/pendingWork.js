// 操作前读取当前状态；确认取消时不暂停计时、不清草稿、不请求退出接口。
export function createPendingWork() {
  const entries = new Map()
  return {
    register(read, prepare) {
      const key = Symbol()
      entries.set(key, {read, prepare})
      return () => entries.delete(key)
    },
    state() {
      const states = [...entries.values()].map(e => e.read() || {})
      const unique = key => [...new Set(states.flatMap(s => [s[key] || []].flat()).filter(Boolean))]
      return {busy:unique('busy'), warnings:unique('warning')}
    },
    async prepare() {
      for(const e of [...entries.values()]) if(e.prepare && await e.prepare() === false) return false
      return true
    },
  }
}
export const pendingWork = createPendingWork()

export function createLogoutFlow({work,confirm,revoke,clear,token,notify}) {
  let running = false
  return async () => {
    if(running) return false
    running = true
    const original = token()
    try {
      const state = work.state()
      if(state.busy.length) {notify(`请等待${state.busy.join('、')}完成后再退出`);return false}
      const message = ['确认退出登录？此账号已有登录会话将失效，当前浏览器的未提交自测草稿将清除。',...state.warnings].join('\n\n')
      if(!await confirm(message)) return false
      if(token() !== original) {notify('登录状态已变化，请重新操作');return false}
      if(work.state().busy.length) {notify('当前操作尚未完成，请稍后退出');return false}
      if(!await work.prepare()) return false
      if(token() !== original) {notify('登录状态已变化，请重新操作');return false}
      await revoke(original)
      // 迟到的旧请求不能清除用户刚登录的新会话。
      if(token() !== original) {notify('登录状态已变化，已保留新会话，请刷新核对账号');return false}
      await clear()
      return true
    } catch {
      notify(token() === original ? '退出未完成，登录状态与草稿已保留。请检查连接后重试。' : '登录状态已变化，请重新登录或核对当前账号。')
      return false
    } finally {running = false}
  }
}
