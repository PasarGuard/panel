import { test } from 'node:test'
import assert from 'node:assert/strict'
import { availableUserFields, userColumnOrder, defaultUserView, normalizeUserView, readUserView, userViewStorageKey, writeUserView } from './user-view-preferences.ts'

function withStorage(run: (data: Map<string, string>) => void) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  const data = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => {
        data.set(key, value)
      },
    },
  })
  try {
    run(data)
  } finally {
    if (previous) Object.defineProperty(globalThis, 'localStorage', previous)
    else Reflect.deleteProperty(globalThis, 'localStorage')
  }
}

test('only optional columns are available and device counts respect permission', () => {
  const allowed = availableUserFields(false)
  for (const field of ['creator', 'username', 'id', 'status', 'usage', 'expire', 'online_at', 'data_limit', 'lifetime_used_traffic']) {
    assert.equal((allowed as string[]).includes(field), false)
  }
  assert.equal(allowed.includes('hwid_count'), false)
  assert.equal(availableUserFields(true).includes('hwid_count'), true)
})

test('restores the original layout for malformed or unsupported preference documents', () => {
  for (const value of [null, true, [], 'bad', { version: 3 }, { desktop: ['note'] }]) {
    assert.deepEqual(normalizeUserView(value), defaultUserView())
  }
  assert.deepEqual(normalizeUserView({ version: 2, desktop: 'note' }), defaultUserView())
})

test('drops unknown and special fields, preserves optional ordering, and allows empty views', () => {
  const result = normalizeUserView({ version: 2, desktop: ['note', 'username', 'select', 'usage', 'note', 'created_at', 'obsolete', null], mobileExpanded: [] })
  assert.deepEqual(result.desktop, ['note', 'created_at'])
  assert.deepEqual(result.mobileExpanded, [])
  assert.deepEqual(normalizeUserView({ version: 2, desktop: [] }).desktop, [])
})

test('migrates the first customization version without moving special fields into columns', () => {
  const result = normalizeUserView({ version: 1, desktop: ['status', 'usage', 'expire', 'creator', 'note'], mobileSummary: ['usage', 'note'], mobileExpanded: ['creator', 'id', 'hwid_count'] })
  assert.deepEqual(result, { version: 2, desktop: ['note'], mobileExpanded: ['hwid_count'], showCreatedBy: true })
  assert.equal(normalizeUserView({ version: 1, desktop: ['note'] }).showCreatedBy, false)
  assert.equal('mobileSummary' in result, false)
})

test('reordering cannot move the original cells or put optional columns after actions', () => {
  const allowed = availableUserFields(true)
  assert.deepEqual(userColumnOrder(['note', 'created_at'], allowed), ['select', 'username', 'status', 'note', 'created_at', 'details', 'chevron'])
  assert.deepEqual(userColumnOrder(['hwid_count', 'note'], availableUserFields(false)), ['select', 'username', 'status', 'note', 'details', 'chevron'])
  assert.deepEqual(userColumnOrder([], allowed), ['select', 'username', 'status', 'details', 'chevron'])
})

test('saves desktop and mobile choices independently and isolates administrator accounts', () =>
  withStorage(() => {
    const view = { ...defaultUserView(), desktop: ['note'] as const }
    const saved = normalizeUserView(view)
    assert.equal(writeUserView('admin/one', saved), true)
    assert.deepEqual(readUserView('admin/one'), saved)
    assert.deepEqual(readUserView('admin/two'), defaultUserView())
    assert.notEqual(userViewStorageKey('admin/one'), userViewStorageKey('admin%2Fone'))
  }))

test('migrates legacy creator visibility and ignores legacy checkbox visibility', () =>
  withStorage(data => {
    data.set('pasarguard-users-show-created-by', 'false')
    data.set('pasarguard-users-show-selection-checkbox', 'false')
    const migrated = readUserView('admin')
    assert.equal(migrated.showCreatedBy, false)
    assert.equal('showSelectionCheckbox' in migrated, false)
    writeUserView('admin', defaultUserView())
    assert.equal(readUserView('admin').showCreatedBy, true)
  }))

test('corrupt JSON and blocked storage do not break the users page', () =>
  withStorage(data => {
    data.set(userViewStorageKey('admin'), '{broken')
    assert.deepEqual(readUserView('admin'), defaultUserView())
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('Storage denied')
      },
    })
    assert.deepEqual(readUserView('admin'), defaultUserView())
    assert.equal(writeUserView('admin', defaultUserView()), false)
  }))
