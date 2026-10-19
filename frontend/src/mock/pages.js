// ============================================================
// 页面级静态演示数据：给「考试管理 / 复习资料 / AI 复习分析」三页
// 在无后端环境（GitHub Pages 在线预览、本机纯前端 UI 检查）下展示
// 与首页同一套演示数据（高数 5 天后 / 英语 11 天后 / 数据结构 14 天后）。
// 仅界面预览用；联调与答辩演示请以真实后端为准（USE_MOCK = false）。
// ============================================================
import { mockDashboard, getToday } from './dashboard'

// 考试列表（与首页 mock 同源；note 为页面补充字段）
export const mockExams = mockDashboard.exams.map((e) => ({ ...e, note: '' }))
mockExams[0].note = '闭卷'
mockExams[1].note = '含听力'

// 复习资料列表（与 MaterialOut 同构）
export const mockMaterials = [
  {
    id: 1, title: '高等数学 2021-2024 历年真题', exam_id: 1, source_type: '历年题',
    file_type: 'pdf', parse_status: 'done', description: '四年期末真题汇总',
    weight: 0.85, default_weight: 0.85,
    text_preview: '（静态演示文本）2024 年期末：一、极限计算（3 小题）；二、定积分应用；……\n2023 年期末：一、等价无穷小替换；二、导数与单调性；……',
  },
  {
    id: 2, title: '极限与连续 老师标注重点', exam_id: 1, source_type: '老师重点',
    file_type: 'docx', parse_status: 'done', description: '',
    weight: 1.0, default_weight: 1.0,
    text_preview: '（静态演示文本）老师标注重点：1. 极限的四则运算与等价无穷小；2. 连续性与间断点分类；3. 闭区间连续函数性质。',
  },
  {
    id: 3, title: '高数课堂笔记 第 1-6 章', exam_id: 1, source_type: '课堂笔记',
    file_type: 'pdf', parse_status: 'done', description: '',
    weight: 0.7, default_weight: 0.7,
    text_preview: '（静态演示文本）第 1 章 函数与极限：…… 第 2 章 导数与微分：……',
  },
  {
    id: 4, title: '英语期末高频词汇表', exam_id: 2, source_type: '老师重点',
    file_type: 'docx', parse_status: 'done', description: 'Unit 1-8 高频词',
    weight: 1.0, default_weight: 1.0,
    text_preview: '（静态演示文本）Unit 1-8 高频词汇共 240 个：abandon, abstract, accumulate …',
  },
  {
    id: 5, title: '英语阅读理解练习题 10 篇', exam_id: 2, source_type: '练习题',
    file_type: 'pdf', parse_status: 'done', description: '',
    weight: 0.85, default_weight: 0.85,
    text_preview: '（静态演示文本）Passage 1 … Passage 10（含答案与解析）',
  },
]

// 学习画像（4.1 用户画像采集的输出，完整态）
export const mockProfile = {
  target: 'pass',
  learning_status: 'weak',
  available_days: 5,
  daily_hours: 3,
  weak_chapters: ['极限与连续', '定积分应用'],
  is_complete: true,
  missing_fields: [],
}

// 复习分析结果（4.10 个性化复习方案生成的输出）
export const mockAnalysis = {
  course: '高等数学',
  summary:
    '按「保及格」目标生成：优先覆盖高频基础考点，压缩低频难题；未来 5 天、每天约 3 小时，先补极限与连续，再练导数与定积分。',
  knowledge_points: [
    { name: '极限与连续', weight: 0.95, importance: 'high', suggest_hours: 6, recommend_reason: '近四年真题每年必考，老师标注为重点', source: '历年题' },
    { name: '导数与微分', weight: 0.82, importance: 'high', suggest_hours: 4.5, recommend_reason: '高频计算题来源，课堂多次强调', source: '老师重点' },
    { name: '定积分及其应用', weight: 0.74, importance: 'medium', suggest_hours: 3.5, recommend_reason: '每年约 2 道大题，你标注为薄弱章节', source: '历年题' },
    { name: '微分中值定理', weight: 0.55, importance: 'medium', suggest_hours: 2, recommend_reason: '证明题常考；保及格目标下以理解结论为主', source: '历年题' },
    { name: '常微分方程初步', weight: 0.3, importance: 'low', suggest_hours: 1, recommend_reason: '近两年出现频率低，可放最后', source: '课堂笔记' },
  ],
  exam_focus: [
    { level: 'must', content: '极限的四则运算与等价无穷小替换', basis: '近 4 年每年必出（共 11 题）', source: '历年题', frequency: 4 },
    { level: 'must', content: '定积分的分部积分与换元', basis: '近 4 年每年 2 道大题', source: '历年题', frequency: 4 },
    { level: 'often', content: '导数应用的单调性与最值', basis: '近 4 年出现 3 次', source: '老师重点', frequency: 3 },
  ],
  question_types: [
    { type: '选择题', count: 10, frequency: 0.25, basis: '历年题选择题约占四分之一', source: '历年题' },
    { type: '填空题', count: 6, frequency: 0.15, basis: '历年题填空题稳定出现', source: '历年题' },
    { type: '计算题', count: 16, frequency: 0.4, basis: '历年题计算题占比最高', source: '历年题' },
    { type: '证明题', count: 4, frequency: 0.1, basis: '历年题证明题每年约 1 道', source: '历年题' },
    { type: '应用题', count: 4, frequency: 0.1, basis: '历年题末段常应用题', source: '历年题' },
  ],
  review_plan: [
    { day: 1, date: '2026-09-08', title: '核心概念与定义', estimated_minutes: 90, priority: 1, detail: '极限定义、连续性判定，过一遍课堂笔记第 1-2 章' },
    { day: 2, date: '2026-09-09', title: '高频题型刷题', estimated_minutes: 120, priority: 1, detail: '等价无穷小替换专项 30 题，整理错题本' },
    { day: 3, date: '2026-09-10', title: '导数与微分', estimated_minutes: 120, priority: 2, detail: '导数计算与单调性最值应用，重点过老师标注例题' },
    { day: 4, date: '2026-09-11', title: '定积分专项', estimated_minutes: 90, priority: 2, detail: '分部积分、换元积分各 15 题' },
    { day: 5, date: '2026-09-12', title: '综合题与易错点回顾', estimated_minutes: 150, priority: 3, detail: '历年真题整卷模考 1 套 + 错题本回顾' },
  ],
  quiz: [
    { question: 'x→0 时，与 x 等价的无穷小是？', options: ['sin x', '1−cos x', 'tan 2x', 'ln(1+x²)'], answer: 'A', knowledge_point: '极限与连续', analysis: 'sin x ~ x（x→0）；1−cos x ~ x²/2，tan 2x ~ 2x，ln(1+x²) ~ x²。' },
    { question: '∫₀¹ x·eˣ dx 的值是？', options: ['1', 'e−1', 'e', 'e+1'], answer: 'A', knowledge_point: '定积分及其应用', analysis: '分部积分：∫x·eˣdx = x·eˣ − eˣ，代入 0~1 得 (e−e)−(0−1) = 1。' },
    { question: '函数 f(x)=x³−3x 的极大值点是？', options: ['x=−1', 'x=1', 'x=0', 'x=3'], answer: 'A', knowledge_point: '导数与微分', analysis: "f'(x)=3x²−3，f'=0 得 x=±1；f''(−1)=−6<0，故 x=−1 为极大值点。" },
  ],
}

// 学习统计总览（与 StatsOverviewOut 同构；锚定 getToday()，与首页 mock 同一天）
const round3 = (x) => Math.round(x * 1000) / 1000
// 30 天每日专注分钟（最后 7 天合计 225，对齐 mockDashboard.extras.focus_minutes）
const MINUTES_30 = [30, 0, 45, 20, 0, 35, 50, 0, 25, 40, 0, 30, 15, 0, 20, 35, 0, 40, 25, 0, 30, 20, 0, 25, 0, 25, 30, 40, 60, 45]

const buildStats = (days) => {
  const base = new Date(`${getToday()}T00:00:00`)
  const daily = []
  for (let i = 0; i < days; i++) {
    const d = new Date(base)
    d.setDate(base.getDate() - (days - 1 - i))
    const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const minutes = MINUTES_30[30 - days + i] ?? 0
    const total = minutes > 0 ? (minutes >= 40 ? 3 : 2) : 0
    const done = total > 0 ? total - 1 : 0
    daily.push({ date, minutes, total, done, rate: total ? round3(done / total) : 0 })
  }
  const totalMinutes = daily.reduce((a, x) => a + x.minutes, 0)
  const gao = Math.round(totalMinutes * 0.55)
  const eng = Math.round(totalMinutes * 0.3)
  const subjects = [
    { exam_id: 1, subject: '高等数学', minutes: gao, total_tasks: 5, done_tasks: 2, rate: 0.4, exam_date: '2026-09-12', days_left: 5 },
    { exam_id: 2, subject: '大学英语', minutes: eng, total_tasks: 3, done_tasks: 1, rate: 0.333, exam_date: '2026-09-18', days_left: 11 },
    { exam_id: 3, subject: '数据结构', minutes: 0, total_tasks: 0, done_tasks: 0, rate: 0, exam_date: '2026-09-21', days_left: 14 },
  ]
  const free = totalMinutes - gao - eng
  if (free > 0) {
    subjects.push({ exam_id: null, subject: '未指定科目', minutes: free, total_tasks: 0, done_tasks: 0, rate: 0, exam_date: null, days_left: null })
  }
  return {
    range_days: days,
    start_date: daily[0]?.date ?? '',
    end_date: daily[daily.length - 1]?.date ?? '',
    total_minutes: totalMinutes,
    total_tasks: 8,
    done_tasks: 3,
    rate: 0.375,
    subjects,
    days: daily,
  }
}

export const mockStatsOverview = (days = 7) =>
  new Promise((resolve) => setTimeout(() => resolve(structuredClone(buildStats(days))), 600))
