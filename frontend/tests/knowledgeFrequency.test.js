import test from 'node:test'
import assert from 'node:assert/strict'
import { knowledgeFrequencyLabel } from '../src/utils/knowledgeFrequency.js'

test('知识点百分比沿用分析结果，不使用题型占比', () => {
  assert.equal(knowledgeFrequencyLabel({ name: '极限', weight: .18, occurrence_count: 4 }), '18% · 已定位 4 次')
})

test('无法核实的次数和空计数完全隐藏', () => {
  for (const count of [undefined, null, 0, -1, NaN]) {
    assert.equal(knowledgeFrequencyLabel({ weight: .48, occurrence_count: count }), '48%')
  }
})
