import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build, cronHourIntervals, parse, validateCronExpression } from './cron-field'
import { validateXrayGeodata } from './xray-geodata'

test('daily, weekly and every-N-hours presets round-trip', () => {
  assert.deepEqual(parse('5 4 * * *'), { mode: 'daily', time: '04:05' })
  assert.deepEqual(parse('30 3 * * 0'), { mode: 'weekly', time: '03:30', day: 0 })
  for (const hours of cronHourIntervals) {
    assert.deepEqual(parse(`0 */${hours} * * *`), { mode: 'hours', hours })
  }
  for (const expression of ['5 4 * * *', '30 3 * * 0', ...cronHourIntervals.map(hours => `0 */${hours} * * *`)]) {
    assert.equal(build(parse(expression)), expression)
    assert.equal(validateCronExpression(expression), true)
  }
})

test('the disabled mode emits an empty value and an omitted cron passes geodata validation', () => {
  const state = parse('')
  assert.deepEqual(state, { mode: 'disabled' })
  assert.equal(build(state), '')
  assert.deepEqual(validateXrayGeodata({}), [])
  assert.equal(validateXrayGeodata({ cron: '' })[0]?.path, '/geodata/cron')
})

test('other schedules and out-of-range values stay editable as custom cron', () => {
  for (const expression of ['*/5 * * * *', '0 4 1 * *', '60 4 * * *', '0 24 * * *', '0 4 * * 7', '0 */5 * * *']) {
    assert.deepEqual(parse(expression), { mode: 'custom', expression })
    assert.equal(build(parse(expression)), expression)
  }
  assert.equal(build({ mode: 'custom', expression: '  0 4 1 * *  ' }), '0 4 1 * *')
})

test('validation accepts five-field Xray syntax and rejects extensions and invalid ranges', () => {
  for (const expression of ['*/5 * * * *', '0 4 1 * *', '0 4 ? JAN-MAR MON-FRI', '+0 +4 * * *']) {
    assert.equal(validateCronExpression(expression), true, expression)
  }
  for (const expression of ['@daily', '0 0 4 * * *', '60 4 * * *', '0 24 * * *', '0 4 * * 7', '0 4 L * *', '0 4 * * MON#2', '0 4 2W * *']) {
    assert.equal(validateCronExpression(expression), false, expression)
  }
})
