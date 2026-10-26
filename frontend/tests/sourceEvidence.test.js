import { test } from 'node:test'
import assert from 'node:assert/strict'
import { excerptParts, mockEvidence, sourceRoute } from '../src/utils/sourceEvidence.js'

test('原文高亮只切分真实文本，保留换行和特殊字符', () => {
  assert.deepEqual(excerptParts({ context: '前文\n<script>积分</script>后文', highlight_start: 3, highlight_end: 22 }), ['前文\n', '<script>积分</script>', '后文'])
})
test('失效引用不生成资料链接，原文位置不放正文到URL', () => {
  assert.equal(sourceRoute({ status: 'changed' }, 1), null)
  const route=sourceRoute({status:'available',material_id:3,start:1500,end:1520,content_hash:'abc'},2)
  assert.equal(route.path,'/materials'); assert.equal(route.query.start,1500)
  assert.equal(Object.hasOwn(route.query,'context'),false)
})
test('演示引用按科目筛选，找不到不虚构出处或页码', () => {
  const rows=[{id:1,exam_id:1,parse_status:'done',text_preview:'积分的定义',title:'数学'}, {id:2,exam_id:2,parse_status:'done',text_preview:'积分 secret',title:'英语'}]
  const response=mockEvidence({name:'积分'},1,rows)
  assert.equal(response.items.length,1); assert.equal(response.items[0].material_id,1)
  assert.equal(response.items[0].page,null)
  assert.equal(mockEvidence({name:'不存在'},1,rows).items.length,0)
})
test('高亮边界钳制到文本范围，避免损坏引用截取异常', () => {
  assert.deepEqual(excerptParts({context:'abc',highlight_start:-5,highlight_end:99}),['','abc',''])
  assert.deepEqual(excerptParts({context:'abc',highlight_start:2,highlight_end:1}),['ab','','c'])
})
