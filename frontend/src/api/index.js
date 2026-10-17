// 各模块接口封装：与 docs/接口文档.md 一一对应
import request from './request'

export const authApi = {
  register: (data) => request.post('/auth/register', data),
  login: (data) => request.post('/auth/login', data),
  me: () => request.get('/auth/me'),
  updateMe: (data) => request.put('/auth/me', data),
  // 1.5 修改密码（登录态）
  changePassword: (data) => request.post('/auth/change-password', data),
  // 1.4 密码找回：先验证身份拿 reset_token，再重置密码（同时解锁）
  resetVerify: (data) => request.post('/auth/reset-password/verify', data),
  resetConfirm: (data) => request.post('/auth/reset-password/confirm', data),
  // 1.7 注销账号（二次确认由页面负责）
  deactivate: () => request.delete('/auth/me'),
}

export const examApi = {
  list: (params) => request.get('/exams', { params }), // 2.4 支持 subject / date_from / date_to
  create: (data) => request.post('/exams', data),
  update: (id, data) => request.put(`/exams/${id}`, data),
  remove: (id) => request.delete(`/exams/${id}`),
  // 2.7 倒推生成备考时间表
  generateSchedule: (id, data) => request.post(`/exams/${id}/generate-schedule`, data),
  // 2.12 ICS 导入（multipart：file + exam_id）
  importIcs: (formData) =>
    request.post('/exams/import-ics', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  // 2.13 ICS 导出（返回文件流，由调用方触发下载）
  exportIcs: () => request.get('/exams/export-ics', { responseType: 'blob' }),
}

export const materialApi = {
  list: (params) => request.get('/materials', { params }),
  upload: (formData) =>
    request.post('/materials', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  detail: (id) => request.get(`/materials/${id}`),
  update: (id, data) => request.put(`/materials/${id}`, data),
  merge: (data) => request.post('/materials/merge', data),
  remove: (id) => request.delete(`/materials/${id}`),
}

export const collectionApi = {
  list: (params) => request.get('/collections', { params }),
  add: (data) => request.post('/collections', data),
  remove: (id) => request.delete(`/collections/${id}`),
  // 自测判分（4.6）答错题批量入错题本
  addMistakes: (mistakes) => request.post('/collections/mistakes', { mistakes }),
}

export const aiApi = {
  profile: (data) => request.post('/ai/profile', data),
  analyze: (examId) => request.post('/ai/analyze', { exam_id: examId }),
  latestAnalysis: (examId) => request.get(`/ai/analyses/${examId}`, { quietNotFound: true }),
}

export const taskApi = {
  today: () => request.get('/tasks/today'),
  list: (params) => request.get('/tasks', { params }),
  create: (data) => request.post('/tasks', data),
  update: (id, data) => request.put(`/tasks/${id}`, data), // 2.6 编辑任务
  checkin: (id) => request.post(`/tasks/${id}/checkin`),
  uncheckin: (id) => request.delete(`/tasks/${id}/checkin`),
  remove: (id) => request.delete(`/tasks/${id}`),
  // 2.8 冲突检测：保存前预检当天总时长是否超上限
  checkConflict: (data) => request.post('/tasks/check-conflict', data),
}

export const dashboardApi = {
  overview: () => request.get('/dashboard'),
  stats: (examId) => request.get(`/stats/${examId}`),
  statsOverview: (days) => request.get('/stats/overview', { params: { days } }),
}

export const focusApi = {
  createSession: (data) => request.post('/focus/sessions', data),
  today: () => request.get('/focus/today'),
  setGoal: (data) => request.put('/focus/goal', data),
  sessions: (params) => request.get('/focus/sessions', { params }),
}

export const featureApi = {
  pressure: () => request.get('/features/pressure'),
  moodToday: () => request.get('/features/mood/today'),
  submitMood: (data) => request.post('/features/mood', data),
  emergency: (params) => request.get('/features/emergency', { params }),
  review: (params) => request.get('/features/review', { params }),
  top3: () => request.get('/features/top3'),
  timeslots: () => request.get('/features/timeslots'),
  relief: (params) => request.get('/features/relief', { params }),
  reliefApply: (data) => request.post('/features/relief/apply', data),
}

export const adminApi = {
  courses: () => request.get('/admin/courses'),
  createCourse: (data) => request.post('/admin/courses', data),
  updateCourse: (id, data) => request.put(`/admin/courses/${id}`, data),
  removeCourse: (id) => request.delete(`/admin/courses/${id}`),
  users: () => request.get('/admin/users'),
  banUser: (id) => request.post(`/admin/users/${id}/ban`),
  unbanUser: (id) => request.post(`/admin/users/${id}/unban`),
  materials: (params) => request.get('/admin/materials', { params }),
  removeMaterial: (id) => request.delete(`/admin/materials/${id}`),
}

export const studyApi = {
  settings: () => request.get('/study/settings'),
  saveSettings: (data) => request.put('/study/settings', data),
  preview: () => request.get('/study/plan/preview'),
  confirm: (data) => request.post('/study/plan/confirm', data),
}
