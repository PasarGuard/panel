import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ComponentProps } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis, type TooltipProps } from 'recharts'
import { DateRange } from 'react-day-picker'
import { AlertTriangle, BarChart3, Calendar, PieChart as PieChartIcon, TrendingUp, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useTheme } from 'next-themes'

import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import UserSubUpdateStatsModal from '@/features/users/dialogs/user-sub-update-stats-modal'
import useDirDetection from '@/hooks/use-dir-detection'
import { useChartViewType } from '@/hooks/use-chart-view-type'
import {
  Period,
  type GetUsersSubUpdateChartParams,
  type UserSubscriptionUpdateChartSegment,
  useGetUsersSubUpdateChart,
} from '@/service/api'
import {
  CHART_PERIOD_OVERRIDE_AUTO,
  type ChartPeriodOverride,
  formatPeriodLabelForPeriod,
  formatTooltipDate,
  getChartQueryRangeFromDateRange,
  getChartQueryRangeFromShortcut,
  getChartXAxisInterval,
  resolvePeriodOverride,
  TrafficShortcutKey,
} from '@/utils/chart-period-utils'
import { getChartBrushWindow, getChartRenderFlags } from '@/utils/chart-performance'
import { numberWithCommas } from '@/utils/formatByte'

import ChartBrush from './chart-brush'
import DenseChartAreaHint from './dense-chart-area-hint'
import { EmptyState } from './empty-state'
import PeriodSelector from './period-selector'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from './time-selector'

interface UserSubUpdatePieChartProps {
  username?: string
  adminId?: number
}

type SegmentWithColor = UserSubscriptionUpdateChartSegment & {
  key: string
  color: string
  count: number
  percentage: number
}

type ChartDataPoint = {
  time: string
  _period_start: string
  [key: string]: string | number
}

type AgentSeries = {
  key: string
  label: string
  color: string
}

type BarRadius = [number, number, number, number]
type CellRadiusProps = Partial<ComponentProps<typeof Cell>>

const BAR_RADIUS = 4
const SQUARE_RADIUS: BarRadius = [0, 0, 0, 0]
const getCellRadiusProps = (radius: BarRadius) => ({ radius }) as unknown as CellRadiusProps

const buildSegmentKey = (name: string, index: number) => {
  const sanitized = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

  return sanitized || `segment-${index}`
}

const generateDistinctColor = (index: number, isDark: boolean): string => {
  const distinctHues = [0, 30, 60, 120, 180, 210, 240, 270, 300, 330, 15, 45, 75, 150, 200, 225, 255, 285, 315, 345]
  const hue = distinctHues[index % distinctHues.length]
  const saturationVariations = [65, 75, 85, 70, 80, 60, 90, 55, 95, 50]
  const lightnessVariations = isDark ? [45, 55, 35, 50, 40, 60, 30, 65, 25, 70] : [40, 50, 30, 45, 35, 55, 25, 60, 20, 65]
  const saturation = saturationVariations[index % saturationVariations.length]
  const lightness = lightnessVariations[index % lightnessVariations.length]
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

const getSegmentColor = (index: number, isDark: boolean) => {
  if (index === 0) return 'hsl(var(--primary))'
  if (index < 5) return `hsl(var(--chart-${index + 1}))`
  return generateDistinctColor(index, isDark)
}

const formatPercentage = (value: number) => {
  if (value > 0 && value < 0.1) return '<0.1%'
  return `${value.toFixed(1)}%`
}

const getStackedBarRadius = (row: ChartDataPoint, seriesKey: string, stackSeries: AgentSeries[]): BarRadius => {
  const visibleSeries = stackSeries.filter(item => Number(row[item.key] || 0) > 0)
  const visibleIndex = visibleSeries.findIndex(item => item.key === seriesKey)

  if (visibleIndex < 0) return SQUARE_RADIUS
  if (visibleSeries.length === 1) return [BAR_RADIUS, BAR_RADIUS, BAR_RADIUS, BAR_RADIUS]

  const isBottomSegment = visibleIndex === 0
  const isTopSegment = visibleIndex === visibleSeries.length - 1

  return [isTopSegment ? BAR_RADIUS : 0, isTopSegment ? BAR_RADIUS : 0, isBottomSegment ? BAR_RADIUS : 0, isBottomSegment ? BAR_RADIUS : 0]
}

function PieTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{
    payload: {
      agent: string
      updates: number
      percentage: number
      fill: string
    }
  }>
}) {
  const { t } = useTranslation()

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload
  const { agent, updates, percentage, fill } = data

  return (
    <div className="bg-background/95 rounded-lg border p-3 shadow-lg backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <div className="border-border/20 h-3 w-3 rounded-full border" style={{ backgroundColor: fill }} />
        <span className="text-foreground text-sm font-medium">{agent}</span>
      </div>
      <div className="mt-2 space-y-1">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5">
            <Users className="text-muted-foreground h-3 w-3" />
            <span className="text-muted-foreground text-xs">{t('statistics.subscriptions')}</span>
          </div>
          <span className="text-foreground font-mono text-sm font-semibold">{numberWithCommas(updates)}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-muted-foreground text-xs">{t('statistics.percentage')}</span>
          <Badge variant="secondary" className="text-xs font-medium">
            {formatPercentage(percentage)}
          </Badge>
        </div>
      </div>
    </div>
  )
}

function SeriesTooltip({
  active,
  payload,
  period,
  seriesByKey,
}: TooltipProps<number, string> & {
  period: Period
  seriesByKey: Record<string, AgentSeries>
}) {
  const { t, i18n } = useTranslation()

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as ChartDataPoint
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
        <span>{t('statistics.totalSubscriptions')}:</span>
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
        {rows.length > 0 && <div className="text-muted-foreground pt-1 text-center text-[10px]">{t('statistics.clickForMore', { defaultValue: 'Click for more details' })}</div>}
      </div>
    </div>
  )
}

function UserSubUpdatePieChart({ username, adminId }: UserSubUpdatePieChartProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()
  const chartViewType = useChartViewType()

  const [chartView, setChartView] = useState<'bar' | 'pie'>('pie')
  const [selectedAdmin, setSelectedAdmin] = useState<string>('all')
  const [selectedAdminId, setSelectedAdminId] = useState<number | null>(() => (adminId != null ? adminId : null))
  const [selectedTime, setSelectedTime] = useState<TrafficShortcutKey>('1m')
  const [periodOverride, setPeriodOverride] = useState<ChartPeriodOverride>(CHART_PERIOD_OVERRIDE_AUTO)
  const [showCustomRange, setShowCustomRange] = useState(false)
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [windowWidth, setWindowWidth] = useState<number>(() => (typeof window !== 'undefined' ? window.innerWidth : 1024))
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedData, setSelectedData] = useState<ChartDataPoint | null>(null)
  const [currentDataIndex, setCurrentDataIndex] = useState(0)

  useEffect(() => {
    if (adminId != null) {
      setSelectedAdminId(adminId)
    }
  }, [adminId])

  const activeQueryRange = useMemo(() => {
    const resolvedOverride = resolvePeriodOverride(periodOverride)
    const periodOptions = { minuteForOneHour: true, periodOverride: resolvedOverride }

    if (showCustomRange && customRange?.from && customRange?.to) {
      return getChartQueryRangeFromDateRange(customRange, selectedTime, periodOptions)
    }

    const range = getChartQueryRangeFromShortcut(selectedTime, new Date(), periodOptions)
    if (!resolvedOverride && selectedTime === 'all') {
      return { ...range, period: Period.month }
    }
    return range
  }, [showCustomRange, customRange, selectedTime, periodOverride])

  const activePeriod = activeQueryRange.period

  const params = useMemo(() => {
    const payload: GetUsersSubUpdateChartParams = {
      period: activePeriod,
      start: activeQueryRange.startDate,
      end: activeQueryRange.endDate,
    }

    if (username) {
      payload.username = username
    }

    if (selectedAdminId != null) {
      payload.admin_id = selectedAdminId
    }

    return payload
  }, [username, selectedAdminId, activePeriod, activeQueryRange.startDate, activeQueryRange.endDate])

  const { data, isLoading, error } = useGetUsersSubUpdateChart(params, {
    query: {
      refetchInterval: 60_000,
    },
  })

  const segments = useMemo<SegmentWithColor[]>(() => {
    if (!data?.segments?.length) return []

    const isDark = resolvedTheme === 'dark'
    return data.segments.map((segment, index) => {
      const safePercentage = typeof segment.percentage === 'number' && !Number.isNaN(segment.percentage) ? segment.percentage : 0
      const safeCount = typeof segment.count === 'number' && !Number.isNaN(segment.count) ? segment.count : 0
      const key = buildSegmentKey(segment.name, index)

      return {
        ...segment,
        key,
        percentage: safePercentage,
        count: safeCount,
        color: getSegmentColor(index, isDark),
      }
    })
  }, [data?.segments, resolvedTheme])

  const series = useMemo<AgentSeries[]>(() => {
    if (segments.length > 0) {
      return segments.map(segment => ({
        key: segment.key,
        label: segment.name,
        color: segment.color,
      }))
    }

    // Fall back to agents present in the time-series when segments are missing.
    if (!data?.stats?.length) return []

    const isDark = resolvedTheme === 'dark'
    const seen = new Map<string, AgentSeries>()
    data.stats.forEach(stat => {
      const name = stat.agent || 'Unknown'
      const key = buildSegmentKey(name, seen.size)
      if (!seen.has(key)) {
        seen.set(key, {
          key,
          label: name,
          color: getSegmentColor(seen.size, isDark),
        })
      }
    })
    return Array.from(seen.values())
  }, [data?.stats, resolvedTheme, segments])

  const seriesByKey = useMemo(
    () =>
      series.reduce<Record<string, AgentSeries>>((acc, item) => {
        acc[item.key] = item
        return acc
      }, {}),
    [series],
  )

  const chartConfig = useMemo<ChartConfig>(() => {
    const dynamicConfig = series.reduce<ChartConfig>((config, item) => {
      config[item.key] = {
        label: item.label,
        color: item.color,
      }
      return config
    }, {})

    return {
      updates: {
        label: t('statistics.totalSubscriptions'),
      },
      ...dynamicConfig,
    }
  }, [series, t])

  const pieChartData = useMemo(
    () =>
      segments.map(segment => ({
        segmentKey: segment.key,
        agent: segment.name,
        updates: segment.count,
        percentage: segment.percentage,
        fill: segment.color,
      })),
    [segments],
  )

  const labelRangeHint = useMemo(
    () => ({
      shortcut: showCustomRange ? undefined : selectedTime,
      customRange: showCustomRange ? customRange : undefined,
    }),
    [customRange, selectedTime, showCustomRange],
  )

  const timeSeriesData = useMemo<ChartDataPoint[]>(() => {
    if (!data?.stats?.length || series.length === 0) return []

    const keyByAgent = new Map(series.map(item => [item.label.toLowerCase(), item.key]))
    const periods = new Map<string, ChartDataPoint>()

    data.stats.forEach(stat => {
      const periodStart = String(stat.period_start)
      const agentName = (stat.agent || 'Unknown').toLowerCase()
      const seriesKey = keyByAgent.get(agentName)
      if (!seriesKey) return

      let row = periods.get(periodStart)
      if (!row) {
        row = {
          time: formatPeriodLabelForPeriod(periodStart, activePeriod, i18n.language, labelRangeHint),
          _period_start: periodStart,
        }
        series.forEach(item => {
          row![item.key] = 0
        })
        periods.set(periodStart, row)
      }

      row[seriesKey] = Number(row[seriesKey] || 0) + Number(stat.count || 0)
    })

    return Array.from(periods.values()).sort((a, b) => String(a._period_start).localeCompare(String(b._period_start)))
  }, [activePeriod, data?.stats, i18n.language, labelRangeHint, series])

  const piePaddingAngle = useMemo(() => {
    if (pieChartData.length <= 1) return 0

    const validSlices = pieChartData.filter(segment => segment.updates > 0)
    if (validSlices.length <= 1) return 0

    const totalUpdates = validSlices.reduce((sum, segment) => sum + segment.updates, 0)
    if (totalUpdates <= 0) return 0

    const smallestSliceAngle = Math.min(...validSlices.map(segment => (segment.updates / totalUpdates) * 360))
    const bySegmentDensity = 36 / validSlices.length
    const bySmallestSlice = smallestSliceAngle * 0.7

    return Math.max(0, Math.min(3, bySegmentDensity, bySmallestSlice))
  }, [pieChartData])

  const pieStrokeWidth = pieChartData.length > 16 ? 1 : 2

  const xAxisInterval = useMemo(
    () =>
      getChartXAxisInterval({
        dataLength: timeSeriesData.length,
        period: activePeriod,
        shortcut: selectedTime,
        windowWidth,
        customRange: showCustomRange ? customRange : undefined,
        periodOverride: resolvePeriodOverride(periodOverride),
      }),
    [activePeriod, customRange, selectedTime, showCustomRange, timeSeriesData.length, windowWidth, periodOverride],
  )

  const { isAnimationActive, usePerBarRadius, useAccessibilityLayer, areaCurveType } = useMemo(
    () => getChartRenderFlags(timeSeriesData.length, series.length),
    [timeSeriesData.length, series.length],
  )
  const brushWindow = useMemo(() => getChartBrushWindow(timeSeriesData.length, series.length), [series.length, timeSeriesData.length])

  const hasPieData = segments.some(segment => segment.count > 0)
  const hasBarData = timeSeriesData.length > 0
  const total = data?.total ?? 0
  const periodTotal = useMemo(() => {
    // Match other charts: only show a period total when the active view has data.
    if (chartView === 'bar') {
      if (!hasBarData) return null
      return timeSeriesData.reduce((sum, row) => sum + series.reduce((rowSum, item) => rowSum + Number(row[item.key] || 0), 0), 0)
    }

    return hasPieData ? total : null
  }, [chartView, hasBarData, hasPieData, series, timeSeriesData, total])
  const leadingSegment = useMemo(() => [...segments].sort((a, b) => b.count - a.count)[0], [segments])

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

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
      if (!timeSeriesData[index]) return
      setCurrentDataIndex(index)
      setSelectedData(timeSeriesData[index])
    },
    [timeSeriesData],
  )

  const handleChartPointClick = useCallback(
    (data: unknown) => {
      const chartClick = data as { activeTooltipIndex?: unknown; activePayload?: Array<{ payload?: unknown }> } | null
      const clickedIndex = typeof chartClick?.activeTooltipIndex === 'number' ? chartClick.activeTooltipIndex : -1
      const clickedData = (chartClick?.activePayload?.[0]?.payload ?? (clickedIndex >= 0 ? timeSeriesData[clickedIndex] : undefined)) as ChartDataPoint | undefined
      if (!clickedData) return

      const activeSeriesCount = series.filter(item => Number(clickedData[item.key] || 0) > 0).length
      if (activeSeriesCount <= 0) return

      const resolvedIndex = clickedIndex >= 0 ? clickedIndex : timeSeriesData.findIndex(item => item._period_start === clickedData._period_start)
      setCurrentDataIndex(resolvedIndex >= 0 ? resolvedIndex : 0)
      setSelectedData(clickedData)
      setModalOpen(true)
    },
    [series, timeSeriesData],
  )

  return (
    <>
      <Card>
      <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 xl:flex-row">
        <div className="flex flex-1 flex-col gap-2 border-b px-4 py-3 xl:px-6 xl:py-4">
          <div className="flex min-w-0 flex-col justify-center gap-1 pt-2">
            <CardTitle className="mb-0.5 flex min-w-0 items-center gap-2">
              <Users className="text-muted-foreground h-4 w-4 shrink-0" />
              <span className="truncate">{t('statistics.subscriptionDistribution')}</span>
            </CardTitle>
            <CardDescription className="text-pretty">{t('statistics.subscriptionDistributionDescription')}</CardDescription>
            <p className="text-muted-foreground flex items-start gap-1.5 text-xs">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                {t('statistics.subscriptionDistributionRetentionNote', {
                  limit: 10,
                  env: 'USER_SUBSCRIPTION_CLIENTS_LIMIT',
                  defaultValue:
                    'By default only the latest {{limit}} subscription updates are kept per user. Change this with {{env}} in your environment.',
                })}
              </span>
            </p>
          </div>
          <div className="flex w-full min-w-0 flex-col gap-2">
            <div className="flex w-full min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
              <TimeSelector selectedTime={selectedTime} setSelectedTime={handleTimeSelect} shortcuts={TRAFFIC_TIME_SELECTOR_SHORTCUTS} maxVisible={5} className="w-full sm:w-fit" />
              <div className="flex w-full items-center gap-2 sm:w-auto">
                <PeriodSelector value={periodOverride} onValueChange={setPeriodOverride} className="min-w-0 flex-1 sm:w-[7rem] sm:flex-none" />
                <button
                  type="button"
                  aria-label={t('statistics.customRange', { defaultValue: 'Custom Range' })}
                  className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${showCustomRange ? 'bg-muted' : ''}`}
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
            </div>
            <div className="flex w-full items-center gap-2">
              <AdminFilterCombobox
                value={selectedAdmin}
                onValueChange={adminUsername => {
                  setSelectedAdmin(adminUsername)
                  if (adminUsername === 'all') {
                    setSelectedAdminId(null)
                  }
                }}
                onAdminSelect={admin => setSelectedAdminId(admin?.id ?? null)}
                className="min-w-0 flex-1 sm:w-[220px] sm:flex-none"
              />
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
            </div>
          </div>
          {showCustomRange && (
            <div className="flex w-full">
              <TimeRangeSelector onRangeChange={handleCustomRangeChange} initialRange={customRange} className="w-full" />
            </div>
          )}
        </div>
        <div className="m-0 flex w-full flex-col justify-center gap-2 p-4 xl:w-auto xl:min-w-[180px] xl:border-l xl:p-5 xl:px-6">
          <span className="text-muted-foreground text-sm">{t('statistics.subscriptionsDuringPeriod', { defaultValue: 'Updates During Period' })}</span>
          {isLoading ? (
            <div className="flex justify-center">
              <Skeleton className="h-5 w-24" />
            </div>
          ) : (
            <span dir="ltr" className="text-foreground flex items-center justify-center gap-2 text-lg">
              <Users className="text-muted-foreground h-4 w-4" />
              {periodTotal != null ? numberWithCommas(periodTotal) : <span className="text-muted-foreground">—</span>}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-4 sm:pt-8">
        {isLoading ? (
          chartView === 'pie' ? (
            <LoadingState />
          ) : (
            <div className="flex max-h-[400px] min-h-[200px] w-full items-center justify-center">
              <Skeleton className="h-[300px] w-full" />
            </div>
          )
        ) : error ? (
          <EmptyState type="error" className="max-h-[400px] min-h-[200px]" />
        ) : chartView === 'pie' && !hasPieData ? (
          <EmptyState type="no-data" title={t('statistics.noDataInRange')} description={t('statistics.noDataInRangeDescription')} className="max-h-[400px] min-h-[200px]" />
        ) : chartView === 'bar' && !hasBarData ? (
          <EmptyState type="no-data" title={t('statistics.noDataInRange')} description={t('statistics.noDataInRangeDescription')} className="max-h-[400px] min-h-[200px]" />
        ) : chartView === 'pie' ? (
          <div className="flex flex-col items-center gap-6 lg:flex-row">
            <div className="w-full lg:w-1/2">
              <ChartContainer
                config={chartConfig}
                className="mx-auto h-[220px] max-h-[320px] w-[220px] max-w-[320px] sm:h-[280px] sm:w-[280px] lg:h-[320px] lg:w-[320px] [&_.recharts-text]:fill-transparent"
              >
                <PieChart>
                  <ChartTooltip content={<PieTooltip />} />
                  <Pie data={pieChartData} dataKey="updates" nameKey="agent" innerRadius="55%" outerRadius="95%" paddingAngle={piePaddingAngle} strokeWidth={pieStrokeWidth} isAnimationActive>
                    {pieChartData.map(segment => (
                      <Cell key={segment.segmentKey} fill={segment.fill} />
                    ))}
                  </Pie>
                </PieChart>
              </ChartContainer>
            </div>
            <div className={`flex w-full flex-1 flex-col gap-4 lg:w-1/2 ${dir === 'rtl' ? 'items-end' : 'items-start'}`}>
              <div className="border-border/60 bg-muted/30 w-full max-w-xs rounded-lg border p-4">
                <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{t('statistics.totalSubscriptions')}</p>
                <p dir="ltr" className="text-foreground mt-2 text-3xl font-semibold">
                  {numberWithCommas(total)}
                </p>
              </div>
              <div className="max-h-64 w-full overflow-y-auto">
                <ul className="w-full space-y-3">
                  {segments.map(segment => (
                    <li key={segment.key} className={`border-border/40 flex max-w-full items-center justify-between gap-4 rounded-md border px-3 py-2 ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                      <div className={`flex items-center gap-2 overflow-hidden ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                        <span className="h-3 w-3 rounded-full" style={{ backgroundColor: segment.color }} />
                        <span className="text-foreground flex-1 truncate text-sm font-medium">{segment.name}</span>
                      </div>
                      <div className={`text-foreground flex items-baseline gap-3 text-sm font-semibold ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
                        <span dir="ltr" className="font-mono">
                          {numberWithCommas(segment.count)}
                        </span>
                        <span className="text-muted-foreground text-xs font-normal">{formatPercentage(segment.percentage)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto w-full">
            <DenseChartAreaHint pointCount={timeSeriesData.length} />
            <ChartContainer dir="ltr" config={chartConfig} className="h-[200px] w-full sm:h-[320px] lg:h-[400px]">
              {chartViewType === 'area' ? (
                <AreaChart {...(useAccessibilityLayer ? { accessibilityLayer: true } : {})} data={timeSeriesData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }} onClick={handleChartPointClick}>
                  <defs>
                    {series.map(item => (
                      <linearGradient key={item.key} id={`sub-update-area-gradient-${item.key}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={item.color} stopOpacity={0.45} />
                        <stop offset="100%" stopColor={item.color} stopOpacity={0.05} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid direction="ltr" vertical={false} />
                  <XAxis direction="ltr" dataKey="time" tickLine={false} tickMargin={10} axisLine={false} minTickGap={28} interval={xAxisInterval} />
                  <YAxis
                    direction="ltr"
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                    domain={[0, 'auto']}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 9, fontWeight: 500 }}
                    width={32}
                    tickMargin={2}
                  />
                  <ChartTooltip cursor={false} content={props => <SeriesTooltip {...(props as TooltipProps<number, string>)} period={activePeriod} seriesByKey={seriesByKey} />} />
                  {series.map(item => (
                    <Area
                      key={item.key}
                      type={areaCurveType}
                      dataKey={item.key}
                      stackId="a"
                      fill={`url(#sub-update-area-gradient-${item.key})`}
                      stroke={item.color}
                      strokeWidth={1.5}
                      dot={false}
                      activeDot={false}
                      isAnimationActive={isAnimationActive}
                      cursor="pointer"
                    />
                  ))}
                  {brushWindow && <ChartBrush startIndex={brushWindow.startIndex} endIndex={brushWindow.endIndex} />}
                </AreaChart>
              ) : (
                <BarChart {...(useAccessibilityLayer ? { accessibilityLayer: true } : {})} data={timeSeriesData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }} onClick={handleChartPointClick}>
                  <CartesianGrid direction="ltr" vertical={false} />
                  <XAxis direction="ltr" dataKey="time" tickLine={false} tickMargin={10} axisLine={false} minTickGap={28} interval={xAxisInterval} />
                  <YAxis
                    direction="ltr"
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 9, fontWeight: 500 }}
                    width={32}
                    tickMargin={2}
                  />
                  <ChartTooltip cursor={false} content={props => <SeriesTooltip {...(props as TooltipProps<number, string>)} period={activePeriod} seriesByKey={seriesByKey} />} />
                  {series.map(item => (
                    <Bar key={item.key} dataKey={item.key} stackId="a" fill={item.color} radius={SQUARE_RADIUS} cursor="pointer" isAnimationActive={isAnimationActive}>
                      {usePerBarRadius &&
                        timeSeriesData.map(row => (
                          <Cell key={`${item.key}-${row._period_start}`} {...getCellRadiusProps(getStackedBarRadius(row, item.key, series))} />
                        ))}
                    </Bar>
                  ))}
                  {brushWindow && <ChartBrush startIndex={brushWindow.startIndex} endIndex={brushWindow.endIndex} />}
                </BarChart>
              )}
            </ChartContainer>
            <div className="overflow-x-auto pt-3">
              <div className="flex min-w-max items-center justify-center gap-4">
                {series.map(item => (
                  <div dir="ltr" key={item.key} className="flex items-center gap-1.5">
                    <div className="h-2 w-2 shrink-0 rounded-[2px]" style={{ backgroundColor: item.color }} />
                    <span className="text-xs whitespace-nowrap">{item.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
      {chartView === 'pie' && leadingSegment && hasPieData && (
        <CardFooter className="flex-col gap-1.5 pt-4">
          <div className="border-primary/20 from-primary/10 via-primary/5 flex items-center gap-2 rounded-lg border bg-gradient-to-r to-transparent px-3 py-2 text-xs">
            <div className="text-primary flex items-center gap-1.5 font-semibold">
              <TrendingUp className="h-3.5 w-3.5" />
              <span>
                {t('statistics.leadingClientMessage', {
                  client: leadingSegment.name,
                  percentage: leadingSegment.percentage > 0 && leadingSegment.percentage < 0.1 ? '<0.1' : leadingSegment.percentage.toFixed(1),
                })}
              </span>
            </div>
            <div className="border-primary/30 ml-auto h-2.5 w-2.5 rounded-full border-2 shadow-sm" style={{ backgroundColor: leadingSegment.color }} />
          </div>
        </CardFooter>
      )}
    </Card>

    <UserSubUpdateStatsModal
      open={modalOpen}
      onClose={() => setModalOpen(false)}
      data={selectedData}
      period={activePeriod}
      series={series}
      allChartData={timeSeriesData}
      currentIndex={currentDataIndex}
      onNavigate={handleModalNavigate}
    />
    </>
  )
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center gap-6 lg:flex-row">
      <div className="flex w-full items-center justify-center lg:w-1/2">
        <Skeleton className="h-[220px] w-[220px] rounded-full sm:h-[260px] sm:w-[260px]" />
      </div>
      <div className="flex w-full flex-1 flex-col gap-4">
        <Skeleton className="h-16 w-full max-w-xs rounded-lg" />
        <Skeleton className="h-10 w-full max-w-xs rounded-lg" />
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <Skeleton className="h-3 w-3 rounded-full" />
                <Skeleton className="h-4 w-24" />
              </div>
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default UserSubUpdatePieChart
