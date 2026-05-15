import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ComponentProps } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis, TooltipProps } from 'recharts'
import { DateRange } from 'react-day-picker'
import { AlertTriangle, BarChart3, Calendar, Gauge, PieChart as PieChartIcon, TimerOff, Users, Wifi } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import UserCountStatsModal from '@/features/users/dialogs/user-count-stats-modal'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import useDirDetection from '@/hooks/use-dir-detection'
import { useChartViewType } from '@/hooks/use-chart-view-type'
import { Period, UserCountMetric, type GetUsersCountMetricParams, type NodeSimple, type UserCountMetricStat, useGetUsersCountMetric } from '@/service/api'
import {
  formatPeriodLabelForPeriod,
  formatTooltipDate,
  getChartQueryRangeFromDateRange,
  getChartQueryRangeFromShortcut,
  getXAxisIntervalForShortcut,
  toStatsRecord,
  TrafficShortcutKey,
} from '@/utils/chart-period-utils'

import { EmptyState } from './empty-state'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from './time-selector'
import { TimeRangeSelector } from '@/components/common/time-range-selector'

type CountDataPoint = {
  time: string
  _period_start: string
  [key: string]: string | number
}

type CountSeries = {
  key: string
  label: string
  color: string
  stackId?: string
}

type CountPieDataPoint = {
  name: string
  count: number
  percentage: number
  fill: string
}

type UserCountsChartProps = {
  nodeId?: number
  isSudo: boolean
  nodesData?: NodeSimple[]
}

type BarRadius = [number, number, number, number]
type CellRadiusProps = Partial<ComponentProps<typeof Cell>>

const BAR_RADIUS = 4
const SQUARE_RADIUS: BarRadius = [0, 0, 0, 0]

const getCellRadiusProps = (radius: BarRadius) => ({ radius }) as unknown as CellRadiusProps

const getDistinctColor = (index: number) => {
  const hues = [156, 212, 32, 280, 6, 188, 248, 318, 96, 44, 228, 12, 176, 268, 336, 128]
  const hue = hues[index % hues.length]
  const saturation = index % 3 === 0 ? 70 : index % 3 === 1 ? 62 : 78
  const lightness = index % 2 === 0 ? 42 : 52
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

const getStackedBarRadius = (row: CountDataPoint, seriesKey: string, stackSeries: CountSeries[]): BarRadius => {
  const visibleSeries = stackSeries.filter(item => Number(row[item.key] || 0) > 0)
  const visibleIndex = visibleSeries.findIndex(item => item.key === seriesKey)

  if (visibleIndex < 0) return SQUARE_RADIUS
  if (visibleSeries.length === 1) return [BAR_RADIUS, BAR_RADIUS, BAR_RADIUS, BAR_RADIUS]

  const isBottomSegment = visibleIndex === 0
  const isTopSegment = visibleIndex === visibleSeries.length - 1

  return [isTopSegment ? BAR_RADIUS : 0, isTopSegment ? BAR_RADIUS : 0, isBottomSegment ? BAR_RADIUS : 0, isBottomSegment ? BAR_RADIUS : 0]
}

function CountTooltip({
  active,
  payload,
  period,
  seriesByKey,
}: TooltipProps<number, string> & {
  period: Period
  seriesByKey: Record<string, CountSeries>
}) {
  const { t, i18n } = useTranslation()

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as CountDataPoint
  const formattedDate = data._period_start ? formatTooltipDate(data._period_start, period, i18n.language) : data.time
  const rows = payload
    .map(item => {
      const key = String(item.dataKey || '')
      return {
        key,
        label: seriesByKey[key]?.label || key,
        color: item.color || seriesByKey[key]?.color || 'hsl(var(--primary))',
        value: Number(item.value || 0),
      }
    })
    .filter(item => item.value > 0)
    .sort((a, b) => b.value - a.value)

  const total = rows.reduce((sum, item) => sum + item.value, 0)
  const visibleRows = rows.slice(0, 8)

  return (
    <div className="border-border bg-background max-w-[300px] min-w-[180px] rounded border p-2 text-xs shadow">
      <div className="text-muted-foreground mb-1 text-center font-semibold">
        <span dir="ltr">{formattedDate}</span>
      </div>
      <div className="text-muted-foreground mb-2 flex items-center justify-center gap-1">
        <span>{t('statistics.totalUsers', { defaultValue: 'Total' })}:</span>
        <span dir="ltr" className="text-foreground font-mono font-semibold">
          {total.toLocaleString()}
        </span>
      </div>
      <div className="grid gap-1">
        {visibleRows.map(item => (
          <div key={item.key} className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: item.color }} />
              <span className="truncate">{item.label}</span>
            </span>
            <span dir="ltr" className="shrink-0 font-mono font-semibold">
              {item.value.toLocaleString()}
            </span>
          </div>
        ))}
        {rows.length > visibleRows.length && <div className="text-muted-foreground pt-1 text-center text-[10px]">{t('statistics.clickForMore', { defaultValue: 'Click for more details' })}</div>}
      </div>
    </div>
  )
}

function CountPieTooltip({ active, payload }: TooltipProps<number, string>) {
  const { t } = useTranslation()

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as CountPieDataPoint

  return (
    <div className="border-border bg-background/95 rounded-lg border p-2 text-xs shadow-sm backdrop-blur-sm">
      <div className="mb-1 flex items-center gap-1.5">
        <div className="border-border/20 h-2.5 w-2.5 rounded-full border" style={{ backgroundColor: data.fill }} />
        <span className="text-foreground font-medium">{data.name}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.totalUsers', { defaultValue: 'Total' })}</span>
        <span dir="ltr" className="text-foreground font-mono font-semibold">
          {data.count.toLocaleString()}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.percentage', { defaultValue: 'Percentage' })}</span>
        <span dir="ltr" className="text-foreground font-mono">{`${data.percentage.toFixed(1)}%`}</span>
      </div>
    </div>
  )
}

export function UserCountsChart({ nodeId, isSudo, nodesData = [] }: UserCountsChartProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const chartViewType = useChartViewType()

  const [selectedMetric, setSelectedMetric] = useState<UserCountMetric>(UserCountMetric.online)
  const [chartView, setChartView] = useState<'bar' | 'pie'>('bar')
  const [selectedAdmin, setSelectedAdmin] = useState<string>('all')
  const [groupByNode, setGroupByNode] = useState(false)
  const [selectedTime, setSelectedTime] = useState<TrafficShortcutKey>('1w')
  const [showCustomRange, setShowCustomRange] = useState(false)
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [windowWidth, setWindowWidth] = useState<number>(() => (typeof window !== 'undefined' ? window.innerWidth : 1024))
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedData, setSelectedData] = useState<CountDataPoint | null>(null)
  const [currentDataIndex, setCurrentDataIndex] = useState(0)

  const activeQueryRange = useMemo(() => {
    if (showCustomRange && customRange?.from && customRange?.to) {
      return getChartQueryRangeFromDateRange(customRange, selectedTime)
    }

    return getChartQueryRangeFromShortcut(selectedTime, new Date(), { minuteForOneHour: true })
  }, [showCustomRange, customRange, selectedTime])

  const activePeriod = activeQueryRange.period
  const canGroupByNode = isSudo && nodeId === undefined && selectedMetric === UserCountMetric.online
  const effectiveGroupByNode = canGroupByNode && groupByNode
  const isNodeScopedCounts = nodeId !== undefined || effectiveGroupByNode
  const effectiveMetric = isNodeScopedCounts ? UserCountMetric.online : selectedMetric
  const adminParam = useMemo(() => (isSudo && selectedAdmin !== 'all' ? [selectedAdmin] : undefined), [isSudo, selectedAdmin])

  const metricParams = useMemo<GetUsersCountMetricParams>(
    () => ({
      period: activePeriod,
      start: activeQueryRange.startDate,
      end: activeQueryRange.endDate,
      group_by_node: effectiveGroupByNode,
      ...(nodeId !== undefined ? { node_id: nodeId } : {}),
      ...(adminParam ? { admin: adminParam } : {}),
    }),
    [activePeriod, activeQueryRange.startDate, activeQueryRange.endDate, effectiveGroupByNode, nodeId, adminParam],
  )

  const {
    data: metricCountsData,
    isLoading: isLoadingMetricCounts,
    error: metricCountsError,
  } = useGetUsersCountMetric(effectiveMetric, metricParams, {
    query: {
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const metricLabels = useMemo<Record<UserCountMetric, string>>(
    () => ({
      [UserCountMetric.online]: t('statistics.onlineUsers', { defaultValue: 'Online Users' }),
      [UserCountMetric.expired]: t('statistics.expiredUsers', { defaultValue: 'Expired Users' }),
      [UserCountMetric.limited]: t('statistics.limitedUsers', { defaultValue: 'Limited Users' }),
    }),
    [t],
  )

  const metricColors = useMemo<Record<UserCountMetric, string>>(
    () => ({
      [UserCountMetric.online]: 'hsl(var(--chart-2))',
      [UserCountMetric.expired]: 'hsl(var(--chart-4))',
      [UserCountMetric.limited]: 'hsl(var(--chart-5))',
    }),
    [],
  )

  const metricIcons = useMemo<Record<UserCountMetric, LucideIcon>>(
    () => ({
      [UserCountMetric.online]: Wifi,
      [UserCountMetric.expired]: TimerOff,
      [UserCountMetric.limited]: Gauge,
    }),
    [],
  )

  const renderMetricLabel = useCallback(
    (metric: UserCountMetric, trigger = false) => {
      const Icon = metricIcons[metric]
      if (trigger) {
        return (
          <div className="flex min-w-0 items-center gap-1.5">
            <Icon className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{metricLabels[metric]}</span>
          </div>
        )
      }

      return (
        <span className="flex min-w-0 items-center gap-1.5">
          <Icon className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{metricLabels[metric]}</span>
        </span>
      )
    },
    [metricIcons, metricLabels],
  )

  const getGroupLabel = useCallback(
    (groupKey: string) => {
      if (groupKey === '-1') return t('all', { defaultValue: 'All' })
      if (groupKey === '0') return t('statistics.unassignedNode', { defaultValue: 'Unassigned Node' })

      const node = nodesData.find(item => String(item.id) === groupKey)
      return node?.name || t('statistics.nodeWithId', { defaultValue: 'Node {{id}}', id: groupKey })
    },
    [nodesData, t],
  )

  const metricStatsByGroup = useMemo(() => toStatsRecord<UserCountMetricStat>(metricCountsData?.stats), [metricCountsData?.stats])

  const groupKeys = useMemo(() => {
    const keys = Object.keys(metricStatsByGroup)
    return keys.sort((a, b) => {
      if (a === '-1') return -1
      if (b === '-1') return 1
      if (a === '0') return 1
      if (b === '0') return -1
      return Number(a) - Number(b)
    })
  }, [metricStatsByGroup])

  const series = useMemo<CountSeries[]>(() => {
    if (effectiveGroupByNode) {
      return groupKeys.map((groupKey, index) => ({
        key: `node_${groupKey}`,
        label: getGroupLabel(groupKey),
        color: getDistinctColor(index),
        stackId: 'nodes',
      }))
    }

    return [{ key: 'count', label: metricLabels[effectiveMetric], color: metricColors[effectiveMetric] }]
  }, [effectiveGroupByNode, effectiveMetric, getGroupLabel, groupKeys, metricColors, metricLabels])

  const seriesByKey = useMemo(
    () =>
      series.reduce<Record<string, CountSeries>>((acc, item) => {
        acc[item.key] = item
        return acc
      }, {}),
    [series],
  )

  const chartConfig = useMemo<ChartConfig>(
    () =>
      series.reduce<ChartConfig>((config, item) => {
        config[item.key] = { label: item.label, color: item.color }
        return config
      }, {}),
    [series],
  )

  const stackedSeries = useMemo(() => series.filter(item => item.stackId), [series])

  const chartData = useMemo<CountDataPoint[]>(() => {
    const periods = new Set<string>()

    Object.values(metricStatsByGroup).forEach(statsArray => {
      statsArray.forEach(stat => periods.add(stat.period_start))
    })

    return Array.from(periods)
      .sort()
      .map(periodStart => {
        const row: CountDataPoint = {
          time: formatPeriodLabelForPeriod(periodStart, activePeriod, i18n.language),
          _period_start: periodStart,
        }

        series.forEach(item => {
          row[item.key] = 0
        })

        if (effectiveGroupByNode) {
          groupKeys.forEach(groupKey => {
            const stat = metricStatsByGroup[groupKey]?.find(point => point.period_start === periodStart)
            row[`node_${groupKey}`] = stat ? Number(stat.count || 0) : 0
          })
        } else {
          Object.values(metricStatsByGroup).forEach(statsArray => {
            const stat = statsArray.find(point => point.period_start === periodStart)
            if (stat) row.count = Number(row.count || 0) + Number(stat.count || 0)
          })
        }

        return row
      })
  }, [activePeriod, effectiveGroupByNode, groupKeys, i18n.language, metricStatsByGroup, series])

  const singleMetricTotal = useMemo(
    () =>
      Object.values(metricStatsByGroup).reduce((sum, statsArray) => {
        return sum + statsArray.reduce((innerSum, stat) => innerSum + Number(stat.count || 0), 0)
      }, 0),
    [metricStatsByGroup],
  )

  const pieData = useMemo<CountPieDataPoint[]>(() => {
    if (!effectiveGroupByNode || chartData.length === 0) return []

    const groupsWithCounts = series
      .map(item => ({
        name: item.label,
        count: chartData.reduce((sum, row) => sum + Number(row[item.key] || 0), 0),
        fill: item.color,
      }))
      .filter(item => item.count > 0)

    const total = groupsWithCounts.reduce((sum, item) => sum + item.count, 0)

    return groupsWithCounts
      .map(item => ({
        ...item,
        percentage: total > 0 ? (item.count * 100) / total : 0,
      }))
      .sort((a, b) => b.count - a.count)
  }, [chartData, effectiveGroupByNode, series])

  const pieChartConfig = useMemo<ChartConfig>(
    () =>
      pieData.reduce<ChartConfig>((config, point) => {
        config[point.name] = { label: point.name, color: point.fill }
        return config
      }, {}),
    [pieData],
  )

  const piePaddingAngle = pieData.length > 1 ? 1 : 0

  const xAxisInterval = useMemo(() => {
    if (showCustomRange && customRange?.from && customRange?.to) {
      if (activePeriod === Period.hour || activePeriod === Period.minute) {
        return Math.max(1, Math.floor(chartData.length / 8))
      }

      const daysDiff = Math.ceil(Math.abs(customRange.to.getTime() - customRange.from.getTime()) / (1000 * 60 * 60 * 24))
      if (daysDiff > 30) return Math.max(1, Math.floor(chartData.length / 5))
      if (daysDiff > 7) return Math.max(1, Math.floor(chartData.length / 8))
      return 0
    }

    if (windowWidth < 500 && selectedTime === '1w') {
      return chartData.length <= 4 ? 0 : Math.max(1, Math.floor(chartData.length / 4))
    }

    return getXAxisIntervalForShortcut(selectedTime, chartData.length, { minuteForOneHour: true })
  }, [activePeriod, chartData.length, customRange, selectedTime, showCustomRange, windowWidth])

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth)

    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (!canGroupByNode && groupByNode) {
      setGroupByNode(false)
    }
  }, [canGroupByNode, groupByNode])

  useEffect(() => {
    if (!effectiveGroupByNode && chartView === 'pie') {
      setChartView('bar')
    }
  }, [chartView, effectiveGroupByNode])

  useEffect(() => {
    if (isNodeScopedCounts && selectedMetric !== UserCountMetric.online) {
      setSelectedMetric(UserCountMetric.online)
    }
  }, [isNodeScopedCounts, selectedMetric])

  const handleTimeSelect = useCallback((value: string) => {
    setSelectedTime(value as TrafficShortcutKey)
    setShowCustomRange(false)
    setCustomRange(undefined)
  }, [])

  const handleCustomRangeChange = useCallback((range: DateRange | undefined) => {
    setCustomRange(range)
    if (range?.from && range?.to) {
      setShowCustomRange(true)
    }
  }, [])

  const handleModalNavigate = useCallback(
    (index: number) => {
      if (!chartData[index]) return
      setCurrentDataIndex(index)
      setSelectedData(chartData[index])
    },
    [chartData],
  )

  const handleChartPointClick = useCallback(
    (data: unknown) => {
      if (!effectiveGroupByNode) return

      const chartClick = data as { activeTooltipIndex?: unknown; activePayload?: Array<{ payload?: unknown }> } | null
      const clickedIndex = typeof chartClick?.activeTooltipIndex === 'number' ? chartClick.activeTooltipIndex : -1
      const clickedData = (chartClick?.activePayload?.[0]?.payload ?? (clickedIndex >= 0 ? chartData[clickedIndex] : undefined)) as CountDataPoint | undefined
      if (!clickedData) return

      const activeSeriesCount = series.filter(item => Number(clickedData[item.key] || 0) > 0).length
      if (activeSeriesCount <= 0) return

      const resolvedIndex = clickedIndex >= 0 ? clickedIndex : chartData.findIndex(item => item._period_start === clickedData._period_start)
      setCurrentDataIndex(resolvedIndex >= 0 ? resolvedIndex : 0)
      setSelectedData(clickedData)
      setModalOpen(true)
    },
    [chartData, effectiveGroupByNode, series],
  )

  const yAxisWidth = effectiveGroupByNode ? 42 : 32
  const EffectiveMetricIcon = metricIcons[effectiveMetric]

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 xl:flex-row">
          <div className="flex flex-1 flex-col gap-2 border-b px-4 py-3 xl:px-6 xl:py-4">
            <div className="flex min-w-0 flex-col justify-center gap-1 pt-2">
              <CardTitle className="mb-0.5 flex items-center gap-2">
                <Users className="text-muted-foreground h-4 w-4 shrink-0" />
                <span>{t('statistics.userCountChart', { defaultValue: 'User Count' })}</span>
              </CardTitle>
              <CardDescription>{t('statistics.userCountChartDescription', { defaultValue: 'Online, expired, and limited user activity counts over time' })}</CardDescription>
              <p className="text-muted-foreground flex items-start gap-1.5 text-xs">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  {t('statistics.userCountChartAccuracyNote', {
                    defaultValue:
                      'Changing user status can make this chart show inaccurate historical data. Resetting usage only removes chart history when chart-data cleanup is enabled in the environment.',
                  })}
                </span>
              </p>
            </div>
            <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
              <div className="flex w-full min-w-0 items-center gap-2 sm:w-auto sm:flex-none">
                <TimeSelector selectedTime={selectedTime} setSelectedTime={handleTimeSelect} shortcuts={TRAFFIC_TIME_SELECTOR_SHORTCUTS} maxVisible={5} className="w-full sm:w-fit" />
                <button
                  type="button"
                  aria-label={t('statistics.customRange', { defaultValue: 'Custom Range' })}
                  className={`shrink-0 rounded border p-1 ${showCustomRange ? 'bg-muted' : ''}`}
                  onClick={() => {
                    const next = !showCustomRange
                    setShowCustomRange(next)
                    if (!next) {
                      setCustomRange(undefined)
                    }
                  }}
                >
                  <Calendar className="h-4 w-4" />
                </button>
              </div>
              {isNodeScopedCounts ? (
                <div className="bg-muted/20 text-muted-foreground flex h-9 w-full items-center gap-1.5 rounded-md border px-3 text-xs sm:w-[204px]">{renderMetricLabel(UserCountMetric.online)}</div>
              ) : (
                <Select value={selectedMetric} onValueChange={value => setSelectedMetric(value as UserCountMetric)}>
                  <SelectTrigger className="h-9 w-full text-xs sm:w-[204px]">{renderMetricLabel(selectedMetric, true)}</SelectTrigger>
                  <SelectContent>
                    <SelectItem value={UserCountMetric.online}>{renderMetricLabel(UserCountMetric.online)}</SelectItem>
                    <SelectItem value={UserCountMetric.expired}>{renderMetricLabel(UserCountMetric.expired)}</SelectItem>
                    <SelectItem value={UserCountMetric.limited}>{renderMetricLabel(UserCountMetric.limited)}</SelectItem>
                  </SelectContent>
                </Select>
              )}
              {isSudo && <AdminFilterCombobox value={selectedAdmin} onValueChange={username => setSelectedAdmin(username)} className="w-full sm:w-[220px] sm:shrink-0" />}
              {canGroupByNode && (
                <label className="bg-muted/20 text-muted-foreground flex h-9 w-full items-center justify-between gap-3 rounded-md border px-3 text-xs sm:w-auto sm:justify-start">
                  <span className="flex items-center gap-1.5 whitespace-nowrap">
                    <Users className="h-3.5 w-3.5" />
                    {t('statistics.groupByNode', { defaultValue: 'Group by node' })}
                  </span>
                  <Switch checked={effectiveGroupByNode} onCheckedChange={setGroupByNode} />
                </label>
              )}
              {effectiveGroupByNode && (
                <div className="bg-muted/30 inline-flex h-8 shrink-0 items-center gap-1 rounded-md border p-1">
                  <button
                    type="button"
                    aria-label={chartViewType === 'area' ? t('theme.chartViewArea', { defaultValue: 'Area chart' }) : t('statistics.barChart', { defaultValue: 'Bar chart' })}
                    className={`inline-flex h-6 w-6 items-center justify-center rounded ${chartView === 'bar' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground'}`}
                    onClick={() => setChartView('bar')}
                  >
                    <BarChart3 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label={t('statistics.pieChart', { defaultValue: 'Pie chart' })}
                    className={`inline-flex h-6 w-6 items-center justify-center rounded ${chartView === 'pie' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground'}`}
                    onClick={() => setChartView('pie')}
                  >
                    <PieChartIcon className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
            {showCustomRange && (
              <div className="flex w-full">
                <TimeRangeSelector onRangeChange={handleCustomRangeChange} initialRange={customRange} className="w-full" />
              </div>
            )}
          </div>
          <div className="m-0 flex min-w-[180px] flex-col justify-center gap-2 p-4 xl:border-l xl:p-5 xl:px-6">
            <span className="text-muted-foreground text-sm">{t('statistics.countDuringPeriod', { defaultValue: 'Count During Period' })}</span>
            {isLoadingMetricCounts ? (
              <div className="flex justify-center">
                <Skeleton className="h-5 w-24" />
              </div>
            ) : (
              <span dir="ltr" className="text-foreground flex items-center justify-center gap-2 text-lg">
                <EffectiveMetricIcon className="text-muted-foreground h-4 w-4" />
                {chartData.length > 0 ? singleMetricTotal.toLocaleString() : <span className="text-muted-foreground">—</span>}
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent dir={dir} className="px-4 pt-4 sm:px-6 sm:pt-8">
          {isLoadingMetricCounts ? (
            <div className="flex max-h-[300px] min-h-[150px] w-full items-center justify-center sm:max-h-[400px] sm:min-h-[200px]">
              <Skeleton className="h-[250px] w-full sm:h-[300px]" />
            </div>
          ) : metricCountsError ? (
            <EmptyState type="error" className="max-h-[300px] min-h-[150px] sm:max-h-[400px] sm:min-h-[200px]" />
          ) : (
            <div className="mx-auto w-full max-w-7xl">
              <ChartContainer dir="ltr" config={effectiveGroupByNode && chartView === 'pie' ? pieChartConfig : chartConfig} className="h-[220px] w-full overflow-x-auto sm:h-[320px] lg:h-[400px]">
                {chartData.length > 0 && (!effectiveGroupByNode || chartView === 'bar') ? (
                  chartViewType === 'area' ? (
                    <AreaChart accessibilityLayer data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }} onClick={handleChartPointClick}>
                      <defs>
                        {series.map(item => (
                          <linearGradient key={item.key} id={`user-count-gradient-${item.key}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={item.color} stopOpacity={0.36} />
                            <stop offset="100%" stopColor={item.color} stopOpacity={0.05} />
                          </linearGradient>
                        ))}
                      </defs>
                      <CartesianGrid direction="ltr" vertical={false} />
                      <XAxis
                        direction="ltr"
                        dataKey="time"
                        tickLine={false}
                        tickMargin={8}
                        axisLine={false}
                        interval={xAxisInterval}
                        minTickGap={5}
                        tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 8, fontWeight: 500 }}
                      />
                      <YAxis
                        direction="ltr"
                        tickLine={false}
                        axisLine={false}
                        allowDecimals={false}
                        width={yAxisWidth}
                        tickMargin={2}
                        tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 8, fontWeight: 500 }}
                      />
                      <ChartTooltip cursor={false} content={props => <CountTooltip {...(props as TooltipProps<number, string>)} period={activePeriod} seriesByKey={seriesByKey} />} />
                      {series.map(item => (
                        <Area
                          key={item.key}
                          dataKey={item.key}
                          name={item.label}
                          type="monotone"
                          fill={`url(#user-count-gradient-${item.key})`}
                          stroke={item.color}
                          strokeWidth={1.8}
                          dot={false}
                          activeDot={{ r: 4 }}
                          stackId={item.stackId}
                          cursor={effectiveGroupByNode ? 'pointer' : undefined}
                        />
                      ))}
                    </AreaChart>
                  ) : (
                    <BarChart accessibilityLayer data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }} onClick={handleChartPointClick}>
                      <CartesianGrid direction="ltr" vertical={false} />
                      <XAxis
                        direction="ltr"
                        dataKey="time"
                        tickLine={false}
                        tickMargin={8}
                        axisLine={false}
                        interval={xAxisInterval}
                        minTickGap={5}
                        tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 8, fontWeight: 500 }}
                      />
                      <YAxis
                        direction="ltr"
                        tickLine={false}
                        axisLine={false}
                        allowDecimals={false}
                        width={yAxisWidth}
                        tickMargin={2}
                        tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 8, fontWeight: 500 }}
                      />
                      <ChartTooltip cursor={false} content={props => <CountTooltip {...(props as TooltipProps<number, string>)} period={activePeriod} seriesByKey={seriesByKey} />} />
                      {series.map(item => {
                        const isStacked = !!item.stackId
                        return (
                          <Bar
                            key={item.key}
                            dataKey={item.key}
                            name={item.label}
                            fill={item.color}
                            {...(!isStacked ? { minPointSize: 1 } : {})}
                            radius={isStacked ? SQUARE_RADIUS : BAR_RADIUS}
                            stackId={item.stackId}
                            cursor={effectiveGroupByNode ? 'pointer' : undefined}
                          >
                            {isStacked && chartData.map(row => <Cell key={`${item.key}-${row._period_start}`} {...getCellRadiusProps(getStackedBarRadius(row, item.key, stackedSeries))} />)}
                          </Bar>
                        )
                      })}
                    </BarChart>
                  )
                ) : chartData.length > 0 && effectiveGroupByNode && chartView === 'pie' ? (
                  pieData.length > 0 ? (
                    <PieChart>
                      <ChartTooltip cursor={false} content={props => <CountPieTooltip {...(props as TooltipProps<number, string>)} />} />
                      <Pie data={pieData} dataKey="count" nameKey="name" innerRadius="45%" outerRadius="88%" paddingAngle={piePaddingAngle} strokeWidth={1.5}>
                        {pieData.map(point => (
                          <Cell key={point.name} fill={point.fill} />
                        ))}
                      </Pie>
                    </PieChart>
                  ) : (
                    <EmptyState
                      type="no-data"
                      title={t('statistics.noDataInRange')}
                      description={t('statistics.noDataInRangeDescription')}
                      className="max-h-[300px] min-h-[150px] sm:max-h-[400px] sm:min-h-[200px]"
                    />
                  )
                ) : (
                  <EmptyState
                    type="no-data"
                    title={t('statistics.noDataInRange')}
                    description={t('statistics.noDataInRangeDescription')}
                    className="max-h-[300px] min-h-[150px] sm:max-h-[400px] sm:min-h-[200px]"
                  />
                )}
              </ChartContainer>
              {chartData.length > 0 && (
                <div className="overflow-x-auto pt-3">
                  <div className="flex min-w-max items-center justify-center gap-4">
                    {(effectiveGroupByNode && chartView === 'pie' ? pieData : series).map(item => {
                      const key = 'key' in item ? item.key : item.name
                      const label = 'label' in item ? item.label : item.name
                      const color = 'color' in item ? item.color : item.fill
                      const percentage = 'percentage' in item ? item.percentage : undefined
                      return (
                        <div dir="ltr" key={key} className="flex items-center gap-1.5">
                          <div className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: color }} />
                          <span className="text-xs whitespace-nowrap">
                            {label}
                            {typeof percentage === 'number' ? ` (${percentage.toFixed(1)}%)` : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <UserCountStatsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        data={selectedData}
        period={activePeriod}
        metricLabel={metricLabels[effectiveMetric]}
        series={series}
        allChartData={chartData}
        currentIndex={currentDataIndex}
        onNavigate={handleModalNavigate}
      />
    </>
  )
}
