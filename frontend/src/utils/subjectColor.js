// ============================================================
// 科目颜色标签（用例 2.11）：全站统一的科目配色工具
// 色板取自全局设计系统（纸 × 墨 × 珊瑚）的状态色并做同风格延伸，
// 任何页面通过 subjectColor()/examColor() 取色，保证同一科目全站同色。
// 用户在「考试管理」为科目自选颜色（exam.color）时优先使用。
// ============================================================

// 统一色板：color 为主色（色点/描边），soft 为浅底（标签底色）
export const SUBJECT_PALETTE = [
  { color: '#e66348', soft: '#f8e1d7' }, // 珊瑚
  { color: '#35554c', soft: '#dfe8e2' }, // 墨绿
  { color: '#3f6f66', soft: '#ddeae5' }, // 青绿
  { color: '#a06a22', soft: '#f2e7cf' }, // 赭黄
  { color: '#b63a2e', soft: '#f6ddd7' }, // 朱红
  { color: '#5b6d9e', soft: '#e0e5f2' }, // 黛蓝
  { color: '#8c5b7f', soft: '#efdfec' }, // 藕紫
  { color: '#4e7a3f', soft: '#e2eedd' }, // 苔绿
]

// 按科目名稳定取色：同一科目名永远映射到同一颜色
export function subjectColor(subject) {
  const name = String(subject || '')
  let hash = 0
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return SUBJECT_PALETTE[hash % SUBJECT_PALETTE.length]
}

// 考试对象取色：用户设置过颜色（exam.color）优先，否则按科目名默认配色
export function examColor(exam) {
  if (exam && exam.color && exam.color.startsWith('#')) {
    const hit = SUBJECT_PALETTE.find((p) => p.color === exam.color)
    return hit || { color: exam.color, soft: exam.color }
  }
  return subjectColor(exam && exam.subject)
}

// 按考试 id 取色（日历/任务等只有 exam_id 的场景）：在组件里用
// const colorById = (id) => examColor(exams.value.find((e) => e.id === id)) 包装使用

// 个人头像色板（1.6 编辑个人资料用）
export const AVATAR_PALETTE = [
  '#0c1614', // 墨（默认）
  '#e66348', // 珊瑚
  '#35554c', // 墨绿
  '#a06a22', // 赭黄
  '#3f6f66', // 青绿
  '#5b6d9e', // 黛蓝
  '#8c5b7f', // 藕紫
  '#b63a2e', // 朱红
]
