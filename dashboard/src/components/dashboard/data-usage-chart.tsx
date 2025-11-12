import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Cell, TooltipProps } from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '../ui/card'
import { ChartConfig, ChartContainer, ChartTooltip } from '../ui/chart'
import { formatBytes } from '@/utils/formatByte'
import { useTranslation } from 'react-i18next'
import { useGetUsersUsage, useGetUsage, Period, UserUsageStatsList, NodeUsageStatsList, UserUsageStat, NodeUsageStat } from '@/service/api'
import { useMemo, useState, useEffect } from 'react'
import { SearchXIcon, TrendingUp, TrendingDown } from 'lucide-react'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select'
import { dateUtils } from '@/utils/dateFormatter'
import dayjs from '@/lib/dayjs'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'

type PeriodOption = {
  label: string
  value: string
  period: Period
  hours?: number
  days?: number
  months?: number
  allTime?: boolean
}

const PERIOD_KEYS = [
  { key: '12h', period: 'hour' as Period, amount: 12, unit: 'hour' },
  { key: '24h', period: 'hour' as Period, amount: 24, unit: 'hour' },
  { key: '3d', period: 'day' as Period, amount: 3, unit: 'day' },
  { key: '7d', period: 'day' as Period, amount: 7, unit: 'day' },
  { key: '30d', period: 'day' as Period, amount: 30, unit: 'day' },
  { key: '3m', period: 'day' as Period, amount: 3, unit: 'month' },
  { key: 'all', period: 'day' as Period, allTime: true },
]

const transformUsageData = (apiData: { stats: (UserUsageStat | NodeUsageStat)[] }, periodOption: PeriodOption, isNodeUsage: boolean = false, locale: string = 'en') => {
  if (!apiData?.stats || !Array.isArray(apiData.stats)) {
    return []
  }
  const today = dateUtils.toDayjs(new Date())

  return apiData.stats.map((stat: UserUsageStat | NodeUsageStat) => {
    const d = dateUtils.toDayjs(stat.period_start)
    const isToday = d.isSame(today, 'day')
    console.log(d.format('HH:mm'), stat.period_start);


    let displayLabel = ''
    if (periodOption.hours) {
      // For hour periods, use period_start with format date function
      displayLabel = d.format('HH:mm')
    } else if (periodOption.period === 'day') {
      // For day periods, use same logic as CustomBarTooltip but with shorter format
      if (locale === 'fa') {
        if (isToday) {
          // For today, show current time
          displayLabel = new Date()
            .toLocaleString('fa-IR', {
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            })
        } else {
          // For other days, show date
          const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
          displayLabel = localDate
            .toLocaleString('fa-IR', {
              month: '2-digit',
              day: '2-digit',
            })
        }
      } else {
        if (isToday) {
          // For today, show current time
          displayLabel = new Date()
            .toLocaleString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            })
        } else {
          // For other days, show date
          const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
          displayLabel = localDate
            .toLocaleString('en-US', {
              month: '2-digit',
              day: '2-digit',
            })
        }
      }
    } else {
      // For other periods (month, etc.), show date format
      if (locale === 'fa') {
        displayLabel = d
          .toDate()
          .toLocaleString('fa-IR', {
            month: '2-digit',
            day: '2-digit',
          })
      } else {
        displayLabel = d
          .toDate()
          .toLocaleString('en-US', {
            month: '2-digit',
            day: '2-digit',
          })
      }
    }

    const traffic = isNodeUsage
      ? ((stat as NodeUsageStat).uplink || 0) + ((stat as NodeUsageStat).downlink || 0)
      : ((stat as UserUsageStat).total_traffic || 0)
    console.log(displayLabel, d);

    return {
      date: displayLabel,
      traffic,
      period_start: stat.period_start, // Keep original for tooltip
    }
  })
}

const chartConfig = {
  traffic: {
    label: 'traffic',
    color: 'hsl(var(--foreground))',
  },
} satisfies ChartConfig

function CustomBarTooltip({ active, payload, period }: TooltipProps<number, string> & { period?: Period }) {
  const { t, i18n } = useTranslation()
  if (!active || !payload || !payload.length) return null
  const data = payload[0].payload
  // Use period_start if available (from transformUsageData), otherwise parse the display label
  const d = data.period_start ? dateUtils.toDayjs(data.period_start) : dateUtils.toDayjs(data.date)
  const today = dateUtils.toDayjs(new Date())
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

  return (
    <div className={`min-w-[160px] rounded border border-border bg-gradient-to-br from-background to-muted/80 p-2 text-xs shadow ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
      <div className={`mb-1 text-xs font-semibold text-primary ${isRTL ? 'text-right' : 'text-center'}`}>
        {t('statistics.date', { defaultValue: 'Date' })}:{' '}
        <span dir="ltr" className="inline-block">
          {formattedDate}
        </span>
      </div>
      <div className="flex flex-col gap-0.5 text-xs">
        <div>
          <span className="font-medium text-foreground">{t('statistics.totalUsage', { defaultValue: 'Total Usage' })}:</span>
          <span dir="ltr" className={isRTL ? 'mr-1' : 'ml-1'}>{formatBytes(data.traffic)}</span>
        </div>
      </div>
    </div>
  )
}

const DataUsageChart = ({ admin_username }: { admin_username?: string }) => {
  const { t, i18n } = useTranslation()
  const { admin } = useAdmin()
  const dir = useDirDetection()
  const is_sudo = admin?.is_sudo || false
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const PERIOD_OPTIONS: PeriodOption[] = useMemo(
    () => [
      ...PERIOD_KEYS.slice(0, 6).map(opt => ({
        label: typeof opt.amount === 'number' ? `${opt.amount} ${t(`time.${opt.unit}${opt.amount > 1 ? 's' : ''}`)}` : '',
        value: opt.key,
        period: opt.period,
        hours: opt.unit === 'hour' && typeof opt.amount === 'number' ? opt.amount : undefined,
        days: opt.unit === 'day' && typeof opt.amount === 'number' ? opt.amount : undefined,
        months: opt.unit === 'month' && typeof opt.amount === 'number' ? opt.amount : undefined,
      })),
      { label: t('alltime', { defaultValue: 'All Time' }), value: 'all', period: 'day', allTime: true },
    ],
    [t],
  )
  const [periodOption, setPeriodOption] = useState<PeriodOption>(() => PERIOD_OPTIONS[3])
  
  // Update periodOption when PERIOD_OPTIONS changes (e.g., language change)
  useEffect(() => {
    setPeriodOption(prev => {
      const currentOption = PERIOD_OPTIONS.find(opt => opt.value === prev.value)
      return currentOption || prev
    })
  }, [PERIOD_OPTIONS])
  
  const { startDate, endDate } = useMemo(() => {
    const now = dayjs()
    let start: dayjs.Dayjs
    if (periodOption.allTime) {
      start = dayjs('2000-01-01T00:00:00Z')
    } else if (periodOption.hours) {
      start = now.subtract(periodOption.hours, 'hour')
    } else if (periodOption.days) {
      const daysToSubtract = periodOption.days === 7 ? 6 : periodOption.days === 3 ? 2 : periodOption.days === 1 ? 0 : periodOption.days
      start = now.subtract(daysToSubtract, 'day').utc().startOf('day')
    } else if (periodOption.months) {
      start = now.subtract(periodOption.months, 'month').utc().startOf('day')
    } else {
      start = now
    }
    return { startDate: start.toISOString(), endDate: now.toISOString() }
  }, [periodOption])

  const shouldUseNodeUsage = is_sudo && !admin_username

  const nodeUsageParams = useMemo(
    () => ({
      period: periodOption.period,
      start: startDate,
      end: dateUtils.toDayjs(endDate).endOf('day').toISOString(),
    }),
    [periodOption.period, startDate, endDate],
  )

  const userUsageParams = useMemo(
    () => ({
      ...(admin_username ? { admin: [admin_username] } : {}),
      period: periodOption.period,
      start: startDate,
      end: dateUtils.toDayjs(endDate).endOf('day').toISOString(),
    }),
    [admin_username, periodOption.period, startDate, endDate],
  )

  const { data: nodeData, isLoading: isLoadingNodes } = useGetUsage(nodeUsageParams, {
    query: {
      enabled: shouldUseNodeUsage,
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const { data: userData, isLoading: isLoadingUsers } = useGetUsersUsage(userUsageParams, {
    query: {
      enabled: !shouldUseNodeUsage,
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const data: UserUsageStatsList | NodeUsageStatsList | undefined = shouldUseNodeUsage ? nodeData : userData
  const isLoading = shouldUseNodeUsage ? isLoadingNodes : isLoadingUsers

  let statsArr: (UserUsageStat | NodeUsageStat)[] = []
  if (data?.stats) {
    if (typeof data.stats === 'object' && !Array.isArray(data.stats)) {
      const statsObj = data.stats as { [key: string]: (UserUsageStat | NodeUsageStat)[] }
      statsArr = statsObj['-1'] || statsObj[Object.keys(statsObj)[0]] || []
    } else if (Array.isArray(data.stats)) {
      statsArr = data.stats
    }
  }

  const chartData = useMemo(() => transformUsageData({ stats: statsArr }, periodOption, shouldUseNodeUsage, i18n.language), [statsArr, periodOption, shouldUseNodeUsage, i18n.language])

  const trend = useMemo(() => {
    if (!chartData || chartData.length < 2) return null
    const last = (chartData[chartData.length - 1] as { traffic: number })?.traffic || 0
    const prev = (chartData[chartData.length - 2] as { traffic: number })?.traffic || 0
    if (prev === 0) return null
    const percent = ((last - prev) / prev) * 100
    return percent
  }, [chartData])

  const xAxisInterval = useMemo(() => {
    // For hours (12h, 24h), show approximately 6-8 labels
    if (periodOption.hours) {
      const targetLabels = periodOption.hours === 12 ? 6 : 8
      return Math.max(1, Math.floor(chartData.length / targetLabels))
    }

    if (periodOption.months || periodOption.allTime) {
      const targetLabels = 5;
      return Math.max(1, Math.floor(chartData.length / targetLabels))
    }

    if (periodOption.days && periodOption.days > 7) {
      const targetLabels = periodOption.days === 30 ? 10 : 8
      return Math.max(1, Math.floor(chartData.length / targetLabels))
    }

    return 0
  }, [periodOption.hours, periodOption.months, periodOption.allTime, periodOption.days, chartData.length])

  return (
    <Card className="flex h-full flex-col justify-between overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{t('admins.used.traffic', { defaultValue: 'Traffic Usage' })}</CardTitle>
          <CardDescription className='mt-1.5'>{t('admins.monitor.traffic', { defaultValue: 'Monitor admin traffic usage over time' })}</CardDescription>
        </div>
        <Select
          value={periodOption.value}
          onValueChange={val => {
            const found = PERIOD_OPTIONS.find(opt => opt.value === val)
            if (found) setPeriodOption(found)
          }}
        >
          <SelectTrigger className={`h-8 w-32 text-xs${dir === 'rtl' ? 'text-right' : ''}`} dir={dir}>
            <SelectValue>{periodOption.label}</SelectValue>
          </SelectTrigger>
          <SelectContent dir={dir}>
            {PERIOD_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={opt.value} className={dir === 'rtl' ? 'text-right' : ''}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-center overflow-hidden p-2 sm:p-6">
        {isLoading ? (
          <div className="mx-auto w-full max-w-7xl">
            <div className="max-h-[320px] min-h-[200px] w-full">
              <div className="flex h-full flex-col">
                <div className="flex-1">
                  <div className="flex h-full items-end justify-center">
                    <div className="flex h-48 items-end gap-2">
                      {[1, 2, 3, 4, 5, 6, 7].map(i => (
                        <div key={i} className="animate-pulse">
                          <div className={`w-8 rounded-t-lg bg-muted ${i === 4 ? 'h-32' : i === 3 || i === 5 ? 'h-24' : i === 2 || i === 6 ? 'h-16' : 'h-20'}`} />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="mt-4 flex justify-between">
                  <div className="h-4 w-16 animate-pulse rounded bg-muted" />
                  <div className="h-4 w-16 animate-pulse rounded bg-muted" />
                </div>
              </div>
            </div>
          </div>
        ) : chartData.length === 0 ? (
          <div className="mt-16 flex min-h-[200px] flex-col items-center justify-center gap-4 text-muted-foreground">
            <SearchXIcon className="size-16" strokeWidth={1} />
            {t('admins.monitor.no_traffic', { defaultValue: 'No traffic data available' })}
          </div>
        ) : (
          <ChartContainer config={chartConfig} dir="ltr" className="h-[240px] w-full overflow-x-auto sm:h-[320px]">
            <BarChart
              data={chartData}
              margin={{ top: 16, right: 4, left: 4, bottom: 8 }}
              barCategoryGap="10%"
              onMouseMove={state => {
                if (state.activeTooltipIndex !== activeIndex) {
                  setActiveIndex(state.activeTooltipIndex !== undefined ? state.activeTooltipIndex : null)
                }
              }}
              onMouseLeave={() => {
                setActiveIndex(null)
              }}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tickLine={false}
                tickMargin={10}
                axisLine={false}
                angle={0}
                textAnchor="middle"
                height={30}
                interval={xAxisInterval}
                minTickGap={5}
                tick={{ fontSize: 10 }}
                tickFormatter={(value: string): string => {
                  // Use the value directly as it's already formatted in transformUsageData
                  // For the last data point when it's today, check if we need to show "Today"
                  if (periodOption.days && chartData.length > 0) {
                    const lastDataPoint = chartData[chartData.length - 1] as { date: string; period_start?: string }
                    // Check if this tick value matches the last data point's date
                    if (lastDataPoint && value === lastDataPoint.date) {
                      const today = dateUtils.toDayjs(new Date())
                      // Try to get period_start from the data point
                      const dataPoint = chartData.find((d) => typeof d === 'object' && d !== null && 'date' in d && (d as { date: string }).date === value) as { period_start?: string } | undefined
                      if (dataPoint?.period_start) {
                        const pointDate = dateUtils.toDayjs(dataPoint.period_start)
                        if (pointDate.isSame(today, 'day')) {
                          return t('today', { defaultValue: 'Today' })
                        }
                      }
                    }
                  }

                  return value || ''
                }}
              />
              <YAxis 
                dataKey={'traffic'} 
                tickLine={false} 
                tickMargin={4} 
                axisLine={false} 
                width={40}
                tickFormatter={val => formatBytes(val, 0, true).toString()} 
                tick={{ fontSize: 10 }}
              />
              <ChartTooltip cursor={false} content={<CustomBarTooltip period={periodOption.period} />} />
              <Bar dataKey="traffic" radius={6} maxBarSize={48}>
                {chartData.map((_, index: number) => (
                  <Cell key={`cell-${index}`} fill={index === activeIndex ? 'hsl(var(--muted-foreground))' : 'hsl(var(--primary))'} />
                ))}
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
      <CardFooter className="mt-0 flex-col items-start gap-2 pt-2 text-sm sm:pt-4">
        {chartData.length > 0 && trend !== null && trend > 0 && (
          <div className="flex gap-2 font-medium leading-none text-green-600 dark:text-green-400">
            {t('usersTable.trendingUp', { defaultValue: 'Trending up by' })} {trend.toFixed(1)}% <TrendingUp className="h-4 w-4" />
          </div>
        )}
        {chartData.length > 0 && trend !== null && trend < 0 && (
          <div className="flex gap-2 font-medium leading-none text-red-600 dark:text-red-400">
            {t('usersTable.trendingDown', { defaultValue: 'Trending down by' })} {Math.abs(trend).toFixed(1)}% <TrendingDown className="h-4 w-4" />
          </div>
        )}
        <div className="leading-none text-muted-foreground">{t('statistics.trafficUsageDescription', { defaultValue: 'Total traffic usage across all servers' })}</div>
      </CardFooter>
    </Card>
  )
}

export default DataUsageChart
