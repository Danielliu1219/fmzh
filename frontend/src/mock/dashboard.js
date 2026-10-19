// ============================================================
// USE_MOCK = true：纯前端预览态（GitHub Pages 在线预览 / 本机不起后端）。
// 首页用下方的 mock 数据，考试 / 资料 / AI 分析三页用 src/mock/pages.js，
// 登录页会显示"免登录预览"按钮。联调真实后端时改回 false，
// 全部页面自动切回真实接口（真实数据由 backend/seed_demo.py 种入：
// 8 任务 / 3 完成 = 38%、今日 3 任务、考试 +5/+11/+14 天）。
// ============================================================
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

// 压力指数（模块 7.1）演示数据：52.0 = 30×0.25 + 30×0.4 + 20×(1−0.375) + 20×1，分档「适中」
export const mockPressure = {
  score: 52.0,
  level: '适中',
  suggestion: '压力适中，保持当前节奏',
  breakdown: { exam_density: 0.25, task_backlog: 0.4, task_done_rate: 0.375, exam_proximity: 1 },
  need_emergency: false,
}

// 临时救急模式（模块 7.2）演示数据：最近一场考试的高频基础考点冲刺清单
export const mockEmergency = {
  exam_id: 1,
  subject: '高等数学',
  exam_date: '2026-09-12',
  days_left: 5,
  items: [
    { content: '函数极限的计算（洛必达法则、等价无穷小）', kind: '考点', level: 'must', weight: null, source: '历年真题', basis: '近 5 年 4 次考查，几乎每年出现' },
    { content: '导数的几何意义与切线方程', kind: '考点', level: 'must', weight: null, source: '老师重点', basis: '课堂反复强调的基础题型' },
    { content: '定积分的换元与分部积分', kind: '考点', level: 'common', weight: null, source: '历年真题', basis: '高频计算题，易错点集中' },
    { content: '极限与连续', kind: '知识点', level: 'high', weight: 0.95, source: '课后习题', basis: '全卷基础，失分影响大' },
    { content: '导数与微分', kind: '知识点', level: 'high', weight: 0.88, source: '历年真题', basis: '主观题必考，占分高' },
    { content: '不定积分', kind: '知识点', level: 'medium', weight: 0.7, source: '教材例题', basis: '与定积分联动，先保基础' },
  ],
  note: '',
}

// 考前重点回顾列表（模块 7.3）演示数据：按权重从高到低的必看知识点
export const mockReview = {
  exam_id: 1,
  subject: '高等数学',
  exam_date: '2026-09-12',
  days_left: 5,
  items: [
    { name: '极限与连续', weight: 0.95, importance: 'high', suggest_hours: 3, source: '历年真题', basis: '全卷基础，失分影响大' },
    { name: '导数与微分', weight: 0.88, importance: 'high', suggest_hours: 3, source: '历年真题', basis: '主观题必考，占分高' },
    { name: '不定积分', weight: 0.7, importance: 'medium', suggest_hours: 2, source: '教材例题', basis: '与定积分联动，先保基础' },
    { name: '定积分的应用', weight: 0.62, importance: 'medium', suggest_hours: 2, source: '课后习题', basis: '常见计算题型' },
    { name: '微分方程初步', weight: 0.45, importance: 'low', suggest_hours: 1, source: '课堂笔记', basis: '低频，时间紧可后置' },
  ],
  note: '',
}

// 今日最重要的三件事（模块 7.4）演示数据：按权重+截止+压力打分置顶
export const mockTop3 = {
  pressure: 52.0,
  items: [
    { task_id: 1, title: '第3天：极限与连续', subject: '高等数学', plan_date: '2026-09-07', priority: 1, estimated_minutes: 120, score: 84.9, reason: '优先级高 · 距高等数学考试 5 天' },
    { task_id: 4, title: '第4天：导数应用专项', subject: '高等数学', plan_date: '2026-09-09', priority: 2, estimated_minutes: 90, score: 72.4, reason: '距高等数学考试 5 天' },
    { task_id: 2, title: '单词 Unit 1-3 记忆', subject: '大学英语', plan_date: '2026-09-07', priority: 2, estimated_minutes: 45, score: 61.5, reason: '距大学英语考试 11 天' },
  ],
  note: '',
}

// 学习时段推荐（模块 7.5）演示数据：按每日可用 4 小时分配到四个时段
export const mockTimeslots = {
  daily_hours: 4,
  learning_status: 'medium',
  slots: [
    { name: '早晨', start: '07:30', end: '09:00', minutes: 70, focus: '攻坚薄弱环节：极限与连续' },
    { name: '上午', start: '09:00', end: '11:30', minutes: 70, focus: '主攻高频重点（极限与连续 等）' },
    { name: '下午', start: '14:00', end: '16:30', minutes: 50, focus: '刷题练习，巩固当天所学' },
    { name: '晚上', start: '19:00', end: '21:00', minutes: 50, focus: '回顾重点 + 整理错题' },
  ],
  note: '',
}

// 低情绪减负与计划重排（模块 7.7）演示数据：按选项给出重排预览
export const mockRelief = {
  lighten: {
    option: 'lighten',
    daily_hours: 4,
    today_capacity: 120,
    moves: [
      { task_id: 5, title: '第5天：综合题与易错点', from_date: '2026-09-10', to_date: '2026-09-11', minutes: 150 },
    ],
    conflicts: [],
    summary: '将后移 1 个任务，今日负担相应减轻',
  },
  halfday: {
    option: 'halfday',
    daily_hours: 4,
    today_capacity: 0,
    moves: [
      { task_id: 1, title: '第3天：极限与连续', from_date: '2026-09-07', to_date: '2026-09-08', minutes: 120 },
      { task_id: 2, title: '单词 Unit 1-3 记忆', from_date: '2026-09-07', to_date: '2026-09-08', minutes: 45 },
      { task_id: 5, title: '第5天：综合题与易错点', from_date: '2026-09-10', to_date: '2026-09-11', minutes: 150 },
    ],
    conflicts: [
      { task_id: 5, title: '第5天：综合题与易错点', reason: '考前时间不足，无法在 2026-09-12 前安排' },
    ],
    summary: '将后移 3 个任务，另有 1 个任务考前排不下，需要取舍',
  },
}

// 管理端（模块 8）演示数据：课程/科目、账号、资料
export const mockAdminCourses = [
  { id: 1, name: '高等数学', code: 'MATH101', teacher: '张老师', credit: 5, term: '2024秋', note: '闭卷', created_at: '2026-09-01T08:00:00' },
  { id: 2, name: '大学英语', code: 'ENG101', teacher: '李老师', credit: 4, term: '2024秋', note: '闭卷', created_at: '2026-09-01T08:00:00' },
  { id: 3, name: '数据结构', code: 'CS201', teacher: '王老师', credit: 4, term: '2024秋', note: '开卷', created_at: '2026-09-01T08:00:00' },
]

export const mockAdminUsers = [
  { id: 1, username: 'demo', nickname: '演示同学', student_no: '20240000', major: '计算机', grade: '2024级', is_admin: true, is_banned: false, exam_count: 3, material_count: 4, created_at: '2026-09-01T08:00:00' },
  { id: 2, username: 'spammer', nickname: '广告小号', student_no: '20249999', major: '未知', grade: '2024级', is_admin: false, is_banned: true, exam_count: 0, material_count: 7, created_at: '2026-09-03T10:20:00' },
  { id: 3, username: 'lily', nickname: '莉莉', student_no: '20240012', major: '软件工程', grade: '2024级', is_admin: false, is_banned: false, exam_count: 2, material_count: 1, created_at: '2026-09-02T14:00:00' },
]

// 操作日志（9.4）演示数据：管理员可查最近的关键操作
export const mockAdminLogs = [
  { id: 108, user_id: 1, username: 'demo', action: 'AI 复习分析', target_type: 'analysis', target_id: 8, detail: '高等数学 · 生成 14 天复习计划', created_at: '2026-09-07T20:15:00' },
  { id: 107, user_id: 1, username: 'demo', action: '上传资料', target_type: 'material', target_id: 12, detail: '历年真题精选（2019-2023）（txt，解析成功）', created_at: '2026-09-07T19:40:00' },
  { id: 106, user_id: 1, username: 'demo', action: '修改考试', target_type: 'exam', target_id: 3, detail: '数据结构（字段：exam_date, note）', created_at: '2026-09-07T18:02:00' },
  { id: 105, user_id: 3, username: 'lily', action: '登录', target_type: '', target_id: null, detail: '登录成功', created_at: '2026-09-07T14:20:00' },
  { id: 104, user_id: 1, username: 'demo', action: '封禁账号', target_type: 'user', target_id: 2, detail: 'spammer', created_at: '2026-09-07T10:05:00' },
  { id: 103, user_id: 2, username: 'spammer', action: '上传资料', target_type: 'material', target_id: 13, detail: '某某刷单兼职【点击领取】（txt，解析成功）', created_at: '2026-09-06T22:30:00' },
]

export const mockAdminMaterials = [
  { id: 11, user_id: 1, username: 'demo', title: '高数期末复习笔记', source_type: '课堂笔记', file_type: 'txt', parse_status: 'done', created_at: '2026-09-05T09:00:00' },
  { id: 12, user_id: 1, username: 'demo', title: '历年真题精选（2019-2023）', source_type: '历年题', file_type: 'txt', parse_status: 'done', created_at: '2026-09-05T09:10:00' },
  { id: 13, user_id: 2, username: 'spammer', title: '某某刷单兼职【点击领取】', source_type: '其他', file_type: 'txt', parse_status: 'done', created_at: '2026-09-06T22:30:00' },
]

// 情绪记录（模块 7.6）演示数据：composite_score < 2.5 → need_relief=true 显示减负入口
export const mockMood = {
  record_date: '2026-09-07',
  mood_score: 3,
  emotion_item: 2.5,
  completion_item: 1.67,
  pressure_item: 3,
  streak_item: 0,
  composite_score: 2.1,
  suggestion: '状态偏低，建议减轻今日任务或暂停半天',
  need_relief: true,
}
