import { test } from 'node:test'
import assert from 'node:assert/strict'

import { noteTriggerClassName } from './note-text.tsx'

const DISPLAY_CLASSES = ['block', 'inline', 'inline-block', 'flex', 'inline-flex', 'grid', 'inline-grid', 'table', 'contents', 'flow-root']

// Classes the callers pass today (node card, nodes table, core card, cores table)
for (const extra of [undefined, 'mt-0.5', 'text-[10px] sm:text-xs']) {
  test(`note trigger keeps a working two-line clamp (className=${extra ?? 'none'})`, () => {
    const classes = noteTriggerClassName(extra).split(/\s+/)
    assert.ok(classes.includes('line-clamp-2'))
    const conflicting = classes.filter(c => DISPLAY_CLASSES.includes(c))
    assert.deepEqual(conflicting, [], `display utility overrides -webkit-box of line-clamp-2: ${conflicting.join(' ')}`)
  })
}
