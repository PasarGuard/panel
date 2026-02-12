import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis, TooltipProps } from 'recharts'
import { DateRange } from 'react-day-picker'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { Period, type NodeUsageStat, type UserUsageStat, useGetAdminUsage, useGetNodesSimple, type NodeSimple, useGetUsage } from '@/service/api'
import { formatBytes, formatGigabytes } from '@/utils/formatByte'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from './empty-state'
import { BarChart3, Calendar, Download, Info, PieChart as PieChartIcon, Upload } from 'lucide-react'
import { useTheme } from '@/components/common/theme-provider'
import NodeStatsModal from '@/components/dialogs/node-stats-modal'
import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from './time-selector'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import {
  formatTooltipDate,
  getChartQueryRangeFromDateRange,
  getChartQueryRangeFromShortcut,
  formatPeriodLabelForPeriod,
  getXAxisIntervalForShortcut,
  toStatsRecord,
  TrafficShortcutKey,
} from '@/utils/chart-period-utils'

type NodeChartDataPoint = {
  time: string
  _period_start: string
  [key: string]: string | number
}

type NodePieChartDataPoint = {
  name: string
  usage: number
  bytes: number
  percentage: number
  fill: string
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

function CustomTooltip({ active, payload, chartConfig, dir, period }: TooltipProps<number, string> & { chartConfig?: ChartConfig; dir: string; period: Period }) {
  const { t, i18n } = useTranslation()
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768)
    }
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as NodeChartDataPoint
  const formattedDate = data._period_start ? formatTooltipDate(data._period_start, period, i18n.language) : String(data.time || '')

  const getNodeColor = (nodeName: string) => chartConfig?.[nodeName]?.color || 'hsl(var(--chart-1))'
  const isRTL = dir === 'rtl'

  const activeNodes = Object.keys(data)
    .filter(key => !key.startsWith('_') && key !== 'time' && key !== '_period_start' && Number(data[key] || 0) > 0)
    .map(nodeName => ({
      name: nodeName,
      usage: Number(data[nodeName] || 0),
      uplink: Number(data[`_uplink_${nodeName}`] || 0),
      downlink: Number(data[`_downlink_${nodeName}`] || 0),
    }))
    .sort((a, b) => b.usage - a.usage)

  const hasDirectionalTraffic = activeNodes.some(node => (node.uplink || 0) > 0 || (node.downlink || 0) > 0)
  const maxNodesToShow = isMobile ? 3 : 6
  const nodesToShow = activeNodes.slice(0, maxNodesToShow)
  const hasMoreNodes = activeNodes.length > maxNodesToShow

  return (
    <div
      className={`min-w-[120px] max-w-[280px] rounded border border-border bg-background p-1.5 text-[10px] shadow sm:min-w-[140px] sm:max-w-[300px] sm:p-2 sm:text-xs ${isRTL ? 'text-right' : 'text-left'} ${isMobile ? 'max-h-[200px] overflow-y-auto' : ''}`}
      dir={isRTL ? 'rtl' : 'ltr'}
    >
      <div className="mb-1 text-center text-[10px] font-semibold opacity-70 sm:text-xs">
        <span dir="ltr" className="inline-block truncate">
          {formattedDate}
        </span>
      </div>
      <div className="mb-1.5 flex items-center justify-center gap-1.5 text-center text-[10px] text-muted-foreground sm:text-xs">
        <span>{t('statistics.totalUsage', { defaultValue: 'Total' })}: </span>
        <span dir="ltr" className="inline-block truncate font-mono">
          {formatGigabytes(activeNodes.reduce((sum, node) => sum + node.usage, 0))}
        </span>
      </div>
      <div className={`grid gap-1 sm:gap-1.5 ${nodesToShow.length > (isMobile ? 2 : 3) ? 'grid-cols-2' : 'grid-cols-1'}`}>
        {nodesToShow.map(node => (
          <div key={node.name} className={`flex flex-col gap-0.5 ${isRTL ? 'items-end' : 'items-start'}`}>
            <span className={`flex items-center gap-0.5 text-[10px] font-semibold sm:text-xs ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
              <div className="h-1.5 w-1.5 flex-shrink-0 rounded-full sm:h-2 sm:w-2" style={{ backgroundColor: getNodeColor(node.name) }} />
              <span className="max-w-[60px] overflow-hidden truncate text-ellipsis sm:max-w-[80px]" title={node.name}>
                {node.name}
              </span>
            </span>
            <span dir="ltr" className="text-[9px] font-mono text-muted-foreground sm:text-[10px]">
              {formatGigabytes(node.usage)}
            </span>
            {hasDirectionalTraffic && (
              <span className={`flex items-center gap-0.5 text-[9px] text-muted-foreground sm:text-[10px] ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <Upload className="h-2.5 w-2.5 flex-shrink-0 sm:h-3 sm:w-3" />
                <span dir="ltr" className="inline-block max-w-[40px] overflow-hidden truncate text-ellipsis font-mono sm:max-w-[50px]" title={String(formatBytes(node.uplink))}>
                  {formatBytes(node.uplink)}
                </span>
                <span className="mx-0.5 text-[8px] opacity-60 sm:text-[10px]">|</span>
                <Download className="h-2.5 w-2.5 flex-shrink-0 sm:h-3 sm:w-3" />
                <span dir="ltr" className="inline-block max-w-[40px] overflow-hidden truncate text-ellipsis font-mono sm:max-w-[50px]" title={String(formatBytes(node.downlink))}>
                  {formatBytes(node.downlink)}
                </span>
              </span>
            )}
          </div>
        ))}
        {hasMoreNodes && (
          <div className="col-span-full mt-1 flex w-full items-center justify-center gap-0.5 text-[9px] text-muted-foreground sm:text-[10px]">
            <Info className="h-2.5 w-2.5 flex-shrink-0 sm:h-3 sm:w-3" />
            <span className="text-center">{t('statistics.clickForMore', { defaultValue: 'Click for more details' })}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function NodePieTooltip({ active, payload }: TooltipProps<number, string>) {
  const { t } = useTranslation()

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as NodePieChartDataPoint

  return (
    <div className="rounded-lg border border-border bg-background/95 p-2 text-xs shadow-sm backdrop-blur-sm">
      <div className="mb-1 flex items-center gap-1.5">
        <div className="h-2.5 w-2.5 rounded-full border border-border/20" style={{ backgroundColor: data.fill }} />
        <span className="font-medium text-foreground">{data.name}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.totalUsage', { defaultValue: 'Total Usage' })}</span>
        <span dir="ltr" className="font-mono font-semibold text-foreground">
          {formatBytes(data.bytes)}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.percentage', { defaultValue: 'Percentage' })}</span>
        <span dir="ltr" className="font-mono text-foreground">{`${data.percentage.toFixed(1)}%`}</span>
      </div>
    </div>
  )
}

export function AllNodesStackedBarChart() {
  const [chartView, setChartView] = useState<'bar' | 'pie'>('bar')
  const [selectedAdmin, setSelectedAdmin] = useState<string>('all')
  const [selectedTime, setSelectedTime] = useState<TrafficShortcutKey>('1w')
  const [showCustomRange, setShowCustomRange] = useState(false)
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [windowWidth, setWindowWidth] = useState<number>(() => (typeof window !== 'undefined' ? window.innerWidth : 1024))
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedData, setSelectedData] = useState<NodeChartDataPoint | null>(null)
  const [currentDataIndex, setCurrentDataIndex] = useState(0)
  const chartContainerRef = useRef<HTMLDivElement>(null)

  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const { data: nodesResponse } = useGetNodesSimple({ all: true }, { query: { enabled: true } })
  const { resolvedTheme } = useTheme()
  const shouldUseNodeUsage = selectedAdmin === 'all'

  const handleModalNavigate = (index: number) => {
    if (!chartData[index]) return
    setCurrentDataIndex(index)
    setSelectedData(chartData[index])
  }

  const nodeList: NodeSimple[] = useMemo(() => nodesResponse?.nodes || [], [nodesResponse])

  const generateDistinctColor = useCallback((index: number, isDark: boolean): string => {
    const distinctHues = [0, 30, 60, 120, 180, 210, 240, 270, 300, 330, 15, 45, 75, 150, 200, 225, 255, 285, 315, 345]
    const saturationVariations = [65, 75, 85, 70, 80, 60, 90, 55, 95, 50]
    const lightnessVariations = isDark ? [45, 55, 35, 50, 40, 60, 30, 65, 25, 70] : [40, 50, 30, 45, 35, 55, 25, 60, 20, 65]
    const hue = distinctHues[index % distinctHues.length]
    const saturation = saturationVariations[index % saturationVariations.length]
    const lightness = lightnessVariations[index % lightnessVariations.length]
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`
  }, [])

  const chartConfig = useMemo(() => {
    const config: ChartConfig = {}
    const isDark = resolvedTheme === 'dark'
    nodeList.forEach((node, index) => {
      if (index === 0) {
        config[node.name] = { label: node.name, color: 'hsl(var(--primary))' }
        return
      }

      if (index < 5) {
        config[node.name] = { label: node.name, color: `hsl(var(--chart-${index + 1}))` }
        return
      }

      config[node.name] = { label: node.name, color: generateDistinctColor(index, isDark) }
    })
    return config
  }, [generateDistinctColor, nodeList, resolvedTheme])

  const activeQueryRange = useMemo(() => {
    if (showCustomRange && customRange?.from && customRange?.to) {
      return getChartQueryRangeFromDateRange(customRange, selectedTime)
    }

    return getChartQueryRangeFromShortcut(selectedTime, new Date(), { minuteForOneHour: true })
  }, [showCustomRange, customRange, selectedTime])

  const activePeriod = activeQueryRange.period

  const usageParams = useMemo(
    () => ({
      period: activePeriod,
      start: activeQueryRange.startDate,
      end: activeQueryRange.endDate,
      group_by_node: true,
    }),
    [activePeriod, activeQueryRange.startDate, activeQueryRange.endDate],
  )

  const { data: nodeUsageData, isLoading: isLoadingNodesUsage, error: nodesUsageError } = useGetUsage(usageParams, {
    query: {
      enabled: shouldUseNodeUsage,
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const { data: adminUsageData, isLoading: isLoadingAdminUsage, error: adminUsageError } = useGetAdminUsage(selectedAdmin, usageParams, {
    query: {
      enabled: !shouldUseNodeUsage && selectedAdmin !== 'all',
      refetchInterval: 1000 * 60 * 5,
    },
  })

  const usageData = shouldUseNodeUsage ? nodeUsageData : adminUsageData
  const isLoading = shouldUseNodeUsage ? isLoadingNodesUsage : isLoadingAdminUsage
  const error = shouldUseNodeUsage ? nodesUsageError : adminUsageError
  const statsByNode = useMemo(() => toStatsRecord<NodeUsageStat | UserUsageStat>(usageData?.stats), [usageData?.stats])

  const { chartData, totalUsage } = useMemo(() => {
    const statsKeys = Object.keys(statsByNode)
    if (statsKeys.length === 0) {
      return { chartData: [] as NodeChartDataPoint[], totalUsage: '0' }
    }

    const hasIndividualNodeData = statsKeys.some(key => key !== '-1')
    const nodeCount = Math.max(nodeList.length, 1)

    if (!hasIndividualNodeData && Array.isArray(statsByNode['-1'])) {
      const aggregatedStats = statsByNode['-1']
      const aggregatedChartData = aggregatedStats.map(point => {
        const usageBytes = getTrafficBytes(point)
        const directionalTraffic = getDirectionalTraffic(point)
        const usagePerNodeInGb = usageBytes / nodeCount / (1024 * 1024 * 1024)

        const entry: NodeChartDataPoint = {
          time: formatPeriodLabelForPeriod(point.period_start, activePeriod, i18n.language),
          _period_start: point.period_start,
        }

        nodeList.forEach(node => {
          entry[node.name] = parseFloat(usagePerNodeInGb.toFixed(2))
          entry[`_uplink_${node.name}`] = directionalTraffic.uplink / nodeCount
          entry[`_downlink_${node.name}`] = directionalTraffic.downlink / nodeCount
        })

        return entry
      })

      const totalBytes = aggregatedStats.reduce((sum, point) => sum + getTrafficBytes(point), 0)
      return {
        chartData: aggregatedChartData,
        totalUsage: totalBytes > 0 ? String(formatBytes(totalBytes, 2)) : '0',
      }
    }

    const allPeriods = new Set<string>()
    Object.values(statsByNode).forEach(statsArray => {
      statsArray.forEach(stat => allPeriods.add(stat.period_start))
    })

    const sortedPeriods = Array.from(allPeriods).sort()
    const chartRows = sortedPeriods.map(periodStart => {
      const row: NodeChartDataPoint = {
        time: formatPeriodLabelForPeriod(periodStart, activePeriod, i18n.language),
        _period_start: periodStart,
      }

      nodeList.forEach(node => {
        const nodeStats = statsByNode[String(node.id)]?.find(stat => stat.period_start === periodStart)
        if (!nodeStats) {
          row[node.name] = 0
          row[`_uplink_${node.name}`] = 0
          row[`_downlink_${node.name}`] = 0
          return
        }

        const usageBytes = getTrafficBytes(nodeStats)
        const directionalTraffic = getDirectionalTraffic(nodeStats)
        row[node.name] = usageBytes / (1024 * 1024 * 1024)
        row[`_uplink_${node.name}`] = directionalTraffic.uplink
        row[`_downlink_${node.name}`] = directionalTraffic.downlink
      })

      return row
    })

    let totalBytes = 0
    Object.values(statsByNode).forEach(statsArray => {
      statsArray.forEach(stat => {
        totalBytes += getTrafficBytes(stat)
      })
    })

    return {
      chartData: chartRows,
      totalUsage: totalBytes > 0 ? String(formatBytes(totalBytes, 2)) : '0',
    }
  }, [statsByNode, nodeList, activePeriod, i18n.language])

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
  }, [showCustomRange, customRange, activePeriod, selectedTime, chartData.length, windowWidth])

  const pieData = useMemo<NodePieChartDataPoint[]>(() => {
    if (chartData.length === 0 || nodeList.length === 0) return []

    const nodesWithUsage = nodeList
      .map((node, index) => {
        const usageInGb = chartData.reduce((sum, row) => sum + Number(row[node.name] || 0), 0)
        const bytes = usageInGb * 1024 * 1024 * 1024
        return {
          name: node.name,
          usage: usageInGb,
          bytes,
          fill: chartConfig[node.name]?.color || `hsl(var(--chart-${(index % 5) + 1}))`,
        }
      })
      .filter(node => node.bytes > 0)

    const totalBytes = nodesWithUsage.reduce((sum, node) => sum + node.bytes, 0)

    return nodesWithUsage
      .map(node => ({
        ...node,
        percentage: totalBytes > 0 ? (node.bytes * 100) / totalBytes : 0,
      }))
      .sort((a, b) => b.bytes - a.bytes)
  }, [chartData, nodeList, chartConfig])

  const pieChartConfig = useMemo<ChartConfig>(
    () =>
      pieData.reduce<ChartConfig>((config, point) => {
        config[point.name] = { label: point.name, color: point.fill }
        return config
      }, {}),
    [pieData],
  )

  const piePaddingAngle = pieData.length > 1 ? 1 : 0

  useEffect(() => {
    const handleResize = () => {
      setWindowWidth(window.innerWidth)
    }

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

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 xl:flex-row">
          <div className="flex flex-1 flex-col gap-2 border-b px-4 py-3 xl:px-6 xl:py-4">
            <div className="flex min-w-0 flex-col justify-center gap-1 pt-2">
              <CardTitle>{t('statistics.trafficUsage')}</CardTitle>
              <CardDescription>{t('statistics.trafficUsageDescription')}</CardDescription>
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
              <div className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border bg-muted/30 p-1">
                <button
                  type="button"
                  aria-label={t('statistics.barChart', { defaultValue: 'Bar chart' })}
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
            {showCustomRange && (
              <div className="flex w-full">
                <TimeRangeSelector onRangeChange={handleCustomRangeChange} initialRange={customRange} className="w-full" />
              </div>
            )}
          </div>
          <div className="m-0 flex flex-col justify-center p-4 xl:border-l xl:p-5 xl:px-6">
            <span className="text-xs text-muted-foreground sm:text-sm">{t('statistics.usageDuringPeriod')}</span>
            <span dir="ltr" className="flex justify-center text-lg text-foreground">
              {isLoading ? <Skeleton className="h-5 w-20" /> : totalUsage}
            </span>
          </div>
        </CardHeader>
        <CardContent ref={chartContainerRef} dir={dir} className="pt-8">
          {isLoading ? (
            <div className="flex max-h-[400px] min-h-[200px] w-full items-center justify-center">
              <Skeleton className="h-[300px] w-full" />
            </div>
          ) : error ? (
            <EmptyState type="error" className="max-h-[400px] min-h-[200px]" />
          ) : nodeList.length === 0 ? (
            <EmptyState type="no-nodes" className="max-h-[400px] min-h-[200px]" />
          ) : (
            <div className="mx-auto w-full">
              <ChartContainer
                dir="ltr"
                config={chartView === 'pie' ? pieChartConfig : chartConfig}
                className="max-h-[400px] min-h-[200px] w-full"
                style={{
                  marginBottom: navigator.userAgent.includes('Safari') && navigator.platform.includes('Mac') ? `${0.18 * window.innerWidth}px` : '0',
                }}
              >
                {chartData.length > 0 && chartView === 'bar' ? (
                  <BarChart
                    accessibilityLayer
                    data={chartData}
                    margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
                    onClick={data => {
                      const clickedIndex = typeof data?.activeTooltipIndex === 'number' ? data.activeTooltipIndex : -1
                      const clickedData = (data?.activePayload?.[0]?.payload ?? (clickedIndex >= 0 ? chartData[clickedIndex] : undefined)) as NodeChartDataPoint | undefined
                      if (!clickedData) return

                      const activeNodesCount = Object.keys(clickedData).filter(key => {
                        if (key.startsWith('_') || key === 'time' || key === '_period_start') return false
                        const usageValue = Number(clickedData[key] || 0)
                        const uplinkValue = Number(clickedData[`_uplink_${key}`] || 0)
                        const downlinkValue = Number(clickedData[`_downlink_${key}`] || 0)
                        return usageValue > 0 || uplinkValue > 0 || downlinkValue > 0
                      }).length

                      if (activeNodesCount > 0) {
                        const resolvedIndex = clickedIndex >= 0 ? clickedIndex : chartData.findIndex(item => item._period_start === clickedData._period_start)
                        setCurrentDataIndex(resolvedIndex >= 0 ? resolvedIndex : 0)
                        setSelectedData(clickedData)
                        setModalOpen(true)
                      }
                    }}
                  >
                    <CartesianGrid direction="ltr" vertical={false} />
                    <XAxis direction="ltr" dataKey="time" tickLine={false} tickMargin={10} axisLine={false} minTickGap={5} interval={xAxisInterval} />
                    <YAxis
                      direction="ltr"
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={value => formatGigabytes(Number(value || 0))}
                      tick={{
                        fill: 'hsl(var(--muted-foreground))',
                        fontSize: 9,
                        fontWeight: 500,
                      }}
                      width={32}
                      tickMargin={2}
                    />
                    <ChartTooltip cursor={false} content={<CustomTooltip chartConfig={chartConfig} dir={dir} period={activePeriod} />} />
                    {nodeList.map((node, index) => (
                      <Bar
                        key={node.id}
                        dataKey={node.name}
                        stackId="a"
                        minPointSize={1}
                        fill={chartConfig[node.name]?.color || `hsl(var(--chart-${(index % 5) + 1}))`}
                        radius={nodeList.length === 1 ? [4, 4, 4, 4] : index === 0 ? [0, 0, 4, 4] : index === nodeList.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                        cursor="pointer"
                        className="overflow-hidden rounded-t-xl"
                      />
                    ))}
                  </BarChart>
                ) : chartData.length > 0 && chartView === 'pie' ? (
                  pieData.length > 0 ? (
                    <PieChart>
                      <ChartTooltip cursor={false} content={<NodePieTooltip />} />
                      <Pie data={pieData} dataKey="bytes" nameKey="name" innerRadius="45%" outerRadius="88%" paddingAngle={piePaddingAngle} strokeWidth={1.5}>
                        {pieData.map(point => (
                          <Cell key={point.name} fill={point.fill} />
                        ))}
                      </Pie>
                    </PieChart>
                  ) : (
                    <EmptyState type="no-data" title={t('statistics.noDataInRange')} description={t('statistics.noDataInRangeDescription')} className="max-h-[400px] min-h-[200px]" />
                  )
                ) : (
                  <EmptyState type="no-data" title={t('statistics.noDataInRange')} description={t('statistics.noDataInRangeDescription')} className="max-h-[400px] min-h-[200px]" />
                )}
              </ChartContainer>
              {chartData.length > 0 && (
                <div className="overflow-x-auto pt-3">
                  <div className="flex min-w-max items-center justify-center gap-4">
                    {(chartView === 'pie' ? pieData : nodeList).map(item => {
                      const nodeName = typeof item === 'object' && 'name' in item ? item.name : ''
                      const itemConfig = chartConfig[nodeName]
                      const percentage = typeof item === 'object' && 'percentage' in item ? item.percentage : undefined
                      return (
                        <div dir="ltr" key={nodeName} className="flex items-center gap-1.5 [&>svg]:h-3 [&>svg]:w-3 [&>svg]:text-muted-foreground">
                          <div
                            className="h-2 w-2 shrink-0 rounded-[2px]"
                            style={{
                              backgroundColor: itemConfig?.color || (typeof item === 'object' && 'fill' in item ? item.fill : 'hsl(var(--chart-1))'),
                            }}
                          />
                          <span className="whitespace-nowrap text-xs">
                            {nodeName}
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

      <NodeStatsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        data={selectedData}
        chartConfig={chartConfig}
        period={activePeriod}
        allChartData={chartData}
        currentIndex={currentDataIndex}
        onNavigate={handleModalNavigate}
        hideUplinkDownlink={selectedAdmin !== 'all'}
      />
    </>
  )
}
