// ============================================================
// Dashboard 已接入真实接口（USE_MOCK = false）。
// 下方 mock 数据保留用于样式回看：数据由 backend/seed_demo.py 种入
// SQLite（8 任务 / 3 完成 = 38%、今日 3 任务、考试 +5/+11/+14 天），
// 全站所有页面读同一份数据，保证口径一致。
// 想临时看静态效果可改回 true；重跑 seed_demo.py 可随时重置演示数据。
// ============================================================
// 【UI 预览中】临时改为 true：不启动后端也能看首页效果；
// 联调真实后端时改回 false，登录页的"免登录预览"按钮会自动消失。
export const USE_MOCK = true

// 真实接口下用本地日期（toISOString 是 UTC，中国凌晨会差一天）
const localDate = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// mock 数据统一锚定在这一天（演示当天）；真实接口下用系统日期
export const getToday = () => (USE_MOCK ? '2026-09-07' : localDate())

// 任务：与 TaskOut 同构，多带一个 exam 显示名（真实数据按 exam_id 映射）
export const mockTasks = [
  { id: 1, exam_id: 1, exam: '高等数学', title: '第3天：极限与连续', plan_date: '2026-09-07', estimated_minutes: 120, priority: 1, is_done: false, source: 'ai' },
  { id: 2, exam_id: 2, exam: '大学英语', title: '单词 Unit 1-3 记忆', plan_date: '2026-09-07', estimated_minutes: 45, priority: 2, is_done: false, source: 'ai' },
  { id: 3, exam_id: 1, exam: '高等数学', title: '第1天：核心概念与定义', plan_date: '2026-09-07', estimated_minutes: 90, priority: 1, is_done: true, source: 'ai' },
  { id: 4, exam_id: 1, exam: '高等数学', title: '第4天：导数应用专项', plan_date: '2026-09-09', estimated_minutes: 90, priority: 2, is_done: false, source: 'ai' },
  { id: 5, exam_id: 1, exam: '高等数学', title: '第5天：综合题与易错点', plan_date: '2026-09-10', estimated_minutes: 150, priority: 3, is_done: false, source: 'ai' },
  { id: 6, exam_id: 2, exam: '大学英语', title: '阅读理解 2 篇', plan_date: '2026-09-08', estimated_minutes: 60, priority: 2, is_done: false, source: 'ai' },
  { id: 7, exam_id: 1, exam: '高等数学', title: '第2天：高频题型刷题', plan_date: '2026-09-06', estimated_minutes: 120, priority: 1, is_done: true, source: 'ai' },
  { id: 8, exam_id: 2, exam: '大学英语', title: '听力精听 30 分钟', plan_date: '2026-09-06', estimated_minutes: 30, priority: 3, is_done: true, source: 'manual' },
]

// 总览：与 DashboardOut 同构（extras 为演示补充字段，真实接口下由前端自行推导）
export const mockDashboard = {
  exams: [
    { id: 1, subject: '高等数学', exam_date: '2026-09-12', days_left: 5, location: '教三 101', duration_minutes: 120, total_tasks: 5, done_tasks: 2, progress: 0.4 },
    { id: 2, subject: '大学英语', exam_date: '2026-09-18', days_left: 11, location: '外语楼 205', duration_minutes: 120, total_tasks: 3, done_tasks: 1, progress: 0.33 },
    { id: 3, subject: '数据结构', exam_date: '2026-09-21', days_left: 14, location: '信息楼 302', duration_minutes: 90, total_tasks: 0, done_tasks: 0, progress: 0 },
  ],
  tasks: mockTasks,
  today_tasks: mockTasks.filter((t) => t.plan_date === '2026-09-07'),
  overall: { total: 8, done: 3, rate: 0.375 },
  extras: { streak: 3, focus_minutes: 225 },
}

// 模拟网络延迟，顺带演示骨架屏加载状态
export const mockOverview = () =>
  new Promise((resolve) => setTimeout(() => resolve(structuredClone(mockDashboard)), 800))
