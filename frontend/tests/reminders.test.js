import test from 'node:test'
import assert from 'node:assert/strict'
import { reminderDate, notificationTime } from '../src/utils/reminders.js'

test('提醒按北京时间计算，提前量可跨日与跨月', () => {
  assert.equal(
    reminderDate('2026-11-01', '00:15', 30),
    '2026-10-31T15:45:00.000Z',
  )
  assert.equal(
    reminderDate('2026-10-17', '12:00', 60),
    '2026-10-17T03:00:00.000Z',
  )
})
test('零提前量与一整天提前量保留基准时刻', () => {
  assert.equal(
    reminderDate('2026-10-17', '09:00', 0),
    '2026-10-17T01:00:00.000Z',
  )
  assert.equal(
    reminderDate('2026-10-17', '09:00', 1440),
    '2026-10-16T01:00:00.000Z',
  )
})
test('通知显示明确使用北京时间，不受浏览器所在时区影响', () => {
  assert.match(
    notificationTime('2026-10-17T03:00:00+00:00'),
    /2026.*10.*17.*11:00/,
  )
})
