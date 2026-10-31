import { test } from 'node:test'
import assert from 'node:assert/strict'

import { toPositiveWholeSeconds, toWholeSeconds } from './timeUnitSeconds.ts'

const HOUR = 60 * 60
const DAY = 24 * HOUR

test('fractional amounts become whole seconds, as the integer API fields require', () => {
  // 0.7 * 86400 is 60479.99999999999 in floating point, which the API rejects with a 422
  assert.equal(toWholeSeconds(0.7, DAY), 60480)
  assert.equal(toWholeSeconds(2.3, DAY), 198720)
  assert.equal(toWholeSeconds(1.1, HOUR), 3960)
  assert.ok(Number.isInteger(toWholeSeconds(0.1, 60)))
})

test('whole amounts are unchanged', () => {
  assert.equal(toWholeSeconds(30, DAY), 30 * DAY)
  assert.equal(toWholeSeconds(1, 1), 1)
  assert.equal(toWholeSeconds(0, DAY), 0)
})

test('an amount that rounds below one second is no adjustment at all', () => {
  // 0.1 seconds rounds to 0: the bulk expiry flow sent a zero second adjustment instead of blocking
  assert.equal(toPositiveWholeSeconds(0.1, 1), undefined)
  assert.equal(toPositiveWholeSeconds(0.4, 1), undefined)
  assert.equal(toPositiveWholeSeconds(0, 60), undefined)
  assert.equal(toPositiveWholeSeconds(-1, DAY), undefined)
  assert.equal(toPositiveWholeSeconds(Number.NaN, DAY), undefined)
  assert.equal(toPositiveWholeSeconds(0.5, 1), 1)
  assert.equal(toPositiveWholeSeconds(0.7, DAY), 60480)
})
