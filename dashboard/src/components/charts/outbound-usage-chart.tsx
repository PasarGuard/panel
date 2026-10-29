import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, TooltipProps } from 'recharts'
import { useTranslation } from 'react-i18next'
import { Network } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import { useTheme } from '@/app/providers/theme-provider'
import useDirDetection from '@/hooks/use-dir-detection'
import { Period, type NodeUsageStat, useGetOutboundUsage } from '@/service/api'
import { getChartSeriesColor } from '@/utils/chart-colors'
import { formatBytes } from '@/utils/formatByte'
import {
  CHART_PERIOD_OVERRIDE_AUTO,
  type ChartPeriodOverride,
  formatPeriodLabelForPeriod,
  formatTooltipDate,
  getChartQueryRangeFromShortcut,
  resolvePeriodOverride,
  TrafficShortcutKey,
} from '@/utils/chart-period-utils'
import { EmptyState } from './empty-state'
import PeriodSelector from './period-selector'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from './time-selector'

// Tags past this rank are summed into one "other" series so the stack stays readable
const MAX_OUTBOUND_SERIES = 8

type Series = { key: string; label: string; isOther: boolean }
type OutboundDataPoint = { time: string; _period_start: string } & Record<string, number | string>

const statBytes = (stat: NodeUsageStat) => Number(stat.uplink || 0) + Number(stat.downlink || 0)

function OutboundTooltip({ active, payload, chartConfig, period, dir }: TooltipProps<number, string> & { chartConfig: ChartConfig; period: Period; dir: string }) {
  const { i18n } = useTranslation()
  if (!active || !payload?.length) return null

  const point = payload[0].payload as OutboundDataPoint
  const rows = payload.filter(item => Number(item.value || 0) > 0).sort((a, b) => Number(b.value || 0) - Number(a.value || 0))

  return (
    <div dir={dir} className="border-border bg-background min-w-[140px] rounded border p-2 text-xs shadow">
      <div className="mb-1 text-center font-semibold opacity-70" dir="ltr">
        {formatTooltipDate(point._period_start, period, i18n.language)}
      </div>
      {rows.map(item => (
        <div key={String(item.dataKey)} className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 items-center gap-1">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: chartConfig[String(item.dataKey)]?.color }} />
            <span className="max-w-[120px] truncate">{chartConfig[String(item.dataKey)]?.label}</span>
          </span>
          <span dir="ltr" className="text-muted-foreground font-mono">
            {formatBytes(Number(item.value || 0))}
          </span>
        </div>
      ))}
    </div>
  )
}

export function OutboundUsageChart({ nodeId }: { nodeId?: number }) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()
  const [selectedTime, setSelectedTime] = useState<TrafficShortcutKey>('1w')
  const [periodOverride, setPeriodOverride] = useState<ChartPeriodOverride>(CHART_PERIOD_OVERRIDE_AUTO)

  const queryRange = useMemo(
    () => getChartQueryRangeFromShortcut(selectedTime, new Date(), { minuteForOneHour: true, periodOverride: resolvePeriodOverride(periodOverride) }),
    [selectedTime, periodOverride],
  )
  const period = queryRange.period

  const { data, isLoading, error } = useGetOutboundUsage(
    {
      period,
      start: queryRange.startDate,
      end: queryRange.endDate,
      ...(nodeId !== undefined ? { node_id: nodeId } : {}),
    },
    { query: { refetchInterval: 1000 * 60 * 5 } },
  )

  // Series keys are not the tags themselves: recharts reads a dotted dataKey as a nested path
  const { series, chartData } = useMemo(() => {
    const stats = data?.stats ?? {}
    const ranked = Object.entries(stats)
      .map(([tag, points]) => ({ tag, total: points.reduce((sum, point) => sum + statBytes(point), 0) }))
      .filter(item => item.total > 0)
      .sort((a, b) => b.total - a.total)

    const shown = ranked.slice(0, MAX_OUTBOUND_SERIES)
    const seriesList: Series[] = shown.map((item, index) => ({ key: `s${index}`, label: item.tag, isOther: false }))
    const keyByTag = new Map(shown.map((item, index) => [item.tag, `s${index}`]))
    if (ranked.length > MAX_OUTBOUND_SERIES) {
      seriesList.push({ key: 'other', label: t('statistics.outboundUsageOther'), isOther: true })
    }

    const rows = new Map<string, OutboundDataPoint>()
    ranked.forEach(({ tag }) => {
      const key = keyByTag.get(tag) ?? 'other'
      stats[tag].forEach(point => {
        const row = rows.get(point.period_start) ?? {
          time: formatPeriodLabelForPeriod(point.period_start, period, i18n.language, { shortcut: selectedTime }),
          _period_start: point.period_start,
        }
        row[key] = Number(row[key] || 0) + statBytes(point)
        rows.set(point.period_start, row)
      })
    })

    const sortedRows = [...rows.values()].sort((a, b) => new Date(a._period_start).getTime() - new Date(b._period_start).getTime())
    return { series: seriesList, chartData: sortedRows }
  }, [data?.stats, period, i18n.language, selectedTime, t])

  const chartConfig = useMemo(() => {
    const isDark = resolvedTheme === 'dark'
    return series.reduce<ChartConfig>((config, item, index) => {
      config[item.key] = { label: item.label, color: item.isOther ? 'hsl(var(--muted-foreground))' : getChartSeriesColor(index, isDark) }
      return config
    }, {})
  }, [series, resolvedTheme])

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 border-b px-4 py-3 xl:px-6 xl:py-4">
        <div className="flex min-w-0 flex-col gap-1 pt-2">
          <CardTitle className="flex min-w-0 items-center gap-2">
            <Network className="text-muted-foreground h-4 w-4 shrink-0" />
            <span className="truncate">{t('statistics.outboundUsage')}</span>
          </CardTitle>
          <CardDescription className="text-pretty">{t('statistics.outboundUsageDescription')}</CardDescription>
        </div>
        <div className="flex w-full min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <TimeSelector
            selectedTime={selectedTime}
            setSelectedTime={value => setSelectedTime(value as TrafficShortcutKey)}
            shortcuts={TRAFFIC_TIME_SELECTOR_SHORTCUTS}
            maxVisible={5}
            className="w-full sm:w-fit"
          />
          <PeriodSelector value={periodOverride} onValueChange={setPeriodOverride} className="w-full sm:w-[7rem]" />
        </div>
      </CardHeader>
      <CardContent dir={dir} className="px-4 pt-4 sm:px-6 sm:pt-8">
        {isLoading ? (
          <Skeleton className="h-[200px] w-full sm:h-[320px]" />
        ) : error ? (
          <EmptyState type="error" className="max-h-[300px] min-h-[150px]" />
        ) : chartData.length === 0 ? (
          <EmptyState type="no-data" description={t('statistics.outboundUsageEmpty')} className="max-h-[300px] min-h-[150px]" />
        ) : (
          <ChartContainer dir="ltr" config={chartConfig} className="h-[200px] w-full sm:h-[320px] lg:h-[400px]">
            <BarChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <CartesianGrid direction="ltr" vertical={false} />
              <XAxis direction="ltr" dataKey="time" tickLine={false} tickMargin={8} axisLine={false} minTickGap={28} tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 8, fontWeight: 500 }} />
              <YAxis
                direction="ltr"
                tickLine={false}
                axisLine={false}
                tickFormatter={value => formatBytes(Number(value || 0), 0, true).toString()}
                tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 8, fontWeight: 500 }}
                width={36}
                tickMargin={2}
              />
              <ChartTooltip cursor={false} content={props => <OutboundTooltip {...(props as TooltipProps<number, string>)} chartConfig={chartConfig} period={period} dir={dir} />} />
              {series.map(item => (
                <Bar key={item.key} dataKey={item.key} stackId="outbound" fill={chartConfig[item.key]?.color} isAnimationActive={chartData.length < 200} />
              ))}
            </BarChart>
          </ChartContainer>
        )}
        {!isLoading && !error && series.length > 0 && (
          <div className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1.5 text-xs">
            {series.map(item => (
              <span key={item.key} className="text-muted-foreground flex min-w-0 items-center gap-1.5">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: chartConfig[item.key]?.color }} />
                <span className="max-w-[140px] truncate" title={item.label}>
                  {item.label}
                </span>
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
