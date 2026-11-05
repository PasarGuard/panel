import { test } from 'node:test'
import assert from 'node:assert/strict'

import type { UserResponse } from '@/service/api'
import { compareBySort, toUsersQueryParams } from './usersCache.ts'

const user = (id: number, username: string, createdAt: string, note = '') => ({ id, username, note, created_at: createdAt }) as unknown as UserResponse

test('a typed search with the default sort asks for best matches', () => {
  assert.equal(toUsersQueryParams({ search: '12345', sort: '-created_at' }).sort, 'relevance')
  assert.equal(toUsersQueryParams({ search: '12345', sort: '' }).sort, 'relevance')
})

test('a sort the admin picked, or no search, is left as is', () => {
  assert.equal(toUsersQueryParams({ search: '12345', sort: '-used_traffic' }).sort, '-used_traffic')
  assert.equal(toUsersQueryParams({ search: '  ', sort: '-created_at' }).sort, '-created_at')
  assert.equal(toUsersQueryParams({ sort: '-created_at' }).sort, '-created_at')
})

test('relevance order matches the server: exact, prefix, contains, note, newest first inside a group', () => {
  const exact = user(1, 'abc', '2026-01-01T00:00:00Z')
  const prefixOld = user(2, 'abcx', '2026-01-02T00:00:00Z')
  const prefixNew = user(3, 'abcy', '2026-01-05T00:00:00Z')
  const contains = user(4, 'xabc', '2026-01-06T00:00:00Z')
  const noteOnly = user(5, 'n1', '2026-01-07T00:00:00Z', 'see abc')
  const sorted = [noteOnly, contains, prefixOld, exact, prefixNew].sort((a, b) => compareBySort(a, b, 'relevance', 'abc'))
  assert.deepEqual(
    sorted.map(u => u.username),
    ['abc', 'abcy', 'abcx', 'xabc', 'n1'],
  )
})

test('with a picked sort only the exact username is pinned', () => {
  const exact = user(1, 'abc', '2026-01-01T00:00:00Z')
  const prefix = user(2, 'abcx', '2026-01-02T00:00:00Z')
  const noteOnly = user(3, 'n1', '2026-01-03T00:00:00Z', 'see abc')
  const sorted = [prefix, exact, noteOnly].sort((a, b) => compareBySort(a, b, '-created_at', 'abc'))
  assert.deepEqual(
    sorted.map(u => u.username),
    ['abc', 'n1', 'abcx'],
  )
})
