import { test } from 'node:test'
import assert from 'node:assert/strict'

import { HostFormSchema } from './host-form.ts'

const keepaliveIsAccepted = (keepalive_seconds: number) => HostFormSchema.shape.wireguard_overrides.safeParse({ keepalive_seconds }).success

test('the host form keeps the WireGuard keepalive within the 65535 the panel accepts', () => {
  assert.equal(keepaliveIsAccepted(0), true)
  assert.equal(keepaliveIsAccepted(25), true)
  assert.equal(keepaliveIsAccepted(65535), true)
  assert.equal(keepaliveIsAccepted(65536), false)
  assert.equal(keepaliveIsAccepted(86400), false)
})
