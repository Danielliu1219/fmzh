const FONT_SIZE = 13
const LINE_HEIGHT = 20
const NODE_PADDING = 12
const SIBLING_GAP = 16
const COLUMN_GAP = 48
const OUTER_PADDING = 24
const COLUMN_WIDTHS = [180, 120, 300, 400]

// 无DOM时仍能计算布局；浏览器传入实际字体测量函数。
const approximateWidth = text => Array.from(text).reduce((sum, char) => sum + (/[^\u0000-\u00ff]/.test(char) ? FONT_SIZE : FONT_SIZE * .6), 0)

export function wrapMindmapText(text, width, measure = approximateWidth, depth = 0) {
  const lines = []
  for (const paragraph of String(text || '未命名').replace(/\r\n?/g, '\n').split('\n')) {
    let line = ''
    for (const character of Array.from(paragraph)) {
      if (line && measure(line + character, depth) > width) { lines.push(line); line = character }
      else line += character
    }
    lines.push(line)
  }
  return lines
}

export function layoutMindmap(data, { width = 1100, collapsed = new Set(), measure = approximateWidth } = {}) {
  if (!data) return { nodes: [], links: [], width: 0, height: 0 }
  let maxDepth = 0
  const prepare = (source, id, depth) => {
    maxDepth = Math.max(maxDepth, depth)
    const children = Array.isArray(source.children) ? source.children : []
    return { id, depth, name: String(source.name || '未命名'), expandable: children.length > 0,
      children: collapsed.has(id) ? [] : children.map((child, index) => prepare(child, `${id}.${index}`, depth + 1)) }
  }
  const root = prepare(data, '0', 0)
  const columns = Array.from({ length: maxDepth + 1 }, (_, depth) => COLUMN_WIDTHS[depth] || 400)
  const naturalWidth = columns.reduce((sum, value) => sum + value, 0) + COLUMN_GAP * maxDepth + 2 * OUTER_PADDING
  // 宽屏将余量留给长标题和依据；窄屏保留可读宽度，在组件内部横向滚动。
  const extra = Math.max(0, width - naturalWidth)
  columns[maxDepth] += extra
  const x = columns.map((_, depth) => OUTER_PADDING + columns.slice(0, depth).reduce((sum, value) => sum + value + COLUMN_GAP, 0))
  const measureBranch = node => {
    node.width = columns[node.depth]
    node.lines = wrapMindmapText(node.name, node.width - (node.expandable ? 60 : 36), measure, node.depth)
    node.height = Math.max(32, node.lines.length * LINE_HEIGHT + NODE_PADDING)
    node.children.forEach(measureBranch)
    const childrenHeight = node.children.reduce((sum, child) => sum + child.branchHeight, 0) + Math.max(0, node.children.length - 1) * SIBLING_GAP
    node.branchHeight = Math.max(node.height, childrenHeight)
  }
  measureBranch(root)
  const nodes = [], links = []
  const position = (node, top) => {
    const center = top + node.branchHeight / 2
    const visible = { id: node.id, name: node.name, depth: node.depth, lines: node.lines,
      x: x[node.depth], y: center - node.height / 2, width: node.width, height: node.height,
      expandable: node.expandable, expanded: node.children.length > 0 }
    nodes.push(visible)
    const childrenHeight = node.children.reduce((sum, child) => sum + child.branchHeight, 0) + Math.max(0, node.children.length - 1) * SIBLING_GAP
    let childTop = top + (node.branchHeight - childrenHeight) / 2
    for (const child of node.children) {
      const childCenter = childTop + child.branchHeight / 2
      const startX = visible.x + visible.width, endX = x[child.depth] + 10
      const middle = (startX + endX) / 2
      links.push({ id: child.id, path: `M ${startX} ${center} C ${middle} ${center}, ${middle} ${childCenter}, ${endX} ${childCenter}` })
      position(child, childTop)
      childTop += child.branchHeight + SIBLING_GAP
    }
  }
  position(root, OUTER_PADDING)
  return { nodes, links, width: Math.max(width, naturalWidth), height: root.branchHeight + OUTER_PADDING * 2 }
}

export function mindmapDetailBranches(data) {
  const ids = new Set()
  const visit = (node, id, depth) => {
    if (depth >= 2 && node.children?.length) ids.add(id)
    node.children?.forEach((child, index) => visit(child, `${id}.${index}`, depth + 1))
  }
  if (data) visit(data, '0', 0)
  return ids
}
