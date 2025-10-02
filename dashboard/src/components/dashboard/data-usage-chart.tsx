import { Bar, BarChart, CartesianGrid, XAxis, YAxis, ResponsiveContainer, Cell, TooltipProps } from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '../ui/card'
import { ChartConfig, ChartContainer, ChartTooltip } from '../ui/chart'
import { formatBytes } from '@/utils/formatByte'
import { useTranslation } from 'react-i18next'
import { useGetUsersUsage, Period } from '@/service/api'
import { useMemo, useState } from 'react'
import { SearchXIcon, TrendingUp, TrendingDown } from 'lucide-react'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select'
import { dateUtils } from '@/utils/dateFormatter'
import dayjs from '@/lib/dayjs'

interface PeriodOption {
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

const transformUsageData = (apiData: any, periodOption: any) => {
  if (!apiData?.stats || !Array.isArray(apiData.stats)) {
    return []
  }

  return apiData.stats.map((stat: any, index: number, array: any[]) => {
    const d = dateUtils.toDayjs(stat.period_start)
    const isLastItem = index === array.length - 1

    let displayLabel = ''
    if (periodOption.hours) {
      if (isLastItem) {
        displayLabel = 'Today'
      } else {
        displayLabel = d.format('HH:mm')
      }
    } else {
      if (isLastItem) {
        displayLabel = 'Today'
      } else {
        displayLabel = d.format('MM/DD')
      }
    }

    return {
      date: displayLabel,
      fullDate: stat.period_start,
      localFullDate: d.toISOString(),
      traffic: stat.total_traffic || 0,
    }
  })
}

const chartConfig = {
  traffic: {
    label: 'traffic',
    color: 'hsl(var(--foreground))',
  },
} satisfies ChartConfig

function CustomBarTooltip({ active, payload, period }: TooltipProps<any, any> & { period?: string }) {
  const { t, i18n } = useTranslation()
  if (!active || !payload || !payload.length) return null
  const data = payload[0].payload
  const d = dateUtils.toDayjs(data.localFullDate || data.fullDate)
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
          <span className={isRTL ? 'mr-1' : 'ml-1'}>{formatBytes(data.traffic)}</span>
        </div>
      </div>
    </div>
  )
}

const DataUsageChart = ({ admin_username }: { admin_username?: string }) => {
  const { t, i18n } = useTranslation()
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

  const { startDate, endDate } = useMemo(() => {
    const now = dayjs()
    let start: dayjs.Dayjs
    if (periodOption.allTime) {
      start = dayjs('2000-01-01T00:00:00Z') // Arbitrary early date
    } else if (periodOption.hours) {
      start = now.subtract(periodOption.hours, 'hour')
    } else if (periodOption.days) {
      // Match the logic from CostumeBarChart.tsx and AllNodesStackedBarChart.tsx
      // For 7d, subtract 6 days; for 3d, subtract 2 days
      const daysToSubtract = periodOption.days === 7 ? 6 : periodOption.days === 3 ? 2 : periodOption.days
      start = now.subtract(daysToSubtract, 'day')
    } else {
      start = now
    }
    return { startDate: start.toISOString(), endDate: now.toISOString() }
  }, [periodOption])

  const { data, isLoading } = useGetUsersUsage(
    {
      ...(admin_username ? { admin: [admin_username] } : {}),
      period: periodOption.period,
      start: startDate,
      end: dateUtils.toDayjs(endDate).endOf('day').toISOString(),
    },
    {
      query: {
        refetchInterval: 1000 * 60 * 5,
      },
    },
  )

  // Extract correct stats array from grouped or flat API response (like CostumeBarChart)
  let statsArr: any[] = []
  if (data?.stats) {
    if (typeof data.stats === 'object' && !Array.isArray(data.stats)) {
      // Use '-1' for all, or first key as fallback
      statsArr = data.stats['-1'] || data.stats[Object.keys(data.stats)[0]] || []
    } else if (Array.isArray(data.stats)) {
      statsArr = data.stats
    }
  }

  const chartData = useMemo(() => transformUsageData({ stats: statsArr }, periodOption), [statsArr, periodOption])

  // Calculate trend
  const trend = useMemo(() => {
    if (!chartData || chartData.length < 2) return null
    const last = chartData[chartData.length - 1]?.traffic || 0
    const prev = chartData[chartData.length - 2]?.traffic || 0
    if (prev === 0) return null
    const percent = ((last - prev) / prev) * 100
    return percent
  }, [chartData])

  return (
    <Card className="flex h-full flex-col justify-between">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{t('admins.used.traffic', { defaultValue: 'Traffic Usage' })}</CardTitle>
          <CardDescription>{t('admins.monitor.traffic', { defaultValue: 'Monitor admin traffic usage over time' })}</CardDescription>
        </div>
        <Select
          value={periodOption.value}
          onValueChange={val => {
            const found = PERIOD_OPTIONS.find(opt => opt.value === val)
            if (found) setPeriodOption(found)
          }}
        >
          <SelectTrigger className={`h-8 w-32 text-xs${i18n.dir() === 'rtl' ? 'text-right' : ''}`} dir={i18n.dir()}>
            <SelectValue>{periodOption.label}</SelectValue>
          </SelectTrigger>
          <SelectContent dir={i18n.dir()}>
            {PERIOD_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={opt.value} className={i18n.dir() === 'rtl' ? 'text-right' : ''}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col justify-center p-2 sm:p-6">
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
          <ChartContainer config={chartConfig} dir="ltr">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart
                data={chartData}
                margin={{ top: 16, right: 8, left: 8, bottom: 8 }}
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
                  tickFormatter={(_value: string, index: number): string => {
                    // If this is the last bar, show 'Today' (translated)
                    if (periodOption.hours && index === chartData.length - 1) {
                      return i18n.language === 'fa' ? 'امروز' : 'Today'
                    }
                    if (periodOption.hours) {
                      // For hour periods, show only time part for compactness
                      const timePart = chartData[index]?.date?.split(' ')[1]
                      return timePart || chartData[index]?.date
                    }
                    // For day periods, show date or 'Today' if present
                    if (chartData[index]?.date === 'Today') {
                      return i18n.language === 'fa' ? 'امروز' : 'Today'
                    }
                    return chartData[index]?.date
                  }}
                />
                <YAxis dataKey={'traffic'} tickLine={false} tickMargin={10} axisLine={false} tickFormatter={val => formatBytes(val, 0, true).toString()} />
                <ChartTooltip cursor={false} content={<CustomBarTooltip period={periodOption.period} />} />
                <Bar dataKey="traffic" radius={6} maxBarSize={48}>
                  {chartData.map((_: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={index === activeIndex ? 'hsl(var(--muted-foreground))' : 'hsl(var(--primary))'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
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
