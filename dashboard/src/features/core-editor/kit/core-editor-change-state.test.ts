import { test } from 'node:test'
import assert from 'node:assert/strict'

import type { CoreResponse } from '@/service/api'
import { selectCoreEditorHasActualChanges } from '@/features/core-editor/kit/core-editor-change-state'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'

const core = {
  id: 7,
  name: 'main',
  type: 'xray',
  config: { inbounds: [], outbounds: [{ tag: 'direct', protocol: 'freedom' }] },
  exclude_inbound_tags: [],
  fallbacks_inbound_tags: [],
  note: 'EU config',
  sort_order: 0,
  created_at: '2026-01-01T00:00:00Z',
} as unknown as CoreResponse

const store = useCoreEditorStore
const hasChanges = () => selectCoreEditorHasActualChanges(store.getState())

test('core note is hydrated from the server and starts clean', () => {
  store.getState().reset()
  store.getState().initFromCore(core)
  assert.equal(store.getState().coreNote, 'EU config')
  assert.equal(hasChanges(), false)
})

test('editing only the note counts as a change and discard restores it', () => {
  store.getState().reset()
  store.getState().initFromCore(core)
  store.getState().setCoreNote('edited')
  assert.equal(hasChanges(), true)
  store.getState().discardDraft()
  assert.equal(store.getState().coreNote, 'EU config')
  assert.equal(hasChanges(), false)
})

test('whitespace-only note edits are not a change', () => {
  store.getState().reset()
  store.getState().initFromCore(core)
  store.getState().setCoreNote('  EU config  ')
  assert.equal(hasChanges(), false)
})

test('saved note becomes the new baseline', () => {
  store.getState().reset()
  store.getState().initFromCore(core)
  store.getState().setCoreNote('')
  assert.equal(hasChanges(), true)
  store.getState().markClean()
  assert.equal(hasChanges(), false)
  assert.equal(store.getState().persistedSnapshot?.coreNote, '')
})

test('core without a note (old records) hydrates to an empty note', () => {
  store.getState().reset()
  store.getState().initFromCore({ ...core, note: undefined } as unknown as CoreResponse)
  assert.equal(store.getState().coreNote, '')
  assert.equal(hasChanges(), false)
  store.getState().initNew('xray', 'new core')
  assert.equal(store.getState().coreNote, '')
})
