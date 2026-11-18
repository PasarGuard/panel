import { test } from 'node:test'
import assert from 'node:assert/strict'

import { isOnlineWithinWindow, ONLINE_USERS_WINDOW_SECONDS } from './onlineStatus.ts'

test('a user the API lists as online is shown as online', () => {
  // online_at is written at most once a minute, so a connected user can be up to 120 seconds old
  assert.equal(isOnlineWithinWindow(30), true)
  assert.equal(isOnlineWithinWindow(90), true)
  assert.equal(isOnlineWithinWindow(ONLINE_USERS_WINDOW_SECONDS), true)
})

test('a user outside the API window is shown as offline', () => {
  assert.equal(isOnlineWithinWindow(ONLINE_USERS_WINDOW_SECONDS + 1), false)
  assert.equal(isOnlineWithinWindow(5 * 60), false)
})
