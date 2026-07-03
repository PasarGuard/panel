import { describe, expect, it } from 'vitest'
import { checkSessionIdRoomSize, sessionIdRoomSize, sessionIdTableLength } from '@/lib/xray-session-id-room-size'

describe('sessionIdTableLength', () => {
  it('resolves predefined Xray-core aliases', () => {
    expect(sessionIdTableLength('Base62')).toBe(62)
    expect(sessionIdTableLength('hex')).toBe(16)
    expect(sessionIdTableLength('number')).toBe(10)
  })

  it('falls back to the literal character count for a custom table', () => {
    expect(sessionIdTableLength('ab')).toBe(2)
    expect(sessionIdTableLength('0123456789abcdef')).toBe(16)
  })
})

describe('sessionIdRoomSize', () => {
  it('sums tableLen^k across the range', () => {
    expect(sessionIdRoomSize(2, 1, 1)).toBe(2)
    expect(sessionIdRoomSize(10, 1, 2)).toBe(10 + 100)
  })
})

describe('checkSessionIdRoomSize', () => {
  it('flags a too-small custom table/length combination', () => {
    expect(checkSessionIdRoomSize('ab', '1')).toBe('room-too-small')
  })

  it('accepts a large enough preset table with a long enough length', () => {
    expect(checkSessionIdRoomSize('Base62', '20')).toBeNull()
  })

  it('flags a non-positive from-length', () => {
    expect(checkSessionIdRoomSize('Base62', '0')).toBe('length-not-positive')
  })

  it('flags an unparseable length once a table is set (Xray has no default length)', () => {
    expect(checkSessionIdRoomSize('Base62', 'not-a-length')).toBe('length-not-positive')
  })

  it('flags a missing length once a table is set', () => {
    expect(checkSessionIdRoomSize('Base62', '')).toBe('length-not-positive')
  })

  it('has nothing to check without a table — Xray only validates sessionIDLength when sessionIDTable is set', () => {
    expect(checkSessionIdRoomSize('', '20')).toBeNull()
    expect(checkSessionIdRoomSize('', '')).toBeNull()
  })

  it('accepts a range whose upper bound alone clears the threshold', () => {
    expect(checkSessionIdRoomSize('hex', '1-30')).toBeNull()
  })
})
