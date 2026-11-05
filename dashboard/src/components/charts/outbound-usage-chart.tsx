import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, TooltipProps } from 'recharts'
import { useTranslation } from 'react-i18next'
import { BarChart3, Download, Info, Network, Upload } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import { useTheme } from '@/app/providers/theme-provider'
import NodeStatsModal from '@/features/nodes/dialogs/node-stats-modal'
import { useChartPeriodLimit } from '@/hooks/use-chart-period-limit'
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
  USAGE_RECORD_BUCKET_MINUTES,
} from '@/utils/chart-period-utils'
import { EmptyState } from './empty-state'
import PeriodSelector from './period-selector'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from './time-selector'

// Tags past this rank are summed into one "other" series so the stack stays readable
const MAX_OUTBOUND_SERIES = 8
const OUTBOUND_REFRESH_MS = 1000 * 60 * 5

type Series = { key: string; label: string; isOther: boolean }
type OutboundDataPoint = { time: string; _period_start: string } & Record<string, number | string>

const statBytes = (stat: NodeUsageStat) => Number(stat.uplink || 0) + Number(stat.downlink || 0)
const isSeriesKey = (key: string) => !key.startsWith('_') && key !== 'time'

function OutboundTooltip({ active, payload, chartConfig, period, dir }: TooltipProps<number, string> & { chartConfig: ChartConfig; period: Period; dir: string }) {
  const { t, i18n } = useTranslation()
  if (!active || !payload?.length) return null

  const point = payload[0].payload as OutboundDataPoint
  const rows = payload.filter(item => Number(item.value || 0) > 0).sort((a, b) => Number(b.value || 0) - Number(a.value || 0))
  const total = rows.reduce((sum, item) => sum + Number(item.value || 0), 0)

  return (
    <div dir={dir} className="border-border bg-background min-w-[140px] rounded border p-2 text-xs shadow">
      <div className="mb-1 text-center font-semibold opacity-70" dir="ltr">
        {formatTooltipDate(point._period_start, period, i18n.language)}
      </div>
      <div className="text-muted-foreground mb-1.5 flex items-center justify-center gap-1.5">
        <span>{t('statistics.totalUsage', { defaultValue: 'Total' })}:</span>
        <span dir="ltr" className="font-mono">
          {formatBytes(total)}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        {rows.map(item => {
          const key = String(item.dataKey)
          return (
            <div key={key} className="flex flex-col">
              <div className="flex items-center justify-between gap-3">
                <span className="flex min-w-0 items-center gap-1">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: chartConfig[key]?.color }} />
                  <span className="max-w-[120px] truncate">{chartConfig[key]?.label}</span>
                </span>
                <span dir="ltr" className="text-muted-foreground font-mono">
                  {formatBytes(Number(item.value || 0))}
                </span>
              </div>
              <span dir="ltr" className="text-muted-foreground flex items-center justify-end gap-1 font-mono text-[10px]">
                <Upload className="h-2.5 w-2.5 shrink-0" />
                {formatBytes(Number(point[`_uplink_${key}`] || 0))}
                <span className="opacity-60">|</span>
                <Download className="h-2.5 w-2.5 shrink-0" />
                {formatBytes(Number(point[`_downlink_${key}`] || 0))}
              </span>
            </div>
          )
        })}
      </div>
      <div className="text-muted-foreground mt-1.5 flex items-center justify-center gap-1 text-[10px]">
        <Info className="h-2.5 w-2.5 shrink-0" />
        <span>{t('statistics.clickForMore', { defaultValue: 'Click for more details' })}</span>
      </div>
    </div>
  )
}

export function OutboundUsageChart({ nodeId }: { nodeId?: number }) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()
  const [selectedTime, setSelectedTime] = useState<TrafficShortcutKey>('1w')
  const [selectedPeriodOverride, setPeriodOverride] = useState<ChartPeriodOverride>(CHART_PERIOD_OVERRIDE_AUTO)
  const [modalOpen, setModalOpen] = useState(false)
  const [currentDataIndex, setCurrentDataIndex] = useState(0)
  const { allowedPeriods, periodOverride } = useChartPeriodLimit({ shortcut: selectedTime }, selectedPeriodOverride, setPeriodOverride, { recordBucketMinutes: USAGE_RECORD_BUCKET_MINUTES })

  // Move the range forward while mounted; a fixed end would hide buckets recorded after the first load
  const [rangeTick, setRangeTick] = useState(0)
  useEffect(() => {
    const id = window.setInterval(() => setRangeTick(tick => tick + 1), OUTBOUND_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [])

  const queryRange = useMemo(
    () => getChartQueryRangeFromShortcut(selectedTime, new Date(), { minuteForOneHour: true, periodOverride: resolvePeriodOverride(periodOverride) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the tick only re-runs new Date()
    [selectedTime, periodOverride, rangeTick],
  )
  const selection = `${selectedTime}|${periodOverride}|${nodeId ?? ''}`
  const period = queryRange.period

  const { data, isLoading, error } = useGetOutboundUsage(
    {
      period,
      start: queryRange.startDate,
      end: queryRange.endDate,
      ...(nodeId !== undefined ? { node_id: nodeId } : {}),
    },
    {
      query: {
        meta: { selection },
        // Day buckets keep the same start/end until midnight, so the key alone does not refresh them
        refetchInterval: OUTBOUND_REFRESH_MS,
        // Keep the bars on a timed range move, show the skeleton when the admin picks another range
        placeholderData: (previous, previousQuery) => (previousQuery?.meta?.selection === selection ? previous : undefined),
      },
    },
  )

  // Series keys are not the tags themselves: recharts reads a dotted dataKey as a nested path
  const { series, chartData, totalBytes } = useMemo(() => {
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
        row[`_uplink_${key}`] = Number(row[`_uplink_${key}`] || 0) + Number(point.uplink || 0)
        row[`_downlink_${key}`] = Number(row[`_downlink_${key}`] || 0) + Number(point.downlink || 0)
        rows.set(point.period_start, row)
      })
    })

    const sortedRows = [...rows.values()].sort((a, b) => new Date(a._period_start).getTime() - new Date(b._period_start).getTime())
    const totalBytes = ranked.reduce((sum, item) => sum + item.total, 0)
    return { series: seriesList, chartData: sortedRows, totalBytes }
  }, [data?.stats, period, i18n.language, selectedTime, t])

  const chartConfig = useMemo(() => {
    const isDark = resolvedTheme === 'dark'
    return series.reduce<ChartConfig>((config, item, index) => {
      config[item.key] = { label: item.label, color: item.isOther ? 'hsl(var(--muted-foreground))' : getChartSeriesColor(index, isDark) }
      return config
    }, {})
  }, [series, resolvedTheme])

  const handleChartClick = useCallback(
    (state: unknown) => {
      const index = (state as { activeTooltipIndex?: unknown } | null)?.activeTooltipIndex
      if (typeof index !== 'number' || !chartData[index]) return
      const hasUsage = Object.keys(chartData[index]).some(key => isSeriesKey(key) && Number(chartData[index][key] || 0) > 0)
      if (!hasUsage) return
      setCurrentDataIndex(index)
      setModalOpen(true)
    },
    [chartData],
  )

  const handleModalNavigate = useCallback(
    (index: number) => {
      if (chartData[index]) setCurrentDataIndex(index)
    },
    [chartData],
  )

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 xl:flex-row">
          <div className="flex flex-1 flex-col gap-2 border-b px-4 py-3 xl:border-b-0 xl:px-6 xl:py-4">
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
              <PeriodSelector value={periodOverride} onValueChange={setPeriodOverride} allowedPeriods={allowedPeriods} className="w-full sm:w-[7rem]" />
            </div>
          </div>
          <div className="m-0 flex flex-col justify-center p-4 xl:border-l xl:p-5 xl:px-6">
            <span className="text-muted-foreground text-xs sm:text-sm">{t('statistics.usageDuringPeriod')}</span>
            <span dir="ltr" className="text-foreground flex items-center justify-center gap-2 text-lg">
              <BarChart3 className="text-muted-foreground h-4 w-4" />
              {isLoading ? <Skeleton className="h-5 w-20" /> : totalBytes > 0 ? formatBytes(totalBytes, 2) : <span className="text-muted-foreground">-</span>}
            </span>
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
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }} onClick={handleChartClick}>
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
                  <Bar key={item.key} dataKey={item.key} stackId="outbound" fill={chartConfig[item.key]?.color} cursor="pointer" isAnimationActive={chartData.length < 200} />
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

      <NodeStatsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        data={chartData[currentDataIndex] ?? null}
        chartConfig={chartConfig}
        period={period}
        allChartData={chartData}
        currentIndex={currentDataIndex}
        onNavigate={handleModalNavigate}
        title={t('statistics.outboundStats', { defaultValue: 'Outbound Statistics' })}
        distributionTitle={t('statistics.outboundTrafficDistribution', { defaultValue: 'Outbound Traffic Distribution' })}
        description={t('statistics.outboundStatsDescription', {
          defaultValue: 'Detailed traffic statistics for each outbound tag at this time period. Click on bars in the chart to view more details.',
        })}
      />
    </>
  )
}
