// 四川大学教务处：2017–2018 秋季学期起使用的本科成绩对照表。
// https://jwc.scu.edu.cn/info/1066/3444.htm
export const SCORE_BANDS = [
  { id: 'D', min: 60, max: 60, gpa: '1.0', range: '及格档', threshold: '及格', strategy: 'pass' },
  { id: 'D+', min: 61, max: 62, gpa: '1.3', range: '61–62 分', threshold: '61+', strategy: 'pass' },
  { id: 'C-', min: 63, max: 65, gpa: '1.7', range: '63–65 分', threshold: '63+', strategy: 'pass' },
  { id: 'C', min: 66, max: 69, gpa: '2.0', range: '66–69 分', threshold: '66+', strategy: 'pass' },
  { id: 'C+', min: 70, max: 72, gpa: '2.3', range: '70–72 分', threshold: '70+', strategy: 'medium' },
  { id: 'B-', min: 73, max: 75, gpa: '2.7', range: '73–75 分', threshold: '73+', strategy: 'medium' },
  { id: 'B', min: 76, max: 79, gpa: '3.0', range: '76–79 分', threshold: '76+', strategy: 'medium' },
  { id: 'B+', min: 80, max: 84, gpa: '3.3', range: '80–84 分', threshold: '80+', strategy: 'medium' },
  { id: 'A-', min: 85, max: 89, gpa: '3.7', range: '85–89 分', threshold: '85+', strategy: 'high' },
  { id: 'A', min: 90, max: 100, gpa: '4.0', range: '90–100 分', threshold: '90+', strategy: 'high' },
]

export const scoreBand = (id) => SCORE_BANDS.find((band) => band.id === id) || null
export const scoreBandText = (id) => {
  const band = scoreBand(id)
  return band ? `${band.range} · 绩点 ${band.gpa}` : ''
}

export function scoreGoalHint(id) {
  const band = scoreBand(id)
  if (!band) return '拖动滑条，选择你希望达到的分数区间。'
  if (band.min < 70) return '先拿稳高频基础分，优先复习核心概念与常见题型。'
  if (band.min < 80) return '覆盖主要考点，巩固常见题型，再针对薄弱章节补缺。'
  if (band.min < 90) return '在基础题稳定得分后，加强综合应用、解题准确率与易错点练习。'
  return '全面覆盖核心考点，增加综合难题、限时训练与细节查漏。'
}
