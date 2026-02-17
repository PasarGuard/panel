import { Area, AreaChart, CartesianGrid, XAxis, YAxis, Tooltip, TooltipProps } from 'recharts'
import { useState, useEffect, useRef, useMemo } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChartConfig, ChartContainer } from '@/components/ui/chart'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from 'react-i18next'
import { SystemStats, Period, NodeStats, NodeRealtimeStats, useGetNodeStatsPeriodic } from '@/service/api'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from './empty-state'
import { Button } from '@/components/ui/button'
import { Clock, History, Cpu, MemoryStick } from 'lucide-react'
import { formatOffsetDateTime } from '@/utils/dateTimeParsing'
import { useTheme } from 'next-themes'
import {
  buildPeriodOptions,
  formatPeriodLabel,
  formatTooltipDate,
  getDateRangeForPeriodOption,
  getDefaultPeriodOption,
  getXAxisInterval,
  PeriodOption,
  toChartQueryEndDate,
} from '@/utils/chart-period-utils'

type DataPoint = {
  time: string
  cpu: number
  ram: number
  _period_start?: string
}

const CustomTooltip = ({ active, payload, period }: TooltipProps<number, string> & { period: Period }) => {
  const { i18n } = useTranslation()

  if (!active || !payload || !payload.length) {
    return null
  }

  const data = payload[0].payload as DataPoint
  const formattedDate = data._period_start ? formatTooltipDate(data._period_start, period, i18n.language) : data.time

  return (
    <div dir="ltr" className="rounded-lg border bg-background/95 p-3 shadow-lg backdrop-blur-sm">
      <p className="text-sm font-medium text-muted-foreground">
        <span dir="ltr">{formattedDate}</span>
      </p>
      <div className="mt-1 space-y-1">
        {payload.map((entry, index) => (
          <div key={index} className="flex items-center gap-2">
            <div
              className="h-3 w-3 rounded-full"
              style={{
                backgroundColor: entry.color,
                boxShadow: `0 0 8px ${entry.color}`,
              }}
            />
            <span className="text-sm font-medium capitalize">{entry.name}:</span>
            <span className="text-sm font-bold">{Number(entry.value || 0).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

interface AreaCostumeChartProps {
  nodeId?: number
  currentStats?: SystemStats | NodeRealtimeStats | null
  realtimeStats?: SystemStats | NodeRealtimeStats
}

const isSystemStats = (stats: SystemStats | NodeRealtimeStats): stats is SystemStats => 'total_user' in stats

const isNodeRealtimeStats = (stats: SystemStats | NodeRealtimeStats): stats is NodeRealtimeStats => 'incoming_bandwidth_speed' in stats

export function AreaCostumeChart({ nodeId, currentStats, realtimeStats }: AreaCostumeChartProps) {
  const { t, i18n } = useTranslation()
  const { resolvedTheme } = useTheme()

  const [realtimeHistory, setRealtimeHistory] = useState<DataPoint[]>([])
  const [realtimeError, setRealtimeError] = useState<Error | null>(null)
  const [viewMode, setViewMode] = useState<'realtime' | 'historical'>('realtime')

  const chartContainerRef = useRef<HTMLDivElement>(null)

  const PERIOD_OPTIONS = useMemo(() => buildPeriodOptions(t), [t])
  const [periodOption, setPeriodOption] = useState<PeriodOption>(() => getDefaultPeriodOption(PERIOD_OPTIONS))

  useEffect(() => {
    setPeriodOption(previous => PERIOD_OPTIONS.find(option => option.value === previous.value) ?? getDefaultPeriodOption(PERIOD_OPTIONS))
  }, [PERIOD_OPTIONS])

  const chartConfig = useMemo<ChartConfig>(
    () => ({
      cpu: {
        label: t('statistics.cpuUsage'),
        color: 'hsl(var(--chart-1))',
      },
      ram: {
        label: t('statistics.ramUsage'),
        color: 'hsl(var(--chart-2))',
      },
    }),
    [t],
  )

  const gradientDefs = useMemo(() => {
    const isDark = resolvedTheme === 'dark'
    return {
      cpu: {
        id: 'cpuGradient',
        color1: 'hsl(var(--chart-1))',
        color2: isDark ? 'rgba(59, 130, 246, 0.2)' : 'rgba(59, 130, 246, 0.3)',
        color3: isDark ? 'rgba(59, 130, 246, 0.05)' : 'rgba(59, 130, 246, 0.1)',
        color4: 'rgba(59, 130, 246, 0)',
      },
      ram: {
        id: 'ramGradient',
        color1: 'hsl(var(--chart-2))',
        color2: isDark ? 'rgba(16, 185, 129, 0.2)' : 'rgba(16, 185, 129, 0.3)',
        color3: isDark ? 'rgba(16, 185, 129, 0.05)' : 'rgba(16, 185, 129, 0.1)',
        color4: 'rgba(16, 185, 129, 0)',
      },
    }
  }, [resolvedTheme])

  useEffect(() => {
    setRealtimeHistory([])
    setRealtimeError(null)
    setViewMode('realtime')
  }, [nodeId])

  const toggleViewMode = () => {
    if (viewMode === 'realtime') {
      setViewMode('historical')
      return
    }

    setViewMode('realtime')
    setRealtimeHistory([])
  }

  useEffect(() => {
    if (!realtimeStats || viewMode !== 'realtime') return

    try {
      const now = new Date()
      const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`

      let cpuUsage = 0
      let ramUsage = 0

      if (isSystemStats(realtimeStats) || isNodeRealtimeStats(realtimeStats)) {
        cpuUsage = Number(realtimeStats.cpu_usage ?? 0)
        const memUsed = Number(realtimeStats.mem_used ?? 0)
        const memTotal = Number(realtimeStats.mem_total ?? 1)
        ramUsage = parseFloat(((memUsed / memTotal) * 100).toFixed(1))
      }

      setRealtimeHistory(previous => {
        const next = [
          ...previous,
          {
            time: timeStr,
            cpu: cpuUsage,
            ram: ramUsage,
            _period_start: formatOffsetDateTime(now),
          },
        ]

        const MAX_HISTORY = 120
        const CLEANUP_THRESHOLD = 150

        if (next.length > CLEANUP_THRESHOLD) {
          const cleaned = next.filter((_, index) => {
            if (index >= next.length - 60) return true
            return index % 2 === 0
          })

          if (cleaned.length > MAX_HISTORY) {
            return cleaned.slice(-MAX_HISTORY)
          }

          return cleaned
        }

        return next
      })

      setRealtimeError(null)
    } catch (error) {
      setRealtimeError(error as Error)
    }
  }, [realtimeStats, viewMode])

  const { startDate, endDate } = useMemo(() => getDateRangeForPeriodOption(periodOption), [periodOption])
  const historicalParams = useMemo(
    () => ({
      start: startDate,
      end: toChartQueryEndDate(endDate),
      period: periodOption.period,
    }),
    [startDate, endDate, periodOption.period],
  )

  const { data: historicalData, isLoading: isLoadingHistorical, error: historicalError } = useGetNodeStatsPeriodic(nodeId ?? 0, historicalParams, {
    query: {
      enabled: viewMode === 'historical' && nodeId !== undefined,
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const historicalHistory = useMemo<DataPoint[]>(() => {
    const statsArray = historicalData?.stats
    if (!Array.isArray(statsArray)) return []

    return statsArray.map((point: NodeStats) => ({
      time: formatPeriodLabel(point.period_start, periodOption, i18n.language),
      cpu: point.cpu_usage_percentage,
      ram: point.mem_usage_percentage,
      _period_start: point.period_start,
    }))
  }, [historicalData?.stats, periodOption, i18n.language])

  const chartData = viewMode === 'historical' ? historicalHistory : realtimeHistory
  const isLoading = viewMode === 'historical' ? isLoadingHistorical : realtimeHistory.length === 0 && !realtimeError && !!realtimeStats
  const error = viewMode === 'historical' ? historicalError : realtimeError
  const historicalXAxisInterval = useMemo(() => getXAxisInterval(periodOption, historicalHistory.length), [periodOption, historicalHistory.length])

  let displayCpuUsage: string | JSX.Element = <Skeleton className="h-5 w-16" />
  let displayRamUsage: string | JSX.Element = <Skeleton className="h-5 w-16" />

  if (currentStats) {
    if (isSystemStats(currentStats) || isNodeRealtimeStats(currentStats)) {
      const cpuUsage = Number(currentStats.cpu_usage ?? 0)
      const memUsed = Number(currentStats.mem_used ?? 0)
      const memTotal = Number(currentStats.mem_total ?? 1)
      const ramPercentage = (memUsed / memTotal) * 100

      displayCpuUsage = `${cpuUsage.toFixed(1)}%`
      displayRamUsage = `${ramPercentage.toFixed(1)}%`
    }
  } else if (!isLoading && error) {
    displayCpuUsage = t('error')
    displayRamUsage = t('error')
  }

  return (
    <Card className="flex flex-1 flex-col">
      <CardHeader className="flex flex-col space-y-4 p-4 md:p-6">
        <div className="flex flex-col space-y-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
          <div className="flex items-center space-x-3">
            <div className="flex items-center gap-x-2">
              <CardTitle className="text-lg md:text-xl">{viewMode === 'realtime' ? t('statistics.realTimeData') : t('statistics.historicalData')}</CardTitle>
            </div>
          </div>

          {nodeId !== undefined && (
            <Button variant={viewMode === 'realtime' ? 'default' : 'outline'} size="sm" onClick={toggleViewMode} className="h-9 w-full px-4 font-medium sm:w-auto">
              {viewMode === 'realtime' ? (
                <>
                  <History className="mr-2 h-4 w-4" />
                  <span>{t('statistics.viewHistorical')}</span>
                </>
              ) : (
                <>
                  <Clock className="mr-2 h-4 w-4" />
                  <span>{t('statistics.viewRealtime')}</span>
                </>
              )}
            </Button>
          )}
        </div>

        <CardDescription className="text-sm text-muted-foreground sm:!mt-0">{viewMode === 'realtime' ? t('statistics.realtimeDescription') : t('statistics.historicalDescription')}</CardDescription>
        <div className="grid grid-cols-2 gap-4 pt-2 sm:gap-6">
          <div className="flex flex-col items-center space-y-2 rounded-lg bg-muted/50 p-3">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('statistics.cpuUsage')}</span>
            </div>
            <span className="text-xl font-bold text-foreground sm:text-2xl">{displayCpuUsage}</span>
          </div>
          <div className="flex flex-col items-center space-y-2 rounded-lg bg-muted/50 p-3">
            <div className="flex items-center gap-2">
              <MemoryStick className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('statistics.ramUsage')}</span>
            </div>
            <span dir="ltr" className="text-xl font-bold text-foreground sm:text-2xl">
              {displayRamUsage}
            </span>
          </div>
        </div>
      </CardHeader>

      {viewMode === 'historical' && nodeId !== undefined && (
        <div className="border-t bg-muted/30 p-4 md:p-6">
          <div className="flex flex-col space-y-4 lg:flex-row lg:items-center lg:justify-between lg:space-y-0">
            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-foreground">{t('statistics.selectTimeRange')}</h4>
              <p className="text-xs text-muted-foreground">{t('statistics.selectTimeRangeDescription')}</p>
            </div>
            <Select
              value={periodOption.value}
              onValueChange={value => {
                const nextOption = PERIOD_OPTIONS.find(option => option.value === value)
                if (nextOption) {
                  setPeriodOption(nextOption)
                }
              }}
            >
              <SelectTrigger className="h-9 w-full text-xs sm:w-32">
                <SelectValue>{periodOption.label}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {PERIOD_OPTIONS.map(option => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      <CardContent className="flex-1 p-4 pt-0 md:p-6">
        {isLoading ? (
          <div className="flex h-[280px] w-full items-center justify-center sm:h-[320px] lg:h-[360px]">
            <Skeleton className="h-full w-full rounded-lg" />
          </div>
        ) : error ? (
          <EmptyState type="error" className="h-[280px] sm:h-[320px] lg:h-[360px]" />
        ) : chartData.length === 0 ? (
          <EmptyState
            type="no-data"
            title={viewMode === 'realtime' ? t('statistics.waitingForData') : t('statistics.noDataAvailable')}
            description={viewMode === 'realtime' ? t('statistics.waitingForDataDescription') : t('statistics.selectTimeRangeToView')}
            className="h-[280px] sm:h-[320px] lg:h-[360px]"
          />
        ) : (
          <div ref={chartContainerRef} className="h-[280px] w-full transition-all duration-300 ease-in-out sm:h-[320px] lg:h-[360px]">
            <ChartContainer dir="ltr" config={chartConfig} className="h-full w-full">
              <AreaChart data={chartData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                <defs>
                  <linearGradient id={gradientDefs.cpu.id} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={gradientDefs.cpu.color1} stopOpacity={0.9} />
                    <stop offset="30%" stopColor={gradientDefs.cpu.color2} stopOpacity={0.4} />
                    <stop offset="70%" stopColor={gradientDefs.cpu.color3} stopOpacity={0.1} />
                    <stop offset="100%" stopColor={gradientDefs.cpu.color4} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id={gradientDefs.ram.id} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={gradientDefs.ram.color1} stopOpacity={0.9} />
                    <stop offset="30%" stopColor={gradientDefs.ram.color2} stopOpacity={0.4} />
                    <stop offset="70%" stopColor={gradientDefs.ram.color3} stopOpacity={0.1} />
                    <stop offset="100%" stopColor={gradientDefs.ram.color4} stopOpacity={0} />
                  </linearGradient>
                </defs>

                <CartesianGrid vertical={false} strokeDasharray="4 4" stroke="hsl(var(--border))" opacity={0.1} />

                <XAxis
                  dataKey="time"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={12}
                  tick={{
                    fill: 'hsl(var(--muted-foreground))',
                    fontSize: 10,
                    fontWeight: 500,
                  }}
                  interval={viewMode === 'historical' ? historicalXAxisInterval : 'preserveStartEnd'}
                  minTickGap={viewMode === 'historical' ? 5 : 30}
                />

                <YAxis
                  tickLine={false}
                  tickFormatter={value => `${value.toFixed(0)}%`}
                  axisLine={false}
                  tickMargin={2}
                  domain={[0, 100]}
                  tick={{
                    fill: 'hsl(var(--muted-foreground))',
                    fontSize: 9,
                    fontWeight: 500,
                  }}
                  width={32}
                />

                <Tooltip
                  content={<CustomTooltip period={viewMode === 'historical' ? periodOption.period : Period.hour} />}
                  cursor={{
                    stroke: 'hsl(var(--border))',
                    strokeWidth: 1,
                    strokeDasharray: '4 4',
                    opacity: 0.3,
                  }}
                />

                <Area
                  dataKey="cpu"
                  type="monotone"
                  fill={`url(#${gradientDefs.cpu.id})`}
                  stroke={gradientDefs.cpu.color1}
                  strokeWidth={2}
                  dot={
                    viewMode === 'realtime'
                      ? false
                      : {
                          fill: 'white',
                          stroke: gradientDefs.cpu.color1,
                          strokeWidth: 2,
                          r: 3,
                        }
                  }
                  activeDot={{
                    r: 6,
                    fill: 'white',
                    stroke: gradientDefs.cpu.color1,
                    strokeWidth: 2,
                  }}
                  animationDuration={viewMode === 'realtime' ? 800 : 1500}
                  animationEasing="ease-out"
                  isAnimationActive={true}
                  animationBegin={0}
                />

                <Area
                  dataKey="ram"
                  type="monotone"
                  fill={`url(#${gradientDefs.ram.id})`}
                  stroke={gradientDefs.ram.color1}
                  strokeWidth={2}
                  dot={
                    viewMode === 'realtime'
                      ? false
                      : {
                          fill: 'white',
                          stroke: gradientDefs.ram.color1,
                          strokeWidth: 2,
                          r: 3,
                        }
                  }
                  activeDot={{
                    r: 6,
                    fill: 'white',
                    stroke: gradientDefs.ram.color1,
                    strokeWidth: 2,
                  }}
                  animationDuration={viewMode === 'realtime' ? 800 : 1500}
                  animationEasing="ease-out"
                  isAnimationActive={true}
                  animationBegin={100}
                />
              </AreaChart>
            </ChartContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
