import type { NodeUsageStat, UserUsageStat } from '@/service/api'

export type UsageStat = NodeUsageStat | UserUsageStat

export type ChartSeries = {
  id: number
  name: string
}

export type NodeChartDataPoint = {
  time: string
  _period_start: string
  [key: string]: string | number
}

export const AGGREGATE_STATS_KEY = '-1'

const BYTES_PER_GB = 1024 * 1024 * 1024

const isNodeUsageStat = (point: UsageStat): point is NodeUsageStat => 'uplink' in point && 'downlink' in point

export const getTrafficBytes = (point: UsageStat) => {
  if ('total_traffic' in point) {
    return Number(point.total_traffic || 0)
  }
  return Number(point.uplink || 0) + Number(point.downlink || 0)
}

export const getDirectionalTraffic = (point: UsageStat) => {
  if (isNodeUsageStat(point) && !('total_traffic' in point)) {
    return {
      uplink: Number(point.uplink || 0),
      downlink: Number(point.downlink || 0),
    }
  }

  return {
    uplink: 0,
    downlink: 0,
  }
}

export const sumTrafficBytes = (stats: UsageStat[]) => stats.reduce((sum, point) => sum + getTrafficBytes(point), 0)

export type NodeChartDataInput = {
  statsBySource: Record<string, UsageStat[]>
  statsBySeries: Record<string, UsageStat[]>
  seriesList: ChartSeries[]
  isScopedToCore: boolean
  formatLabel: (periodStart: string) => string
}

export type NodeChartDataResult = {
  chartData: NodeChartDataPoint[]
  totalBytes: number
  perNodeBreakdownUnavailable: boolean
}

export const buildNodeChartData = ({ statsBySource, statsBySeries, seriesList, isScopedToCore, formatLabel }: NodeChartDataInput): NodeChartDataResult => {
  const statsKeys = Object.keys(statsBySource)
  if (statsKeys.length === 0) {
    return { chartData: [], totalBytes: 0, perNodeBreakdownUnavailable: false }
  }

  const hasIndividualNodeData = statsKeys.some(key => key !== AGGREGATE_STATS_KEY)

  if (!hasIndividualNodeData && Array.isArray(statsBySource[AGGREGATE_STATS_KEY])) {
    return { chartData: [], totalBytes: sumTrafficBytes(statsBySource[AGGREGATE_STATS_KEY]), perNodeBreakdownUnavailable: true }
  }

  const visibleStats = isScopedToCore ? seriesList.map(series => statsBySeries[String(series.id)] || []) : Object.values(statsBySource)

  const allPeriods = new Set<string>()
  visibleStats.forEach(statsArray => {
    statsArray.forEach(stat => allPeriods.add(stat.period_start))
  })

  const chartData = Array.from(allPeriods)
    .sort()
    .map(periodStart => {
      const row: NodeChartDataPoint = {
        time: formatLabel(periodStart),
        _period_start: periodStart,
      }

      seriesList.forEach(node => {
        const nodeStats = statsBySeries[String(node.id)]?.find(stat => stat.period_start === periodStart)
        if (!nodeStats) {
          row[node.name] = 0
          row[`_uplink_${node.name}`] = 0
          row[`_downlink_${node.name}`] = 0
          return
        }

        const directionalTraffic = getDirectionalTraffic(nodeStats)
        row[node.name] = getTrafficBytes(nodeStats) / BYTES_PER_GB
        row[`_uplink_${node.name}`] = directionalTraffic.uplink
        row[`_downlink_${node.name}`] = directionalTraffic.downlink
      })

      return row
    })

  const totalBytes = visibleStats.reduce((sum, statsArray) => sum + sumTrafficBytes(statsArray), 0)

  return { chartData, totalBytes, perNodeBreakdownUnavailable: false }
}
