import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, TooltipProps } from 'recharts'
import { DateRange } from 'react-day-picker'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { Period, type NodeUsageStat, type UserUsageStat, useGetAdminUsage, useGetUsage } from '@/service/api'
import { formatBytes } from '@/utils/formatByte'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from './empty-state'
import { Calendar, Download, Upload } from 'lucide-react'
import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from './time-selector'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import {
  formatTooltipDate,
  pickStatsArray,
  getChartQueryRangeFromShortcut,
  getChartQueryRangeFromDateRange,
  formatPeriodLabelForPeriod,
  getXAxisIntervalForShortcut,
  TrafficShortcutKey,
} from '@/utils/chart-period-utils'

type DataPoint = {
  time: string
  usage: number
  _uplink: number
  _downlink: number
  _period_start: string
}

const chartConfig = {
  usage: {
    label: 'Traffic Usage (GB)',
    color: 'hsl(var(--primary))',
  },
} satisfies ChartConfig

interface CostumeBarChartProps {
  nodeId?: number
}

const isNodeUsageStat = (point: NodeUsageStat | UserUsageStat): point is NodeUsageStat => 'uplink' in point && 'downlink' in point

const getTrafficBytes = (point: NodeUsageStat | UserUsageStat) => {
  if ('total_traffic' in point) {
    return Number(point.total_traffic || 0)
  }
  return Number(point.uplink || 0) + Number(point.downlink || 0)
}

const getDirectionalTraffic = (point: NodeUsageStat | UserUsageStat) => {
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

function CustomBarTooltip({ active, payload, period }: TooltipProps<number, string> & { period: Period }) {
  const { t, i18n } = useTranslation()
  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as DataPoint
  const formattedDate = data._period_start ? formatTooltipDate(data._period_start, period, i18n.language) : data.time
  const isRTL = i18n.language === 'fa'
  const hasDirectionalTraffic = (data._uplink || 0) > 0 || (data._downlink || 0) > 0

  return (
    <div className={`min-w-[140px] rounded border border-border bg-background p-2 text-[11px] shadow ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
      <div className={`mb-1.5 text-[11px] font-semibold opacity-70 ${isRTL ? 'text-right' : 'text-center'}`}>
        <span dir="ltr" className="inline-block">
          {formattedDate}
        </span>
      </div>
      <div className={`mb-1.5 text-[11px] text-muted-foreground ${isRTL ? 'text-right' : 'text-center'}`}>
        <span>{t('statistics.totalUsage', { defaultValue: 'Total' })}: </span>
        <span dir="ltr" className="inline-block font-mono">
          {data.usage} GB
        </span>
      </div>
      {hasDirectionalTraffic && (
        <div className="flex flex-col gap-1">
          <div className={`flex items-center gap-1 text-[10px] text-muted-foreground ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
            <Upload className="h-3 w-3 flex-shrink-0" />
            <span dir="ltr" className="inline-block font-mono">
              {formatBytes(data._uplink)}
            </span>
            <span className="mx-1 opacity-60">|</span>
            <Download className="h-3 w-3 flex-shrink-0" />
            <span dir="ltr" className="inline-block font-mono">
              {formatBytes(data._downlink)}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

export function CostumeBarChart({ nodeId }: CostumeBarChartProps) {
  const [chartKey, setChartKey] = useState(0)
  const [selectedAdmin, setSelectedAdmin] = useState<string>('all')
  const [selectedTime, setSelectedTime] = useState<TrafficShortcutKey>('1w')
  const [showCustomRange, setShowCustomRange] = useState(false)
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [windowWidth, setWindowWidth] = useState<number>(() => (typeof window !== 'undefined' ? window.innerWidth : 1024))

  const chartContainerRef = useRef<HTMLDivElement>(null)

  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const shouldUseNodeUsage = selectedAdmin === 'all'

  const activeQueryRange = useMemo(() => {
    if (showCustomRange && customRange?.from && customRange?.to) {
      return getChartQueryRangeFromDateRange(customRange, selectedTime)
    }

    return getChartQueryRangeFromShortcut(selectedTime, new Date(), { minuteForOneHour: true })
  }, [showCustomRange, customRange, selectedTime])

  const activePeriod = activeQueryRange.period

  const nodeUsageParams = useMemo(
    () => ({
      period: activePeriod,
      start: activeQueryRange.startDate,
      end: activeQueryRange.endDate,
      ...(nodeId !== undefined ? { node_id: nodeId } : {}),
    }),
    [activePeriod, activeQueryRange.startDate, activeQueryRange.endDate, nodeId],
  )

  const adminUsageParams = useMemo(
    () => ({
      period: activePeriod,
      start: activeQueryRange.startDate,
      end: activeQueryRange.endDate,
      ...(nodeId !== undefined ? { node_id: nodeId } : {}),
    }),
    [activePeriod, activeQueryRange.startDate, activeQueryRange.endDate, nodeId],
  )

  const { data: nodeUsageData, isLoading: isLoadingNodeUsage, error: nodeUsageError } = useGetUsage(nodeUsageParams, {
    query: {
      enabled: shouldUseNodeUsage,
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const { data: adminUsageData, isLoading: isLoadingAdminUsage, error: adminUsageError } = useGetAdminUsage(selectedAdmin, adminUsageParams, {
    query: {
      enabled: !shouldUseNodeUsage && selectedAdmin !== 'all',
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const usageData = shouldUseNodeUsage ? nodeUsageData : adminUsageData
  const isLoading = shouldUseNodeUsage ? isLoadingNodeUsage : isLoadingAdminUsage
  const error = shouldUseNodeUsage ? nodeUsageError : adminUsageError

  const statsArr = useMemo(
    () => pickStatsArray<NodeUsageStat | UserUsageStat>(usageData?.stats, nodeId !== undefined ? [String(nodeId), '-1'] : ['-1']),
    [usageData?.stats, nodeId],
  )

  const chartData = useMemo<DataPoint[]>(
    () =>
      statsArr.map(point => {
        const usageBytes = getTrafficBytes(point)
        const directionalTraffic = getDirectionalTraffic(point)

        return {
          time: formatPeriodLabelForPeriod(point.period_start, activePeriod, i18n.language),
          usage: parseFloat((usageBytes / (1024 * 1024 * 1024)).toFixed(2)),
          _uplink: directionalTraffic.uplink,
          _downlink: directionalTraffic.downlink,
          _period_start: point.period_start,
        }
      }),
    [statsArr, activePeriod, i18n.language],
  )

  const totalUsage = useMemo(() => {
    const total = statsArr.reduce((sum, point) => sum + getTrafficBytes(point), 0)
    if (total <= 0) return '0'
    return String(formatBytes(total, 2))
  }, [statsArr])

  const xAxisInterval = useMemo(() => {
    if (showCustomRange && customRange?.from && customRange?.to) {
      if (activePeriod === Period.hour || activePeriod === Period.minute) {
        return Math.max(1, Math.floor(chartData.length / 8))
      }

      const daysDiff = Math.ceil(Math.abs(customRange.to.getTime() - customRange.from.getTime()) / (1000 * 60 * 60 * 24))
      if (daysDiff > 30) {
        return Math.max(1, Math.floor(chartData.length / 5))
      }

      if (daysDiff > 7) {
        return Math.max(1, Math.floor(chartData.length / 8))
      }

      return 0
    }

    if (windowWidth < 500 && selectedTime === '1w') {
      return chartData.length <= 4 ? 0 : Math.max(1, Math.floor(chartData.length / 4))
    }

    return getXAxisIntervalForShortcut(selectedTime, chartData.length, { minuteForOneHour: true })
  }, [showCustomRange, customRange, activePeriod, chartData.length, selectedTime, windowWidth])

  const refreshChartInstant = useCallback(() => {
    if (chartData.length > 0) {
      setChartKey(previous => previous + 1)
    }
  }, [chartData.length])

  const lastRerenderTime = useRef<number>(0)
  const rerenderTimeout = useRef<NodeJS.Timeout>()

  const refreshChartThrottled = useCallback(() => {
    const now = Date.now()

    if (now - lastRerenderTime.current < 100) {
      if (rerenderTimeout.current) {
        clearTimeout(rerenderTimeout.current)
      }
      rerenderTimeout.current = setTimeout(() => {
        refreshChartThrottled()
      }, 100)
      return
    }

    if (chartData.length > 0) {
      lastRerenderTime.current = now
      setChartKey(previous => previous + 1)
    }
  }, [chartData.length])

  useEffect(() => {
    let resizeTimeout: NodeJS.Timeout

    const handleResize = () => {
      setWindowWidth(window.innerWidth)
      clearTimeout(resizeTimeout)
      resizeTimeout = setTimeout(() => {
        refreshChartThrottled()
      }, 150)
    }

    window.addEventListener('resize', handleResize)

    const resizeObserver = new ResizeObserver(entries => {
      for (const entry of entries) {
        if (entry.target === chartContainerRef.current) {
          const { width, height } = entry.contentRect
          if (width > 0 && height > 0) {
            handleResize()
          }
        }
      }
    })

    if (chartContainerRef.current) {
      resizeObserver.observe(chartContainerRef.current)
    }

    const mutationObserver = new MutationObserver(mutations => {
      const hasSidebarChange = mutations.some(mutation => mutation.type === 'attributes' && (mutation.attributeName === 'class' || mutation.attributeName === 'data-state'))
      if (hasSidebarChange) {
        refreshChartInstant()
      }
    })

    mutationObserver.observe(document.body, {
      attributes: true,
      attributeFilter: ['class', 'data-sidebar-state', 'data-state'],
      childList: false,
      subtree: false,
    })

    const sidebar = document.querySelector('[data-sidebar]') || document.querySelector('aside')
    if (sidebar) {
      mutationObserver.observe(sidebar, {
        attributes: true,
        attributeFilter: ['class', 'data-state'],
      })
    }

    return () => {
      clearTimeout(resizeTimeout)
      if (rerenderTimeout.current) {
        clearTimeout(rerenderTimeout.current)
      }
      window.removeEventListener('resize', handleResize)
      resizeObserver.disconnect()
      mutationObserver.disconnect()
    }
  }, [refreshChartThrottled, refreshChartInstant])

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

  return (
    <Card>
      <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 xl:flex-row">
        <div className="flex flex-1 flex-col gap-2 border-b px-4 py-3 xl:px-6 xl:py-4">
          <div className="flex min-w-0 flex-col justify-center gap-1 pt-2">
            <CardTitle className="text-sm sm:text-base">{t('statistics.trafficUsage')}</CardTitle>
            <CardDescription className="text-xs sm:text-sm">{t('statistics.trafficUsageDescription')}</CardDescription>
          </div>
          <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
            <div className="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
              <TimeSelector selectedTime={selectedTime} setSelectedTime={handleTimeSelect} shortcuts={TRAFFIC_TIME_SELECTOR_SHORTCUTS} maxVisible={5} className="w-full" />
              <button
                type="button"
                aria-label="Custom Range"
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
            <AdminFilterCombobox value={selectedAdmin} onValueChange={setSelectedAdmin} className="w-full sm:w-[220px] sm:shrink-0" />
          </div>
          {showCustomRange && (
            <div className="flex w-full">
              <TimeRangeSelector onRangeChange={handleCustomRangeChange} initialRange={customRange} className="w-full" />
            </div>
          )}
        </div>
        <div className="m-0 flex flex-col justify-center p-4 xl:border-l xl:p-5 xl:px-6">
          <span className="text-xs text-muted-foreground">{t('statistics.usageDuringPeriod')}</span>
          <span dir="ltr" className="flex justify-center text-base text-foreground sm:text-lg">
            {isLoading ? <Skeleton className="h-5 w-20" /> : totalUsage}
          </span>
        </div>
      </CardHeader>
      <CardContent ref={chartContainerRef} dir={dir} className="px-4 pt-4 sm:px-6 sm:pt-8">
        {isLoading ? (
          <div className="flex max-h-[300px] min-h-[150px] w-full items-center justify-center sm:max-h-[400px] sm:min-h-[200px]">
            <Skeleton className="h-[250px] w-full sm:h-[300px]" />
          </div>
        ) : error ? (
          <EmptyState type="error" className="max-h-[300px] min-h-[150px] sm:max-h-[400px] sm:min-h-[200px]" />
        ) : (
          <div className="mx-auto w-full max-w-7xl">
            <ChartContainer
              key={chartKey}
              dir="ltr"
              config={chartConfig}
              className="max-h-[300px] min-h-[150px] w-full overflow-x-auto sm:max-h-[400px] sm:min-h-[200px]"
              style={{
                marginBottom: navigator.userAgent.includes('Safari') && navigator.platform.includes('Mac') ? `${0.18 * window.innerWidth}px` : '0',
              }}
            >
              {chartData.length > 0 ? (
                <BarChart accessibilityLayer data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <CartesianGrid direction="ltr" vertical={false} />
                  <XAxis
                    direction="ltr"
                    dataKey="time"
                    tickLine={false}
                    tickMargin={8}
                    axisLine={false}
                    interval={xAxisInterval}
                    tick={{
                      fill: 'hsl(var(--muted-foreground))',
                      fontSize: 8,
                      fontWeight: 500,
                    }}
                    minTickGap={5}
                  />
                  <YAxis
                    direction="ltr"
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={value => formatBytes(Number(value || 0) * 1024 * 1024 * 1024, 0, true).toString()}
                    tick={{
                      fill: 'hsl(var(--muted-foreground))',
                      fontSize: 8,
                      fontWeight: 500,
                    }}
                    width={28}
                    tickMargin={2}
                  />
                  <ChartTooltip cursor={false} content={<CustomBarTooltip period={activePeriod} />} />
                  <Bar dataKey="usage" fill="var(--color-usage)" radius={6} />
                </BarChart>
              ) : (
                <EmptyState
                  type="no-data"
                  title={t('statistics.noDataInRange')}
                  description={t('statistics.noDataInRangeDescription')}
                  className="max-h-[300px] min-h-[150px] sm:max-h-[400px] sm:min-h-[200px]"
                />
              )}
            </ChartContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
