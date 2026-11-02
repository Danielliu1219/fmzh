import test from 'node:test'
import assert from 'node:assert/strict'
import { layoutMindmap, mindmapDetailBranches, wrapMindmapText } from '../src/utils/mindmapLayout.js'

const tree = (count, repeats = 5) => ({ name: '微积分复习', children: ['知识点', '考点'].map((name, group) => ({ name,
  children: Array.from({ length: count }, (_, index) => ({ name: `${group}类第${index}个知识点（含参数方程及复杂的长标题）`,
    children: [{ name: '依据：' + '资料中给出了相应概念、条件与典型题，需要结合原文进行复习。'.repeat(repeats) }, { name: '建议投入：180分钟' }] })) })) })

function assertReadableLayout(layout) {
  for (const node of layout.nodes) {
    assert.ok(node.x >= 0 && node.y >= 0)
    assert.ok(node.x + node.width <= layout.width)
    assert.ok(node.y + node.height <= layout.height)
    assert.ok(node.lines.length * 20 + 12 <= node.height)
  }
  for (let i = 0; i < layout.nodes.length; i++) {
    for (let j = i + 1; j < layout.nodes.length; j++) {
      const first = layout.nodes[i], second = layout.nodes[j]
      const overlapX = first.x < second.x + second.width && second.x < first.x + first.width
      const overlapY = first.y < second.y + second.height && second.y < first.y + first.height
      assert.equal(overlapX && overlapY, false, `节点 ${first.id} 与 ${second.id} 重叠`)
    }
  }
}

test('长依据与大量节点都完整位于画布内，所有节点矩形不相交', () => {
  const data = tree(11), before = JSON.stringify(data)
  const layout = layoutMindmap(data, { width: 1366 })
  assertReadableLayout(layout)
  assert.ok(layout.height > 460)
  assert.equal(layout.links.length, layout.nodes.length - 1)
  assert.equal(JSON.stringify(data), before)
  assert.ok(layoutMindmap(tree(11, 10), { width: 1366 }).height > layout.height)
  assert.ok(layoutMindmap(tree(16), { width: 1366 }).height > layout.height)
})

test('窄屏保留文字列宽供横向滚动，宽屏不压缩节点高度', () => {
  const data = tree(8)
  const narrow = layoutMindmap(data, { width: 342 }), wide = layoutMindmap(data, { width: 1800 })
  assertReadableLayout(narrow); assertReadableLayout(wide)
  assert.ok(narrow.width > 342)
  assert.equal(wide.width, 1800)
  assert.ok(narrow.height >= wide.height)
})

test('收起与展开依据会重新计算高度，同时保留原始内容', () => {
  const data = tree(6)
  const full = layoutMindmap(data), collapsed = layoutMindmap(data, { collapsed: mindmapDetailBranches(data) })
  assertReadableLayout(collapsed)
  assert.ok(collapsed.height < full.height)
  assert.ok(collapsed.nodes.every(node => node.depth <= 2))
  assert.ok(collapsed.nodes.some(node => node.expandable && !node.expanded))
  assert.deepEqual(layoutMindmap(data), full)
  const root = layoutMindmap(data, { collapsed: new Set(['0']) })
  assert.equal(root.nodes.length, 1)
  assert.equal(root.links.length, 0)
})

test('换行保留全部文字，包含中文、公式和无空格英文长词', () => {
  const text = '极限与连续\nlongcontinuousformula1234567890＋证明条件'
  const lines = wrapMindmapText(text, 6, value => Array.from(value).length)
  assert.equal(lines.join(''), text.replaceAll('\n', ''))
  assert.ok(lines.every(line => Array.from(line).length <= 6))
  assert.deepEqual(layoutMindmap(null), { nodes: [], links: [], width: 0, height: 0 })
})
