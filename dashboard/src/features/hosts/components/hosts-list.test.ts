import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('drag reorder sends only IDs and priorities to the priority endpoint', () => {
  const source = readFileSync(new URL('./hosts-list.tsx', import.meta.url), 'utf8')
  const handler = source.slice(source.indexOf('const handleDragEnd ='), source.indexOf('// Sort hosts by priority'))
  assert.match(handler, /fetcher<void>\('\/api\/hosts\/priorities'/)
  assert.match(handler, /body: updatedHosts\.map\(host => \(\{ id: host\.id, priority: host\.priority \}\)\)/)
  assert.doesNotMatch(handler, /modifyHosts|fragment_settings/)
})
