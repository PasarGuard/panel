import { useEffect, useRef, useState, useCallback } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import { DateRange } from 'react-day-picker'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { getAdminUsage, getUsage, Period, type NodeUsageStat, type UserUsageStat } from '@/service/api'
import { formatBytes } from '@/utils/formatByte'
import { Skeleton } from '@/components/ui/skeleton'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import { EmptyState } from './empty-state'
import { TrendingUp, Upload, Download, Calendar } from 'lucide-react'
import { dateUtils } from '@/utils/dateFormatter'
import { TooltipProps } from 'recharts'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from './time-selector'
import { getPeriodFromDateRange } from '@/utils/datePickerUtils'
import { getDateRangeFromShortcut } from '@/utils/timeShortcutUtils'
import AdminFilterCombobox from '@/components/common/admin-filter-combobox'

type DataPoint = {
  time: string
  usage: number
}

const chartConfig = {
  usage: {
    label: 'Traffic Usage (GB)',
    color: 'hsl(var(--primary))',
  },
} satisfies ChartConfig

// Define props interface
interface CostumeBarChartProps {
  nodeId?: number
}

const isNodeUsageStat = (point: NodeUsageStat | UserUsageStat): point is NodeUsageStat => {
  return 'uplink' in point && 'downlink' in point
}

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

function CustomBarTooltip({ active, payload, period }: TooltipProps<any, any> & { period?: string }) {
  const { t, i18n } = useTranslation()
  if (!active || !payload || !payload.length) return null
  const data = payload[0].payload
  const d = dateUtils.toSystemTimezoneDayjs(data._period_start)
  const today = dateUtils.toSystemTimezoneDayjs(new Date())
  const isToday = d.isSame(today, 'day')

  let formattedDate
  if (i18n.language === 'fa') {
    try {
      if (period === 'day' && isToday) {
        formattedDate = new Date()
          .toLocaleString('fa-IR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          })
          .replace(',', '')
      } else if (period === 'day') {
        const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
        formattedDate = localDate
          .toLocaleString('fa-IR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          })
          .replace(',', '')
      } else {
        formattedDate = d
          .toDate()
          .toLocaleString('fa-IR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          })
          .replace(',', '')
      }
    } catch {
      formattedDate = d.format('YYYY/MM/DD HH:mm')
    }
  } else {
    if (period === 'day' && isToday) {
      const now = new Date()
      formattedDate = now
        .toLocaleString('en-US', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })
        .replace(',', '')
    } else if (period === 'day') {
      const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
      formattedDate = localDate
        .toLocaleString('en-US', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })
        .replace(',', '')
    } else {
      formattedDate = d
        .toDate()
        .toLocaleString('en-US', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })
        .replace(',', '')
    }
  }

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
        <div className={`flex flex-col gap-1`}>
          <div className={`flex items-center gap-1 text-[10px] text-muted-foreground ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
            <Upload className="h-3 w-3 flex-shrink-0" />
            <span dir="ltr" className="inline-block font-mono">
              {formatBytes(data._uplink)}
            </span>
            <span className={`opacity-60 ${isRTL ? 'mx-1' : 'mx-1'}`}>|</span>
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
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined)
  const [selectedTime, setSelectedTime] = useState<string>('1w')
  const [showCustomRange, setShowCustomRange] = useState(false)
  const [chartData, setChartData] = useState<DataPoint[] | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [totalUsage, setTotalUsage] = useState('0')
  const [chartKey, setChartKey] = useState(0)
  const [selectedAdmin, setSelectedAdmin] = useState<string>('all')

  const chartContainerRef = useRef<HTMLDivElement>(null)

  const { t } = useTranslation()
  const dir = useDirDetection()

  // Instant chart refresh for sidebar changes
  const refreshChartInstant = useCallback(() => {
    // No throttling for instant response
    if (chartData && chartData.length > 0) {
      setChartKey(prev => prev + 1)
    }
  }, [chartData])

  // Throttled chart refresh for resize events
  const lastRerenderTime = useRef<number>(0)
  const rerenderTimeout = useRef<NodeJS.Timeout>()

  const refreshChartThrottled = useCallback(() => {
    const now = Date.now()

    // Simple throttling - only prevent if called within 100ms
    if (now - lastRerenderTime.current < 100) {
      if (rerenderTimeout.current) {
        clearTimeout(rerenderTimeout.current)
      }
      rerenderTimeout.current = setTimeout(() => {
        refreshChartThrottled()
      }, 100)
      return
    }

    // Only refresh if we have data to display
    if (chartData && chartData.length > 0) {
      lastRerenderTime.current = now
      setChartKey(prev => prev + 1)
    }
  }, [chartData])

  // Simple and fast resize/sidebar detection
  useEffect(() => {
    let resizeTimeout: NodeJS.Timeout

    const handleResize = () => {
      clearTimeout(resizeTimeout)
      resizeTimeout = setTimeout(() => {
        refreshChartThrottled()
      }, 150) // Simple debounce
    }

    // Listen to window resize
    window.addEventListener('resize', handleResize)

    // Use ResizeObserver on the chart container
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

    // Observe the chart container
    if (chartContainerRef.current) {
      resizeObserver.observe(chartContainerRef.current)
    }

    // MutationObserver for sidebar state changes - immediate response
    const mutationObserver = new MutationObserver(mutations => {
      const hasSidebarChange = mutations.some(mutation => mutation.type === 'attributes' && (mutation.attributeName === 'class' || mutation.attributeName === 'data-state'))
      if (hasSidebarChange) {
        // Instant response for sidebar changes - no throttling
        refreshChartInstant()
      }
    })

    // Observe body and sidebar for state changes
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

  useEffect(() => {
    const fetchUsageData = async () => {
      if (!dateRange?.from || !dateRange?.to) {
        setChartData(null)
        setTotalUsage('0')
        return
      }

      setIsLoading(true)
      setError(null)

      try {
        const startDate = dateRange.from
        const endDate = dateRange.to
        // Determine period based on range
        const period = getPeriodFromDateRange(dateRange)
        const startTime = period === Period.day ? dateUtils.toUTCDayStartISO(startDate) : dateUtils.toSystemTimezoneISO(startDate)
        const endTime = dateUtils.toSystemTimezoneISO(dateUtils.toSystemTimezoneDayjs(endDate).endOf('day').toDate())

        // Prepare API parameters
        const params = {
          period: period,
          start: startTime,
          end: endTime,
          ...(nodeId !== undefined && { node_id: nodeId }),
        }

        const response = selectedAdmin === 'all' ? await getUsage(params) : await getAdminUsage(selectedAdmin, params)

        let statsArr: Array<NodeUsageStat | UserUsageStat> = []
        if (response && response.stats) {
          if (typeof response.stats === 'object' && !Array.isArray(response.stats)) {
            // If nodeId is provided, use that key
            const key = nodeId !== undefined ? String(nodeId) : '-1'
            if (response.stats[key] && Array.isArray(response.stats[key])) {
              statsArr = response.stats[key]
            } else {
              // fallback: use first available key
              const firstKey = Object.keys(response.stats)[0]
              if (firstKey && Array.isArray(response.stats[firstKey])) {
                statsArr = response.stats[firstKey]
              }
            }
          } else if (Array.isArray(response.stats)) {
            // fallback: old format
            statsArr = response.stats
          }
        }

        if (statsArr.length > 0) {
          const formattedData = statsArr.map(point => {
            const d = dateUtils.toSystemTimezoneDayjs(point.period_start)
            let timeFormat
            if (period === Period.hour) {
              timeFormat = d.format('HH:mm')
            } else {
              timeFormat = d.format('MM/DD')
            }
            const usageBytes = getTrafficBytes(point)
            const directionalTraffic = getDirectionalTraffic(point)
            const usageInGB = usageBytes / (1024 * 1024 * 1024)
            return {
              time: timeFormat,
              usage: parseFloat(usageInGB.toFixed(2)),
              _uplink: directionalTraffic.uplink,
              _downlink: directionalTraffic.downlink,
              _period_start: point.period_start,
            }
          })

          setChartData(formattedData)

          const total = statsArr.reduce((sum: number, point) => sum + getTrafficBytes(point), 0)
          const formattedTotal = formatBytes(total, 2)
          if (typeof formattedTotal === 'string') {
            setTotalUsage(formattedTotal)
          }
        } else {
          setChartData(null)
          setTotalUsage('0')
        }
      } catch (err) {
        setError(err as Error)
        setChartData(null)
        setTotalUsage('0')
        console.error('Error fetching usage data:', err)
      } finally {
        setIsLoading(false)
      }
    }

    fetchUsageData()
  }, [dateRange, nodeId, selectedAdmin])

  // Add effect to update dateRange when selectedTime changes
  useEffect(() => {
    if (!showCustomRange) {
      const nextRange = getDateRangeFromShortcut(selectedTime)
      if (nextRange) {
        setDateRange(nextRange)
      }
    }
  }, [selectedTime, showCustomRange])

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
                {showCustomRange ? (
                  <TimeRangeSelector
                    onRangeChange={range => {
                      setDateRange(range)
                      setShowCustomRange(true)
                    }}
                    initialRange={dateRange}
                    className="w-full"
                  />
                ) : (
                  <TimeSelector
                    selectedTime={selectedTime}
                    setSelectedTime={v => {
                      setSelectedTime(v)
                      setShowCustomRange(false)
                    }}
                    shortcuts={TRAFFIC_TIME_SELECTOR_SHORTCUTS}
                    maxVisible={5}
                    className="w-fit max-w-full"
                  />
                )}
                <button type="button" aria-label="Custom Range" className={`shrink-0 rounded border p-1 ${showCustomRange ? 'bg-muted' : ''}`} onClick={() => setShowCustomRange(v => !v)}>
                  <Calendar className="h-4 w-4" />
                </button>
              </div>
            <AdminFilterCombobox value={selectedAdmin} onValueChange={setSelectedAdmin} className="w-full sm:w-[220px] sm:shrink-0" />
          </div>
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
        ) : !dateRange ? (
          <EmptyState
            type="no-data"
            title={t('statistics.selectTimeRange')}
            description={t('statistics.selectTimeRangeDescription')}
            icon={<TrendingUp className="h-8 w-8 text-muted-foreground/50 sm:h-12 sm:w-12" />}
            className="max-h-[300px] min-h-[150px] sm:max-h-[400px] sm:min-h-[200px]"
          />
        ) : (
          <div className="mx-auto w-full max-w-7xl">
            <ChartContainer
              key={chartKey}
              dir={'ltr'}
              config={chartConfig}
              className="max-h-[300px] min-h-[150px] w-full overflow-x-auto sm:max-h-[400px] sm:min-h-[200px]"
              style={{
                marginBottom: navigator.userAgent.includes('Safari') && navigator.platform.includes('Mac') ? `${0.18 * window.innerWidth}px` : '0',
              }}
            >
              {chartData && chartData.length > 0 ? (
                <BarChart accessibilityLayer data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <CartesianGrid direction={'ltr'} vertical={false} />
                  <XAxis
                    direction={'ltr'}
                    dataKey="time"
                    tickLine={false}
                    tickMargin={8}
                    axisLine={false}
                    tick={{
                      fill: 'hsl(var(--muted-foreground))',
                      fontSize: 8,
                      fontWeight: 500,
                    }}
                    minTickGap={5}
                  />
                  <YAxis
                    direction={'ltr'}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={value => `${value.toFixed(2)} GB`}
                    tick={{
                      fill: 'hsl(var(--muted-foreground))',
                      fontSize: 8,
                      fontWeight: 500,
                    }}
                    width={28}
                    tickMargin={2}
                  />
                  <ChartTooltip cursor={false} content={<CustomBarTooltip period={getPeriodFromDateRange(dateRange)} />} />
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
