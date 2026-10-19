export function clearSession() {
  localStorage.removeItem('fmzh_token')
  localStorage.removeItem('fmzh_user')
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith('fmzh_quiz_draft:')) localStorage.removeItem(key)
  }
}

export function readSession() {
  try {
    const token = localStorage.getItem('fmzh_token') || ''
    const user = JSON.parse(localStorage.getItem('fmzh_user') || 'null')
    if (!token || !user || typeof user !== 'object' || !user.username) {
      clearSession()
      return { token: '', user: null }
    }
    return { token, user }
  } catch {
    clearSession()
    return { token: '', user: null }
  }
}
