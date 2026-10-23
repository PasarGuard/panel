import { test } from 'node:test'
import assert from 'node:assert/strict'

import { bytesToFormGigabytes, formGigabytesToBytes, gbToBytes } from './formatByte.ts'

test('an unchanged data limit keeps the stored bytes instead of the two-decimal form value', () => {
  // 1.5 GB (decimal) shows as 1.4 GiB in the form; saving 1.4 used to store 1503238554 bytes
  const stored = 1500000000
  assert.equal(bytesToFormGigabytes(stored), 1.4)
  assert.equal(formGigabytesToBytes(bytesToFormGigabytes(stored), stored), stored)

  const typedWithThreeDecimals = gbToBytes(1.125)!
  assert.equal(formGigabytesToBytes(bytesToFormGigabytes(typedWithThreeDecimals), typedWithThreeDecimals), typedWithThreeDecimals)
})

test('a changed data limit is converted from the form value', () => {
  assert.equal(formGigabytesToBytes(2, 1500000000), 2 * 1024 ** 3)
  assert.equal(formGigabytesToBytes(0, 1500000000), 0)
})

test('without a stored limit the form value is converted as before', () => {
  assert.equal(formGigabytesToBytes(1.4, undefined), gbToBytes(1.4))
  assert.equal(formGigabytesToBytes(1.4, null), gbToBytes(1.4))
  assert.equal(formGigabytesToBytes(0, 0), 0)
  assert.equal(formGigabytesToBytes('', 1500000000), undefined)
})
