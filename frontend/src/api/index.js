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
  remove: (id) => request.delete(`/materials/${id}`),
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
