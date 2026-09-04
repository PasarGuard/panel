import assert from 'node:assert/strict'
import test from 'node:test'

import { createLatestRequestGuard } from './latest-request-guard.ts'

test('cancel invalidates a subscription rules reset before its response resolves', async () => {
  const guard = createLatestRequestGuard()
  const requestId = guard.begin()
  let resolveRequest!: () => void
  const pendingRequest = new Promise<void>(resolve => {
    resolveRequest = resolve
  })

  const reset = pendingRequest.then(() => guard.isCurrent(requestId))

  guard.invalidate()
  resolveRequest()

  assert.equal(await reset, false)
})

test('the current subscription rules reset remains applicable', () => {
  const guard = createLatestRequestGuard()
  const requestId = guard.begin()

  assert.equal(guard.isCurrent(requestId), true)
})
