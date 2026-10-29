import test from 'node:test'
import assert from 'node:assert/strict'
import { SCORE_BANDS } from '../src/utils/scoreTargets.js'
import { applyRecommendationStrategy, refreshStrategy, splitMinutes, strategyFor, suggestedTime } from '../src/utils/recommendationStrategy.js'

const profile = (band = 'B+', changes = {}) => ({ target_band: band, target: 'medium', learning_status: 'medium', available_days: 7, daily_hours: 2, weak_chapters: [], ...changes })
const result = () => ({ knowledge_points: [{ name: '极限', weight: .8 }, { name: '积分', weight: .8 }], review_plan: [{ day: 1, date: '2000-01-01', title: '极限', estimated_minutes: 120, priority: 1 }, { day: 2, date: '2000-01-01', title: '积分', estimated_minutes: 120, priority: 2 }] })

test('10 档目标只改变练习侧重，保留全部分数绩点且总时长不增加', () => {
  const original = JSON.stringify(SCORE_BANDS)
  const ratios = SCORE_BANDS.map(band => {
    const data = applyRecommendationStrategy(result(), profile(band.id), '2026-10-29')
    assert.equal(data.strategy.planned_minutes, 240)
    assert.equal(data.knowledge_points.reduce((sum, k) => sum + k.suggest_minutes, 0), 240)
    assert.equal(data.strategy.phases.reduce((sum, p) => sum + p.percent, 0), 100)
    assert.equal(data.strategy.phases.reduce((sum, p) => sum + p.minutes, 0), 240)
    return data.strategy.phases.map(p => p.percent).join(',')
  })
  assert.equal(new Set(ratios).size, 10)
  assert.equal(JSON.stringify(SCORE_BANDS), original)
})

test('高目标仍先补薄弱基础，临考压缩综合练习', () => {
  const weak = strategyFor(profile('A', { learning_status: 'weak' }))
  const good = strategyFor(profile('A', { learning_status: 'good' }))
  assert.ok(weak.phases[0].percent > good.phases[0].percent)
  assert.ok(strategyFor(profile('A', { available_days: 2 })).phases[2].percent <= 10)
  const data = applyRecommendationStrategy(result(), profile('B', { weak_chapters: ['积分'] }), '2026-10-29')
  assert.ok(data.knowledge_points[1].suggest_minutes > data.knowledge_points[0].suggest_minutes)
  assert.equal(data.knowledge_points[1].weight, .8)
})

test('同日累计限额、超出天数说明和活动分钟守恒', () => {
  const data = result()
  data.review_plan.push({ ...data.review_plan[0], estimated_minutes: 90 }, { ...data.review_plan[0], day: 9, estimated_minutes: 40 })
  applyRecommendationStrategy(data, profile('B+', { daily_hours: .5, available_days: 2 }), '2026-10-29')
  assert.equal(data.strategy.deferred_minutes, 310)
  assert.deepEqual(data.review_plan.map(p => p.date), ['2026-10-29', '2026-10-30'])
  data.review_plan.forEach(p => assert.equal(p.activities.reduce((sum, a) => sum + a.minutes, 0), p.estimated_minutes))
})

test('零预算、1 分钟和反馈重排不会被最低时长放大', () => {
  for (const minutes of [0, 1, 2, 17]) {
    const data = applyRecommendationStrategy(result(), profile('D', { daily_hours: minutes / 60, available_days: 1 }), '2026-10-29')
    assert.equal(data.knowledge_points.reduce((sum, k) => sum + k.suggest_minutes, 0), minutes)
    assert.equal(data.strategy.planned_minutes, minutes)
    if (!minutes) assert.equal(suggestedTime(data.knowledge_points[0]), '本轮暂不安排')
  }
  const data = applyRecommendationStrategy(result(), profile(), '2026-10-29')
  data.review_plan = [{ ...data.review_plan[0], estimated_minutes: 23 }]
  refreshStrategy(data)
  assert.equal(data.strategy.planned_minutes, 23)
  assert.equal(data.strategy.phases.reduce((sum, p) => sum + p.minutes, 0), 23)
  assert.equal(data.knowledge_points.reduce((sum, k) => sum + k.suggest_minutes, 0), 23)
  assert.equal(suggestedTime({ suggest_hours: 1.5 }), '1.5 小时')
  assert.deepEqual(splitMinutes(2, [0, 0, 0]), [1, 1, 0])
  assert.deepEqual(splitMinutes(2, []), [])
})
