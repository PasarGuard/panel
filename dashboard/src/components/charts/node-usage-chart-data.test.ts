import { test } from 'node:test'
import assert from 'node:assert/strict'

import { buildNodeChartData, type ChartSeries } from './node-usage-chart-data.ts'

const GB = 1024 * 1024 * 1024
const series: ChartSeries[] = [
  { id: 1, name: 'node-a' },
  { id: 2, name: 'node-b' },
  { id: 3, name: 'node-c' },
]
const formatLabel = (periodStart: string) => periodStart

test('an aggregate-only usage response is not split evenly across nodes', () => {
  const statsBySource = {
    '-1': [{ period_start: '2026-01-01T00:00:00Z', uplink: 20 * GB, downlink: 10 * GB }],
  }

  const result = buildNodeChartData({ statsBySource, statsBySeries: statsBySource, seriesList: series, isScopedToCore: false, formatLabel })

  assert.deepEqual(result.chartData, [])
  assert.equal(result.perNodeBreakdownUnavailable, true)
  assert.equal(result.totalBytes, 30 * GB)
})

test('a per-node usage response keeps the measured per-node values', () => {
  const statsBySource = {
    '1': [{ period_start: '2026-01-01T00:00:00Z', uplink: 3 * GB, downlink: 1 * GB }],
    '2': [{ period_start: '2026-01-01T00:00:00Z', uplink: 0, downlink: 1 * GB }],
  }

  const result = buildNodeChartData({ statsBySource, statsBySeries: statsBySource, seriesList: series, isScopedToCore: false, formatLabel })

  assert.equal(result.perNodeBreakdownUnavailable, false)
  assert.equal(result.totalBytes, 5 * GB)
  assert.equal(result.chartData.length, 1)
  assert.equal(result.chartData[0]['node-a'], 4)
  assert.equal(result.chartData[0]['node-b'], 1)
  assert.equal(result.chartData[0]['node-c'], 0)
  assert.equal(result.chartData[0]['_uplink_node-a'], 3 * GB)
  assert.equal(result.chartData[0]['_downlink_node-b'], 1 * GB)
})
