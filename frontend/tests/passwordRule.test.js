import test from 'node:test'
import assert from 'node:assert/strict'
import { passwordLengthRule } from '../src/utils/passwordRule.js'

test('账号三种设置密码流程按字符验证中文和表情，保持后端6–32字符边界', () => {
  for (const value of ['a'.repeat(6), '汉'.repeat(32), '🙂'.repeat(24), '🙂'.repeat(32)]) {
    let result = null
    passwordLengthRule({}, value, error => { result = error })
    assert.equal(result, undefined)
  }
  for (const value of ['', 'a'.repeat(5), '🙂'.repeat(3), '汉'.repeat(33), '🙂'.repeat(33)]) {
    let result
    passwordLengthRule({}, value, error => { result = error })
    assert.ok(result instanceof Error)
  }
})
