import { describe, expect, it } from 'bun:test'

import { getCurrentNodeStats } from '../src/utils/node-chart-stats'

describe('current node chart stats', () => {
  it('excludes deleted nodes from series, periods, and totals', () => {
    const stats = { '7': [{ period_start: '2026-10-18', count: 2 }], '104': [{ period_start: '2026-10-17', count: 900 }] }
    expect(getCurrentNodeStats(stats, [{ id: 7 }])).toEqual({ '7': stats['7'] })
    expect(stats['104'][0].count).toBe(900)
  })

  it('keeps all existing nodes regardless of connection status', () => {
    const nodes = [
      { id: 7, status: 'disabled' },
      { id: 104, status: 'error' },
    ]
    const stats = { '7': [1], '104': [2] }
    expect(getCurrentNodeStats(stats, nodes)).toEqual(stats)
  })

  it('keeps the unassigned user group only when requested', () => {
    const stats = { '0': [4], '7': [2], '104': [900] }
    expect(getCurrentNodeStats(stats, [{ id: 7 }], true)).toEqual({ '0': [4], '7': [2] })
    expect(getCurrentNodeStats(stats, [{ id: 7 }])).toEqual({ '7': [2] })
  })

  it('preserves the aggregate-only API fallback', () => {
    expect(getCurrentNodeStats({ '-1': [6] }, [{ id: 7 }])).toEqual({ '-1': [6] })
  })

  it('does not double-count aggregates or redistribute deleted-node usage', () => {
    expect(getCurrentNodeStats({ '-1': [6], '7': [2], '104': [4] }, [{ id: 7 }])).toEqual({ '7': [2] })
    expect(getCurrentNodeStats({ '-1': [6], '104': [6] }, [{ id: 7 }])).toEqual({})
  })

  it('does not create series when all nodes have been deleted', () => {
    expect(getCurrentNodeStats({ '7': [2], '104': [4] }, [])).toEqual({})
  })
})
