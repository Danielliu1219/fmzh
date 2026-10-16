import { defineStore } from 'pinia'
import { authApi } from '../api'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('fmzh_token') || '',
    user: JSON.parse(localStorage.getItem('fmzh_user') || 'null'),
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    displayName: (state) => state.user?.nickname || state.user?.username || '同学',
    isAdmin: (state) => !!state.user?.is_admin,
  },
  actions: {
    _setSession(data) {
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('fmzh_token', this.token)
      localStorage.setItem('fmzh_user', JSON.stringify(this.user))
    },
    async login(username, password) {
      this._setSession(await authApi.login({ username, password }))
    },
    async register(payload) {
      this._setSession(await authApi.register(payload))
    },
    // 1.6 编辑资料 / 1.5 修改密码后，用最新用户信息刷新本地会话
    applyUser(user) {
      this.user = user
      localStorage.setItem('fmzh_user', JSON.stringify(user))
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('fmzh_token')
      localStorage.removeItem('fmzh_user')
    },
  },
})
