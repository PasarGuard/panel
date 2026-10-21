import { test } from 'node:test'
import assert from 'node:assert/strict'

import { streamFormsCommitBlock } from '@/features/core-editor/components/xray/stream-form-validity'
import type { StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'

const t = (key: string, options?: Record<string, unknown>) => `${key}|${String(options?.defaultValue)}`
const issue = (field: string, message: string, severity: StreamFieldIssue['severity'] = 'error'): StreamFieldIssue => ({ field, code: 'XCK_SEMANTIC_MASQUE_TEST', severity, message })

test('streamFormsCommitBlock: unparsed inputs come first, without running the kit check', () => {
  let checked = false
  const block = streamFormsCommitBlock(t, true, () => {
    checked = true
    return [issue('mtu', 'bad')]
  })
  assert.deepEqual(block, { title: 'coreEditor.streamForms.invalidInputs|Some fields have values that cannot be saved. Fix the ones marked in red.' })
  assert.equal(checked, false)
})

test('streamFormsCommitBlock: blocking kit issues give the title and at most six messages', () => {
  const issues = [issue('clients', 'backend'), issue('mux', 'only a warning', 'warning'), ...['a', 'b', 'c', 'd', 'e', 'f', 'g'].map(message => issue('user', message))]
  assert.deepEqual(
    streamFormsCommitBlock(t, false, () => issues),
    {
      title: 'coreEditor.streamForms.blockingTitle|Fix these MASQUE or XDrive settings first',
      description: 'a\nb\nc\nd\ne\nf',
    },
  )
})

test('streamFormsCommitBlock: nothing blocks without unparsed inputs or blocking issues', () => {
  assert.equal(
    streamFormsCommitBlock(t, false, () => []),
    null,
  )
  assert.equal(
    streamFormsCommitBlock(t, false, () => [issue('clients', 'backend'), issue('mux', 'warning', 'warning')]),
    null,
  )
})
