// 各模块接口封装：与 docs/接口文档.md 一一对应
import request from './request'

export const authApi = {
  register: (data) => request.post('/auth/register', data),
  login: (data) => request.post('/auth/login', data),
  me: () => request.get('/auth/me'),
  updateMe: (data) => request.put('/auth/me', data),
}

export const examApi = {
  list: () => request.get('/exams'),
  create: (data) => request.post('/exams', data),
  update: (id, data) => request.put(`/exams/${id}`, data),
  remove: (id) => request.delete(`/exams/${id}`),
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
  latestAnalysis: (examId) => request.get(`/ai/analyses/${examId}`),
}

export const taskApi = {
  today: () => request.get('/tasks/today'),
  list: (params) => request.get('/tasks', { params }),
  create: (data) => request.post('/tasks', data),
  checkin: (id) => request.post(`/tasks/${id}/checkin`),
  uncheckin: (id) => request.delete(`/tasks/${id}/checkin`),
  remove: (id) => request.delete(`/tasks/${id}`),
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
