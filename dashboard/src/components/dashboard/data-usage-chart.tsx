import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Cell, TooltipProps } from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '../ui/card'
import { ChartConfig, ChartContainer, ChartTooltip } from '../ui/chart'
import { formatBytes } from '@/utils/formatByte'
import { useTranslation } from 'react-i18next'
import { useGetUsersUsage, useGetUsage, Period, UserUsageStatsList, NodeUsageStatsList, UserUsageStat, NodeUsageStat } from '@/service/api'
import { useMemo, useState, useEffect } from 'react'
import { SearchXIcon, TrendingUp, TrendingDown } from 'lucide-react'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import { formatPeriodLabelForPeriod, formatTooltipDate, getChartQueryRangeFromShortcut, getXAxisIntervalForShortcut } from '@/utils/chart-period-utils'

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
  { key: '1h', period: 'minute' as Period, amount: 1, unit: 'hour' },
  { key: '2h', period: 'hour' as Period, amount: 2, unit: 'hour' },
  { key: '4h', period: 'hour' as Period, amount: 4, unit: 'hour' },
  { key: '6h', period: 'hour' as Period, amount: 6, unit: 'hour' },
  { key: '12h', period: 'hour' as Period, amount: 12, unit: 'hour' },
  { key: '24h', period: 'hour' as Period, amount: 24, unit: 'hour' },
  { key: '2d', period: 'day' as Period, amount: 2, unit: 'day' },
  { key: '3d', period: 'day' as Period, amount: 3, unit: 'day' },
  { key: '5d', period: 'day' as Period, amount: 5, unit: 'day' },
  { key: '7d', period: 'day' as Period, amount: 7, unit: 'day' },
  { key: '14d', period: 'day' as Period, amount: 14, unit: 'day' },
  { key: '30d', period: 'day' as Period, amount: 30, unit: 'day' },
  { key: '1m', period: 'day' as Period, amount: 1, unit: 'month' },
  { key: '3m', period: 'day' as Period, amount: 3, unit: 'month' },
  { key: 'all', period: 'day' as Period, allTime: true },
]

const transformUsageData = (apiData: { stats: (UserUsageStat | NodeUsageStat)[] }, period: Period, isNodeUsage: boolean = false, locale: string = 'en') => {
  if (!apiData?.stats || !Array.isArray(apiData.stats)) {
    return []
  }

  return apiData.stats.map((stat: UserUsageStat | NodeUsageStat) => {
    const displayLabel = formatPeriodLabelForPeriod(stat.period_start, period, locale)

    const traffic = isNodeUsage ? ((stat as NodeUsageStat).uplink || 0) + ((stat as NodeUsageStat).downlink || 0) : (stat as UserUsageStat).total_traffic || 0

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
  const formattedDate = data.period_start ? formatTooltipDate(data.period_start, period ?? Period.hour, i18n.language) : String(data.date ?? '')

  const isRTL = i18n.language === 'fa'

  return (
    <div className={`min-w-[160px] rounded border border-border bg-gradient-to-br from-background to-muted/80 p-2 text-xs shadow ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
      <div className={`mb-1 text-xs font-semibold ${isRTL ? 'text-right' : 'text-left'}`}>
        {t('statistics.date', { defaultValue: 'Date' })}:{' '}
        <span dir="ltr" className="inline-block">
          {formattedDate}
        </span>
      </div>
      <div className="flex flex-col gap-0.5 text-xs">
        <div>
          <span className="font-medium text-foreground">{t('statistics.totalUsage', { defaultValue: 'Total Usage' })}:</span>
          <span dir="ltr" className={isRTL ? 'mr-1' : 'ml-1'}>
            {formatBytes(data.traffic)}
          </span>
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
      ...PERIOD_KEYS.filter(opt => !opt.allTime).map(opt => ({
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
  const [periodOption, setPeriodOption] = useState<PeriodOption>(() => PERIOD_OPTIONS.find(opt => opt.value === '7d') ?? PERIOD_OPTIONS[0])

  // Update periodOption when PERIOD_OPTIONS changes (e.g., language change)
  useEffect(() => {
    setPeriodOption(prev => {
      const currentOption = PERIOD_OPTIONS.find(opt => opt.value === prev.value)
      return currentOption || prev
    })
  }, [PERIOD_OPTIONS])

  const queryRange = useMemo(() => getChartQueryRangeFromShortcut(periodOption.value, new Date(), { minuteForOneHour: true }), [periodOption.value])
  const activePeriod = queryRange.period

  const shouldUseNodeUsage = is_sudo && !admin_username

  const nodeUsageParams = useMemo(
    () => ({
      period: activePeriod,
      start: queryRange.startDate,
      end: queryRange.endDate,
    }),
    [activePeriod, queryRange.startDate, queryRange.endDate],
  )

  const userUsageParams = useMemo(
    () => ({
      ...(admin_username ? { admin: [admin_username] } : {}),
      period: activePeriod,
      start: queryRange.startDate,
      end: queryRange.endDate,
    }),
    [admin_username, activePeriod, queryRange.startDate, queryRange.endDate],
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

  const chartData = useMemo(() => transformUsageData({ stats: statsArr }, activePeriod, shouldUseNodeUsage, i18n.language), [statsArr, activePeriod, shouldUseNodeUsage, i18n.language])

  const trend = useMemo(() => {
    if (!chartData || chartData.length < 2) return null
    const last = (chartData[chartData.length - 1] as { traffic: number })?.traffic || 0
    const prev = (chartData[chartData.length - 2] as { traffic: number })?.traffic || 0
    if (prev === 0) return null
    const percent = ((last - prev) / prev) * 100
    return percent
  }, [chartData])

  // Calculate total usage during period
  const totalUsageDuringPeriod = useMemo(() => {
    if (!chartData || chartData.length === 0) return '0 B'
    const totalBytes = chartData.reduce((sum, dataPoint) => {
      const traffic = (dataPoint as { traffic: number })?.traffic || 0
      return sum + traffic
    }, 0)
    return formatBytes(totalBytes, 2)
  }, [chartData])

  const xAxisInterval = useMemo(() => getXAxisIntervalForShortcut(periodOption.value, chartData.length, { minuteForOneHour: true }), [periodOption.value, chartData.length])

  return (
    <Card className="flex h-full flex-col justify-between overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{t('admins.used.traffic', { defaultValue: 'Traffic Usage' })}</CardTitle>
          <CardDescription className="mt-1.5">{t('admins.monitor.traffic', { defaultValue: 'Monitor admin traffic usage over time' })}</CardDescription>
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
                tickFormatter={(value: string): string => value || ''}
              />
              <YAxis dataKey={'traffic'} tickLine={false} tickMargin={4} axisLine={false} width={40} tickFormatter={val => formatBytes(val, 0, true).toString()} tick={{ fontSize: 10 }} />
              <ChartTooltip cursor={false} content={<CustomBarTooltip period={activePeriod} />} />
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
        {chartData.length > 0 && (
          <div className="leading-none text-muted-foreground">
            {t('statistics.usageDuringPeriod', { defaultValue: 'Usage During Period' })}: <span dir="ltr" className="font-mono">{totalUsageDuringPeriod}</span>
          </div>
        )}
        <div className="leading-none text-muted-foreground">{t('statistics.trafficUsageDescription', { defaultValue: 'Total traffic usage across all servers' })}</div>
      </CardFooter>
    </Card>
  )
}

export default DataUsageChart
