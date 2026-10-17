import { defineStore } from 'pinia'
import { notifications } from '../services/notifications'

export const useNotificationStore = defineStore('notifications', {
  state: () => ({
    unread: 0,
    preview: [],
    enabled: true,
    error: '',
    loading: false,
    revision: 0,
  }),
  actions: {
    reset() {
      this.revision++
      this.unread = 0
      this.preview = []
      this.error = ''
      this.loading = false
    },
    async refresh(check = true) {
      const revision = ++this.revision
      this.loading = true
      try {
        if (check) await notifications.check()
        const [list, prefs] = await Promise.all([
          notifications.list({ unread_only: true, page_size: 3 }),
          notifications.preferences(),
        ])
        if (revision !== this.revision) return
        this.unread = list.unread_count
        this.preview = list.items
        this.enabled = prefs.enabled
        this.error = ''
      } catch {
        if (revision === this.revision)
          this.error = '站内提醒暂时未能加载，请重试'
      } finally {
        if (revision === this.revision) this.loading = false
      }
    },
  },
})
