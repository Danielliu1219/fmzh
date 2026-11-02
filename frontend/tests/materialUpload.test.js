import test from 'node:test'
import assert from 'node:assert/strict'
import { addUploadFiles, MAX_MATERIAL_BYTES, runUploadBatch, uploadBytes, uploadTitle } from '../src/utils/materialUpload.js'

const file = (name, size = 100, path = name) => ({ name, size, webkitRelativePath: path, lastModified: 42 })

test('文件夹保留子目录的同名文件，重复选择去重，按单文件与总容量检查', () => {
  const first = file('试卷.pdf', 100, '往年题/2024/试卷.pdf')
  const second = file('试卷.pdf', 100, '往年题/2025/试卷.pdf')
  const selection = addUploadFiles([], [first, second, first, file('说明.exe'), file('大.pdf', MAX_MATERIAL_BYTES + 1), file('空.txt', 0)], 250)
  assert.equal(selection.accepted.length, 2)
  assert.equal(selection.rejected.length, 3)
  assert.equal(uploadBytes(selection.accepted), 200)
  const next = addUploadFiles(selection.accepted, [file('第三份.pdf', 100)], 250)
  assert.equal(next.accepted.length, 2)
  assert.match(next.rejected[0].reason, /容量/)
  assert.equal(addUploadFiles([], [file('边界.pdf', MAX_MATERIAL_BYTES)], MAX_MATERIAL_BYTES).accepted.length, 1)
})

test('成功项自动移出暂存区，失败项保留；重试只传失败文件', async () => {
  let queue = addUploadFiles([], [file('第一份.pdf'), file('第二份.pdf')]).accepted
  const received = []
  const result = await runUploadBatch(queue, async raw => {
    received.push(raw.name)
    if (raw.name === '第二份.pdf') throw new Error('临时失败')
    return { id: 1 }
  }, (item, error) => { if (!error) queue = queue.filter(row => row.id !== item.id) })
  assert.equal(result.succeeded.length, 1)
  assert.equal(queue.length, 1)
  await runUploadBatch(queue, async raw => { received.push(raw.name); return { id: 2 } }, (item, error) => {
    if (!error) queue = queue.filter(row => row.id !== item.id)
  })
  assert.deepEqual(received, ['第一份.pdf', '第二份.pdf', '第二份.pdf'])
  assert.equal(queue.length, 0)
  assert.equal(addUploadFiles(queue, [file('第三份.pdf')]).accepted.length, 1)
})

test('登录失效时停止队列，未上传项保留；批量标题分别使用文件名', async () => {
  const queue = addUploadFiles([], [file('一.txt'), file('二.txt')]).accepted
  let calls = 0
  await runUploadBatch(queue, async () => { calls++; throw { response: { status: 401 } } })
  assert.equal(calls, 1)
  assert.equal(queue.length, 2)
  assert.equal(uploadTitle(file('期末试题.pdf')), '期末试题')
})
