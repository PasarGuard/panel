import { test } from 'node:test'
import assert from 'node:assert/strict'

import { getSelectedRowIds, keepVisibleRowSelection, nextRowSelection } from './rowSelection.ts'

test('rows that left the table (other page, search or filter) are dropped from the selection', () => {
  // Ticked on page 1, then page 2 is shown: bulk delete used to send the hidden page 1 ids too
  const selection = { '2995': true, '2996': true, '2984': true }
  const pageTwo = ['2989', '2988', '2987', '2986', '2985', '2984', '2983']
  assert.deepEqual(keepVisibleRowSelection(selection, pageTwo), { '2984': true })
  assert.deepEqual(keepVisibleRowSelection(selection, []), {})
})

test('a selection of shown rows is returned as is, so the table does not re-render', () => {
  const selection = { '2': true, '3': true }
  assert.equal(keepVisibleRowSelection(selection, ['1', '2', '3']), selection)
  const empty = {}
  assert.equal(keepVisibleRowSelection(empty, ['1']), empty)
})

test('selected ids are numbers and unselected entries are skipped', () => {
  assert.deepEqual(getSelectedRowIds({ '7': true, '8': false, '9': true }), [7, 9])
})

test('a reset clears the selection even when rows left the table in the same render', () => {
  // A cleared selection used to come back: pruning the old selection ran after the reset and was applied last
  const selection = { '1': true, '2': true }
  assert.deepEqual(nextRowSelection(selection, ['1'], true), {})
  assert.deepEqual(nextRowSelection(selection, ['1', '2'], true), {})
  assert.deepEqual(nextRowSelection(selection, ['1'], false), { '1': true })
  assert.equal(nextRowSelection(selection, ['1', '2'], false), selection)
})
