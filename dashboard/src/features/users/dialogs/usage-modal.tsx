import { useState, useMemo, useEffect, useCallback } from 'react'
import type { ComponentProps } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card'
import { ChartContainer, ChartTooltip, ChartConfig } from '@/components/ui/chart'
import { BarChart3, PieChart as PieChartIcon, TrendingUp, Calendar, Info } from 'lucide-react'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from '@/components/charts/time-selector'
import { useTranslation } from 'react-i18next'
import { Period, useGetNodesSimple, useGetCurrentAdmin, useGetUserUsageById } from '@/service/api'
import type { GetUserUsageParams, NodeSimple, UserUsageStat, UserUsageStatsListStats } from '@/service/api'
import { DateRange } from 'react-day-picker'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import { Button } from '@/components/ui/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { TooltipProps, Area, AreaChart, Bar, BarChart, CartesianGrid, XAxis, YAxis, Cell, Pie, PieChart as RechartsPieChart } from 'recharts'
import useDirDetection from '@/hooks/use-dir-detection'
import { useChartViewType } from '@/hooks/use-chart-view-type'
import { useTheme } from '@/app/providers/theme-provider'
import NodeStatsModal from '@/features/nodes/dialogs/node-stats-modal'
import {
  TrafficShortcutKey,
  formatTooltipDate,
  getChartQueryRangeFromDateRange,
  getChartQueryRangeFromShortcut,
  formatPeriodLabelForPeriod,
  getXAxisIntervalForShortcut,
} from '@/utils/chart-period-utils'

interface UsageModalProps {
  open: boolean
  onClose: () => void
  userId: number
}

type NodePieChartDataPoint = {
  name: string
  usage: number
  percentage: number
  fill: string
}

type StackBarRadius = [number, number, number, number]
type CellRadiusProps = Partial<ComponentProps<typeof Cell>>
type UsageChartDataPoint = Record<string, string | number | undefined>
type LegacyUserUsageStatsGroup = {
  node_id?: number
  stats?: UserUsageStat[]
}
type UserUsageStatsPayload = UserUsageStatsListStats | LegacyUserUsageStatsGroup[]

const STACKED_BAR_RADIUS = 4
const SQUARE_STACK_RADIUS: StackBarRadius = [0, 0, 0, 0]

const getCellRadiusProps = (radius: StackBarRadius) => ({ radius }) as unknown as CellRadiusProps

const isStatsRecord = (stats: unknown): stats is UserUsageStatsListStats => typeof stats === 'object' && stats !== null && !Array.isArray(stats)

const isLegacyStatsArray = (stats: unknown): stats is LegacyUserUsageStatsGroup[] => Array.isArray(stats)

const getStackedNodeRadius = (row: UsageChartDataPoint, nodeName: string, nodeList: NodeSimple[]): StackBarRadius => {
  const visibleNodes = nodeList.filter(node => Number(row[node.name] || 0) > 0)
  const visibleIndex = visibleNodes.findIndex(node => node.name === nodeName)

  if (visibleIndex < 0) return SQUARE_STACK_RADIUS
  if (visibleNodes.length === 1) return [STACKED_BAR_RADIUS, STACKED_BAR_RADIUS, STACKED_BAR_RADIUS, STACKED_BAR_RADIUS]

  const isBottomSegment = visibleIndex === 0
  const isTopSegment = visibleIndex === visibleNodes.length - 1

  return [isTopSegment ? STACKED_BAR_RADIUS : 0, isTopSegment ? STACKED_BAR_RADIUS : 0, isBottomSegment ? STACKED_BAR_RADIUS : 0, isBottomSegment ? STACKED_BAR_RADIUS : 0]
}

// Move this hook to a separate file if reused elsewhere
const useWindowSize = () => {
  const [windowSize, setWindowSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  })

  useEffect(() => {
    const handleResize = () => {
      setWindowSize({
        width: window.innerWidth,
        height: window.innerHeight,
      })
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  return windowSize
}

function CustomBarTooltip({ active, payload, chartConfig, dir, period }: TooltipProps<number, string> & { chartConfig?: ChartConfig; dir: string; period: Period }) {
  const { t, i18n } = useTranslation()
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768) // md breakpoint
    }
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])
  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload
  const formattedDate = data._period_start ? formatTooltipDate(data._period_start, period, i18n.language) : data.time

  // Get node color from chart config
  const getNodeColor = (nodeName: string) => {
    return chartConfig?.[nodeName]?.color || 'hsl(var(--chart-1))'
  }

  const isRTL = dir === 'rtl'

  // Get active nodes with usage > 0, sorted by usage descending
  const activeNodes = Object.keys(data)
    .filter(key => !key.startsWith('_') && key !== 'time' && key !== '_period_start' && key !== 'usage' && (data[key] || 0) > 0)
    .map(nodeName => ({
      name: nodeName,
      usage: data[nodeName] || 0,
    }))
    .sort((a, b) => b.usage - a.usage)

  // Determine how many nodes to show based on screen size
  const maxNodesToShow = isMobile ? 3 : 6
  const nodesToShow = activeNodes.slice(0, maxNodesToShow)
  const hasMoreNodes = activeNodes.length > maxNodesToShow

  // For user usage data, we typically don't have node breakdowns
  // Check if this is aggregated user data (has usage field but no individual nodes)
  const isUserUsageData = (data.usage !== undefined && activeNodes.length === 0) || (activeNodes.length === 0 && Object.keys(data).includes('usage'))

  return (
    <div
      className={`border-border bg-background max-w-[280px] min-w-[120px] rounded border p-1.5 text-[10px] shadow sm:max-w-[300px] sm:min-w-[140px] sm:p-2 sm:text-xs ${isRTL ? 'text-right' : 'text-left'} ${isMobile ? 'max-h-[200px] overflow-y-auto' : ''}`}
      dir={isRTL ? 'rtl' : 'ltr'}
    >
      <div className={`mb-1 text-center text-[10px] font-semibold opacity-70 sm:text-xs`}>
        <span dir="ltr" className="inline-block truncate">
          {formattedDate}
        </span>
      </div>
      <div className={`text-muted-foreground mb-1.5 flex items-center justify-center gap-1.5 text-center text-[10px] sm:text-xs`}>
        <span>{t('statistics.totalUsage', { defaultValue: 'Total' })}: </span>
        <span dir="ltr" className="inline-block truncate font-mono">
          {isUserUsageData ? data.usage.toFixed(2) : nodesToShow.reduce((sum, node) => sum + node.usage, 0).toFixed(2)} GB
        </span>
      </div>

      {!isUserUsageData && (
        // Node breakdown data
        <div className={`grid gap-1 sm:gap-1.5 ${nodesToShow.length > (isMobile ? 2 : 3) ? 'grid-cols-2' : 'grid-cols-1'}`}>
          {nodesToShow.map(node => (
            <div key={node.name} className={`flex flex-col gap-0.5 ${isRTL ? 'items-end' : 'items-start'}`}>
              <span className={`flex items-center gap-0.5 text-[10px] font-semibold sm:text-xs ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <div className="h-1.5 w-1.5 flex-shrink-0 rounded-full sm:h-2 sm:w-2" style={{ backgroundColor: getNodeColor(node.name) }} />
                <span className="max-w-[60px] truncate overflow-hidden text-ellipsis sm:max-w-[80px]" title={node.name}>
                  {node.name}
                </span>
              </span>
              <span className={`text-muted-foreground flex items-center gap-0.5 text-[9px] sm:text-[10px] ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <span dir="ltr" className="font-mono">
                  {node.usage.toFixed(2)} GB
                </span>
              </span>
            </div>
          ))}
          {hasMoreNodes && (
            <div className={`text-muted-foreground col-span-full mt-1 flex w-full items-center justify-center gap-0.5 text-[9px] sm:text-[10px]`}>
              <Info className="h-2.5 w-2.5 flex-shrink-0 sm:h-3 sm:w-3" />
              <span className="text-center">{t('statistics.clickForMore', { defaultValue: 'Click for more details' })}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function NodePieTooltip({ active, payload }: TooltipProps<number, string>) {
  const { t } = useTranslation()

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as NodePieChartDataPoint

  return (
    <div className="border-border bg-background/95 rounded-lg border p-2 text-xs shadow-sm backdrop-blur-sm">
      <div className="mb-1 flex items-center gap-1.5">
        <div className="border-border/20 h-2.5 w-2.5 rounded-full border" style={{ backgroundColor: data.fill }} />
        <span className="text-foreground font-medium">{data.name}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.totalUsage', { defaultValue: 'Total Usage' })}</span>
        <span dir="ltr" className="text-foreground font-mono font-semibold">
          {data.usage.toFixed(2)} GB
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.percentage', { defaultValue: 'Percentage' })}</span>
        <span dir="ltr" className="text-foreground font-mono">{`${data.percentage.toFixed(1)}%`}</span>
      </div>
    </div>
  )
}

const UsageModal = ({ open, onClose, userId }: UsageModalProps) => {
  // Memoize now only once per modal open
  const [rangeNow, setRangeNow] = useState(() => Date.now())
  useEffect(() => {
    if (open) setRangeNow(Date.now())
  }, [open])

  const [period, setPeriod] = useState<TrafficShortcutKey>('1w')
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [showCustomRange, setShowCustomRange] = useState(false)
  const { t, i18n } = useTranslation()
  const { width } = useWindowSize()
  const [selectedNodeId, setSelectedNodeId] = useState<number | undefined>(undefined)
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedData, setSelectedData] = useState<UsageChartDataPoint | null>(null)
  const [currentDataIndex, setCurrentDataIndex] = useState(0)
  const [chartData, setChartData] = useState<UsageChartDataPoint[] | null>(null)
  const [chartView, setChartView] = useState<'bar' | 'pie'>('bar')
  const chartViewType = useChartViewType()

  // Get current admin to check permissions
  const { data: currentAdmin } = useGetCurrentAdmin()
  const is_sudo = currentAdmin?.is_sudo || false
  const allNodesSelected = selectedNodeId === undefined && is_sudo
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()

  // Reset node selection for non-sudo admins
  useEffect(() => {
    if (!is_sudo) {
      setSelectedNodeId(undefined) // Non-sudo admins see all nodes (master server data)
    }
  }, [is_sudo])

  useEffect(() => {
    if (!allNodesSelected && chartView !== 'bar') {
      setChartView('bar')
    }
  }, [allNodesSelected, chartView])

  // Fetch nodes list - only for sudo admins
  const { data: nodesResponse, isLoading: isLoadingNodes } = useGetNodesSimple(
    { all: true },
    {
      query: {
        enabled: open && is_sudo, // Only fetch nodes for sudo admins when modal is open
      },
    },
  )

  // Navigation handler for modal
  const handleModalNavigate = (index: number) => {
    if (chartData && chartData[index]) {
      setCurrentDataIndex(index)
      setSelectedData(chartData[index])
    }
  }

  // Build color palette for nodes
  const nodeList: NodeSimple[] = useMemo(() => nodesResponse?.nodes || [], [nodesResponse])

  // Function to generate distinct colors based on theme
  const generateDistinctColor = useCallback((index: number, _totalNodes: number, isDark: boolean): string => {
    // Define a more distinct color palette with better contrast
    const distinctHues = [
      0, // Red
      30, // Orange
      60, // Yellow
      120, // Green
      180, // Cyan
      210, // Blue
      240, // Indigo
      270, // Purple
      300, // Magenta
      330, // Pink
      15, // Red-orange
      45, // Yellow-orange
      75, // Yellow-green
      150, // Green-cyan
      200, // Cyan-blue
      225, // Blue-indigo
      255, // Indigo-purple
      285, // Purple-magenta
      315, // Magenta-pink
      345, // Pink-red
    ]

    const hue = distinctHues[index % distinctHues.length]

    // Create more distinct saturation and lightness values
    const saturationVariations = [65, 75, 85, 70, 80, 60, 90, 55, 95, 50]
    const lightnessVariations = isDark ? [45, 55, 35, 50, 40, 60, 30, 65, 25, 70] : [40, 50, 30, 45, 35, 55, 25, 60, 20, 65]

    const saturation = saturationVariations[index % saturationVariations.length]
    const lightness = lightnessVariations[index % lightnessVariations.length]

    return `hsl(${hue}, ${saturation}%, ${lightness}%)`
  }, [])

  // Build chart config dynamically based on nodes
  const chartConfig = useMemo(() => {
    const config: ChartConfig = {}
    const isDark = resolvedTheme === 'dark'
    nodeList.forEach((node, idx) => {
      let color
      if (idx === 0) {
        // First node uses primary color like CostumeBarChart
        color = 'hsl(var(--primary))'
      } else if (idx < 5) {
        // Use palette colors for nodes 2-5: --chart-2, --chart-3, ...
        color = `hsl(var(--chart-${idx + 1}))`
      } else {
        // Generate distinct colors for nodes beyond palette
        color = generateDistinctColor(idx, nodeList.length, isDark)
      }
      config[node.name] = {
        label: node.name,
        color: color,
      }
    })
    return config
  }, [nodeList, resolvedTheme, generateDistinctColor])

  const queryRange = useMemo(() => {
    if (showCustomRange && customRange?.from && customRange?.to) {
      return getChartQueryRangeFromDateRange(customRange, period)
    }

    return getChartQueryRangeFromShortcut(period, new Date(rangeNow), { minuteForOneHour: true })
  }, [showCustomRange, customRange, period, rangeNow])

  const backendPeriod = queryRange.period

  const userUsageParams = useMemo<GetUserUsageParams>(() => {
    const params: GetUserUsageParams = {
      period: backendPeriod,
      start: queryRange.startDate,
      end: queryRange.endDate,
    }

    if (selectedNodeId !== undefined) {
      params.node_id = selectedNodeId
    }

    if (selectedNodeId === undefined && is_sudo) {
      params.group_by_node = true
    }

    return params
  }, [backendPeriod, queryRange.startDate, queryRange.endDate, selectedNodeId, is_sudo])

  // Only fetch when modal is open
  const { data, isLoading } = useGetUserUsageById(userId, userUsageParams, { query: { enabled: open && !!userId } })

  // Prepare chart data for BarChart with node grouping
  const processedChartData = useMemo<UsageChartDataPoint[]>(() => {
    const statsPayload = data?.stats as UserUsageStatsPayload | undefined
    if (!statsPayload) return []

    // If all nodes selected for sudo admins (selectedNodeId is undefined and is_sudo), handle like AllNodesStackedBarChart
    if (selectedNodeId === undefined && is_sudo) {
      let statsByNode: UserUsageStatsListStats = {}
      if (isStatsRecord(statsPayload)) {
        // This is the expected format when no node_id is provided
        statsByNode = statsPayload
      } else if (isLegacyStatsArray(statsPayload)) {
        // fallback: old format - not expected for all nodes
        console.warn('Unexpected array format for all nodes usage')
      }

      // Build a map from node id to node name for quick lookup
      const nodeIdToName = nodeList.reduce(
        (acc, node) => {
          acc[node.id] = node.name
          return acc
        },
        {} as Record<string, string>,
      )

      // Check if we have data for individual nodes or aggregated data
      const hasIndividualNodeData = Object.keys(statsByNode).some(key => key !== '-1')

      if (!hasIndividualNodeData && statsByNode['-1']) {
        // API returned aggregated data for all nodes combined
        const aggregatedStats = statsByNode['-1']

        if (aggregatedStats.length > 0) {
          const nodeCount = Math.max(nodeList.length, 1)
          const data = aggregatedStats.map((point): UsageChartDataPoint => {
            const usageInGB = point.total_traffic / (1024 * 1024 * 1024)
            // Create entry with all nodes having the same usage (aggregated)
            const entry: UsageChartDataPoint = {
              time: formatPeriodLabelForPeriod(point.period_start, backendPeriod, i18n.language),
              _period_start: point.period_start,
            }
            nodeList.forEach(node => {
              // Distribute usage equally among nodes
              const nodeUsage = usageInGB / nodeCount
              entry[node.name] = nodeUsage
            })
            return entry
          })

          return data
        } else {
          return []
        }
      } else {
        // Handle individual node data
        // Build a set of all period_start values
        const allPeriods = new Set<string>()
        Object.values(statsByNode).forEach(arr => arr.forEach(stat => allPeriods.add(stat.period_start)))
        // Sort periods
        const sortedPeriods = Array.from(allPeriods).sort()

        if (sortedPeriods.length > 0) {
          // Build chart data: [{ time, [nodeName]: usage, ... }]
          const data = sortedPeriods.map((periodStart): UsageChartDataPoint => {
            const entry: UsageChartDataPoint = {
              time: formatPeriodLabelForPeriod(periodStart, backendPeriod, i18n.language),
              _period_start: periodStart,
            }

            Object.entries(statsByNode).forEach(([nodeId, statsArr]) => {
              if (nodeId === '-1') return // Skip aggregated data
              const nodeName = nodeIdToName[nodeId]
              if (!nodeName) {
                console.warn('No node name found for ID:', nodeId)
                return
              }
              const nodeStats = statsArr.find(s => s.period_start === periodStart)
              if (nodeStats) {
                const usageInGB = nodeStats.total_traffic / (1024 * 1024 * 1024)
                entry[nodeName] = usageInGB
              } else {
                entry[nodeName] = 0
              }
            })
            return entry
          })

          return data
        } else {
          return []
        }
      }
    } else {
      // Single node selected - use existing logic
      let flatStats: UserUsageStat[] = []
      if (isStatsRecord(statsPayload)) {
        // Dict format: use nodeId if provided, else '-1', else first key
        const key = selectedNodeId !== undefined ? String(selectedNodeId) : '-1'
        if (statsPayload[key] && Array.isArray(statsPayload[key])) {
          flatStats = statsPayload[key]
        } else {
          const firstKey = Object.keys(statsPayload)[0]
          if (firstKey && Array.isArray(statsPayload[firstKey])) {
            flatStats = statsPayload[firstKey]
          } else {
            flatStats = []
          }
        }
      } else if (isLegacyStatsArray(statsPayload)) {
        // List format: use node_id === -1, then 0, else first
        let selectedStats = statsPayload.find(s => s.node_id === -1)
        if (!selectedStats) selectedStats = statsPayload.find(s => s.node_id === 0)
        if (!selectedStats) selectedStats = statsPayload[0]
        flatStats = selectedStats?.stats || []
      }
      return flatStats.map((point): UsageChartDataPoint => {
        const usageInGB = point.total_traffic / (1024 * 1024 * 1024)
        return {
          time: formatPeriodLabelForPeriod(point.period_start, backendPeriod, i18n.language),
          usage: usageInGB,
          _period_start: point.period_start,
        }
      })
    }
  }, [data, backendPeriod, selectedNodeId, nodeList, i18n.language, is_sudo])

  // Update chartData state when processedChartData changes
  useEffect(() => {
    setChartData(processedChartData)
  }, [processedChartData])

  // Calculate total usage during period
  const totalUsageDuringPeriod = useMemo(() => {
    if (!processedChartData || processedChartData.length === 0) return 0

    const getTotalUsage = (dataPoint: UsageChartDataPoint) => {
      if (selectedNodeId === undefined && is_sudo) {
        // All nodes selected - sum all node usages
        return Object.keys(dataPoint)
          .filter(key => !key.startsWith('_') && key !== 'time' && key !== 'usage' && Number(dataPoint[key] || 0) > 0)
          .reduce((sum, nodeName) => sum + Number(dataPoint[nodeName] || 0), 0)
      } else {
        // Single node selected - use usage field
        return Number(dataPoint.usage || 0)
      }
    }

    return processedChartData.reduce((sum, dataPoint) => sum + getTotalUsage(dataPoint), 0)
  }, [processedChartData, selectedNodeId, is_sudo])

  // Calculate trend (simple: compare last and previous usage)
  const trend = useMemo(() => {
    if (!processedChartData || processedChartData.length < 2) return null

    const getTotalUsage = (dataPoint: UsageChartDataPoint) => {
      if (selectedNodeId === undefined && is_sudo) {
        // All nodes selected - sum all node usages
        return Object.keys(dataPoint)
          .filter(key => !key.startsWith('_') && key !== 'time' && key !== 'usage' && Number(dataPoint[key] || 0) > 0)
          .reduce((sum, nodeName) => sum + Number(dataPoint[nodeName] || 0), 0)
      } else {
        // Single node selected - use usage field
        return Number(dataPoint.usage || 0)
      }
    }

    const last = getTotalUsage(processedChartData[processedChartData.length - 1])
    const prev = getTotalUsage(processedChartData[processedChartData.length - 2])
    if (prev === 0) return null
    const percent = ((last - prev) / prev) * 100
    return percent
  }, [processedChartData, selectedNodeId, is_sudo])

  const xAxisInterval = useMemo(() => {
    if (showCustomRange && customRange?.from && customRange?.to) {
      if (backendPeriod === Period.hour || backendPeriod === Period.minute) {
        return Math.max(1, Math.floor(processedChartData.length / 8))
      }

      const daysDiff = Math.ceil(Math.abs(customRange.to.getTime() - customRange.from.getTime()) / (1000 * 60 * 60 * 24))
      if (daysDiff > 30) {
        return Math.max(1, Math.floor(processedChartData.length / 5))
      }

      if (daysDiff > 7) {
        return Math.max(1, Math.floor(processedChartData.length / 8))
      }

      return 0
    }

    if (width < 500 && period === '1w') {
      return processedChartData.length <= 4 ? 0 : Math.max(1, Math.floor(processedChartData.length / 4))
    }

    return getXAxisIntervalForShortcut(period, processedChartData.length, { minuteForOneHour: true })
  }, [showCustomRange, customRange, backendPeriod, processedChartData.length, period, width])

  const pieData = useMemo<NodePieChartDataPoint[]>(() => {
    if (!allNodesSelected || processedChartData.length === 0 || nodeList.length === 0) return []

    const nodesWithUsage = nodeList
      .map((node, index) => {
        const usage = processedChartData.reduce((sum, row) => sum + Number(row[node.name] || 0), 0)
        return {
          name: node.name,
          usage,
          fill: chartConfig[node.name]?.color || `hsl(var(--chart-${(index % 5) + 1}))`,
        }
      })
      .filter(node => node.usage > 0)

    const totalUsage = nodesWithUsage.reduce((sum, node) => sum + node.usage, 0)

    return nodesWithUsage
      .map(node => ({
        ...node,
        percentage: totalUsage > 0 ? (node.usage * 100) / totalUsage : 0,
      }))
      .sort((a, b) => b.usage - a.usage)
  }, [allNodesSelected, processedChartData, nodeList, chartConfig])

  const pieChartConfig = useMemo<ChartConfig>(
    () =>
      pieData.reduce<ChartConfig>((config, point) => {
        config[point.name] = { label: point.name, color: point.fill }
        return config
      }, {}),
    [pieData],
  )

  const piePaddingAngle = pieData.length > 1 ? 1 : 0

  // Handlers
  const handleCustomRangeChange = useCallback((range: DateRange | undefined) => {
    setCustomRange(range)
    if (range?.from && range?.to) {
      setShowCustomRange(true)
    }
  }, [])

  const handleTimeSelect = useCallback((newPeriod: TrafficShortcutKey) => {
    setPeriod(newPeriod)
    setShowCustomRange(false)
    setCustomRange(undefined)
  }, [])

  const handleTrafficChartClick = useCallback(
    (data: unknown) => {
      if (!processedChartData || processedChartData.length === 0) return

      const chartClick = data as { activeTooltipIndex?: unknown; activePayload?: Array<{ payload?: unknown }> } | null
      const clickedIndex = typeof chartClick?.activeTooltipIndex === 'number' ? chartClick.activeTooltipIndex : -1
      const clickedData = (chartClick?.activePayload?.[0]?.payload ?? (clickedIndex >= 0 ? processedChartData[clickedIndex] : undefined)) as UsageChartDataPoint | undefined
      if (!clickedData) return

      if (allNodesSelected) {
        const activeNodesCount = Object.keys(clickedData).filter(
          key => !key.startsWith('_') && key !== 'time' && key !== '_period_start' && key !== 'usage' && Number(clickedData[key] || 0) > 0,
        ).length
        if (activeNodesCount === 0) return
      } else if (Number(clickedData.usage || 0) <= 0) {
        return
      }

      const resolvedIndex = clickedIndex >= 0 ? clickedIndex : processedChartData.findIndex(item => item._period_start === clickedData._period_start)
      setCurrentDataIndex(resolvedIndex >= 0 ? resolvedIndex : 0)
      setSelectedData(clickedData)
      setModalOpen(true)
    },
    [processedChartData, allNodesSelected],
  )

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            <span>{t('usersTable.usageChart', { defaultValue: 'Usage Chart' })}</span>
          </DialogTitle>
          <DialogDescription>{t('usersTable.usageSummary', { defaultValue: 'Showing total usage for the selected period.' })}</DialogDescription>
        </DialogHeader>
        <Card className="w-full border-none bg-transparent shadow-none">
          <CardHeader className="pb-2">
            <div className="flex flex-col items-center gap-4 pt-1">
              <div className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 sm:flex sm:justify-center">
                <TimeSelector
                  selectedTime={period}
                  setSelectedTime={value => handleTimeSelect(value as TrafficShortcutKey)}
                  shortcuts={TRAFFIC_TIME_SELECTOR_SHORTCUTS}
                  maxVisible={5}
                  className="w-full sm:w-auto"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('usersTable.selectCustomRange', { defaultValue: 'Select custom range' })}
                  className={`shrink-0 ${showCustomRange ? 'text-primary' : ''}`}
                  onClick={() => {
                    setShowCustomRange(!showCustomRange)
                    if (!showCustomRange) {
                      setCustomRange(undefined)
                    }
                  }}
                >
                  <Calendar className="h-4 w-4" />
                </Button>
                {allNodesSelected && (
                  <div className="flex w-full items-center justify-center sm:w-fit">
                    <div className="bg-muted/30 inline-flex h-8 w-fit shrink-0 items-center gap-1 rounded-md border p-1">
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
                )}
              </div>
              {/* Node selector - only show for sudo admins */}
              {is_sudo && (
                <div className="flex w-full items-center justify-center gap-2">
                  <Select value={selectedNodeId?.toString() || 'all'} onValueChange={value => setSelectedNodeId(value === 'all' ? undefined : Number(value))} disabled={isLoadingNodes}>
                    <SelectTrigger className="w-full sm:w-[180px]">
                      <SelectValue placeholder={t('userDialog.selectNode', { defaultValue: 'Select Node' })} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('userDialog.allNodes', { defaultValue: 'All Nodes' })}</SelectItem>
                      {nodeList.map(node => (
                        <SelectItem key={node.id} value={node.id.toString()}>
                          {node.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              {showCustomRange && (
                <div className="flex w-full justify-center">
                  <TimeRangeSelector onRangeChange={handleCustomRangeChange} initialRange={customRange} className="w-full sm:w-auto" />
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent dir="ltr" className="mb-0 p-0">
            <div className="w-full">
              {isLoading ? (
                <div className="mx-auto w-full">
                  <div className={`w-full px-4 py-2 ${width < 500 ? 'h-[200px]' : 'h-[320px]'}`}>
                    <div className="flex h-full flex-col">
                      <div className="flex-1">
                        <div className="flex h-full items-end justify-center">
                          <div className={`flex items-end gap-2 ${width < 500 ? 'h-40' : 'h-48'}`}>
                            {[1, 2, 3, 4, 5, 6, 7, 8].map(i => {
                              const isMobile = width < 500
                              let heightClass = ''
                              if (i === 4 || i === 5) {
                                heightClass = isMobile ? 'h-28' : 'h-32'
                              } else if (i === 3 || i === 6) {
                                heightClass = isMobile ? 'h-20' : 'h-24'
                              } else if (i === 2 || i === 7) {
                                heightClass = isMobile ? 'h-12' : 'h-16'
                              } else {
                                heightClass = isMobile ? 'h-16' : 'h-20'
                              }
                              return <Skeleton key={i} className={`w-6 rounded-t-lg sm:w-8 ${heightClass}`} />
                            })}
                          </div>
                        </div>
                      </div>
                      <div className="mt-4 flex justify-between px-2">
                        <Skeleton className="h-3 w-12 sm:h-4 sm:w-16" />
                        <Skeleton className="h-3 w-12 sm:h-4 sm:w-16" />
                      </div>
                    </div>
                  </div>
                </div>
              ) : processedChartData.length === 0 ? (
                <div className="text-muted-foreground flex h-60 flex-col items-center justify-center gap-2">
                  <PieChartIcon className="h-12 w-12 opacity-30" />
                  <div className="text-lg font-medium">{t('usersTable.noUsageData', { defaultValue: 'No usage data available for this period.' })}</div>
                  <div className="text-sm">{t('usersTable.tryDifferentRange', { defaultValue: 'Try a different time range.' })}</div>
                </div>
              ) : (
                <ChartContainer config={allNodesSelected && chartView === 'pie' ? pieChartConfig : chartConfig} dir={'ltr'} className="h-[200px] w-full sm:h-[320px]">
                  {allNodesSelected && chartView === 'pie' ? (
                    <RechartsPieChart>
                      <ChartTooltip cursor={false} content={props => <NodePieTooltip {...(props as TooltipProps<number, string>)} />} />
                      <Pie data={pieData} dataKey="usage" nameKey="name" innerRadius="45%" outerRadius="88%" paddingAngle={piePaddingAngle} strokeWidth={1.5}>
                        {pieData.map(point => (
                          <Cell key={point.name} fill={point.fill} />
                        ))}
                      </Pie>
                    </RechartsPieChart>
                  ) : chartViewType === 'area' ? (
                    <AreaChart data={processedChartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }} onClick={handleTrafficChartClick}>
                      <defs>
                        {allNodesSelected ? (
                          nodeList.map((node, idx) => {
                            const color = chartConfig[node.name]?.color || `hsl(var(--chart-${(idx % 5) + 1}))`
                            return (
                              <linearGradient key={node.id} id={`usage-modal-node-gradient-${node.id}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                                <stop offset="100%" stopColor={color} stopOpacity={0.05} />
                              </linearGradient>
                            )
                          })
                        ) : (
                          <linearGradient id="usage-modal-single-gradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                            <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.05} />
                          </linearGradient>
                        )}
                      </defs>
                      <CartesianGrid direction={'ltr'} vertical={false} />
                      <XAxis direction={'ltr'} dataKey="time" tickLine={false} tickMargin={10} axisLine={false} minTickGap={5} interval={xAxisInterval} />
                      <YAxis
                        direction={'ltr'}
                        tickLine={false}
                        axisLine={false}
                        domain={[0, 'auto']}
                        tickFormatter={value => `${value.toFixed(2)} GB`}
                        tick={{
                          fill: 'hsl(var(--muted-foreground))',
                          fontSize: 9,
                          fontWeight: 500,
                        }}
                        width={32}
                        tickMargin={2}
                      />
                      <ChartTooltip cursor={false} content={props => <CustomBarTooltip {...(props as TooltipProps<number, string>)} chartConfig={chartConfig} dir={dir} period={backendPeriod} />} />
                      {allNodesSelected ? (
                        nodeList.map((node, idx) => (
                          <Area
                            key={node.id}
                            type="monotone"
                            dataKey={node.name}
                            stackId="a"
                            fill={`url(#usage-modal-node-gradient-${node.id})`}
                            stroke={chartConfig[node.name]?.color || `hsl(var(--chart-${(idx % 5) + 1}))`}
                            strokeWidth={1.5}
                            dot={false}
                            activeDot={{ r: 4 }}
                            cursor="pointer"
                          />
                        ))
                      ) : (
                        <Area type="monotone" dataKey="usage" fill="url(#usage-modal-single-gradient)" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} activeDot={{ r: 4 }} cursor="pointer" />
                      )}
                    </AreaChart>
                  ) : (
                    <BarChart data={processedChartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }} onClick={handleTrafficChartClick}>
                      <CartesianGrid direction={'ltr'} vertical={false} />
                      <XAxis direction={'ltr'} dataKey="time" tickLine={false} tickMargin={10} axisLine={false} minTickGap={5} interval={xAxisInterval} />
                      <YAxis
                        direction={'ltr'}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={value => `${value.toFixed(2)} GB`}
                        tick={{
                          fill: 'hsl(var(--muted-foreground))',
                          fontSize: 9,
                          fontWeight: 500,
                        }}
                        width={32}
                        tickMargin={2}
                      />
                      <ChartTooltip cursor={false} content={props => <CustomBarTooltip {...(props as TooltipProps<number, string>)} chartConfig={chartConfig} dir={dir} period={backendPeriod} />} />
                      {allNodesSelected ? (
                        // All nodes selected for sudo admins - render stacked bars
                        nodeList.map((node, idx) => (
                          <Bar key={node.id} dataKey={node.name} stackId="a" fill={chartConfig[node.name]?.color || `hsl(var(--chart-${(idx % 5) + 1}))`} radius={SQUARE_STACK_RADIUS} cursor="pointer">
                            {processedChartData.map(row => (
                              <Cell key={`${node.id}-${row._period_start}`} {...getCellRadiusProps(getStackedNodeRadius(row, node.name, nodeList))} />
                            ))}
                          </Bar>
                        ))
                      ) : (
                        // Single node selected OR non-sudo admin aggregated data - render single bar
                        <Bar dataKey="usage" radius={6} cursor="pointer" minPointSize={2}>
                          {processedChartData.map((_point, index) => (
                            <Cell key={`cell-${index}`} fill={'hsl(var(--primary))'} />
                          ))}
                        </Bar>
                      )}
                    </BarChart>
                  )}
                </ChartContainer>
              )}
            </div>
          </CardContent>
          <CardFooter className="mt-0 flex-col items-start gap-2 text-xs sm:text-sm">
            {trend !== null && trend > 0 && (
              <div className="flex gap-2 leading-none font-medium text-green-600 dark:text-green-400">
                {t('usersTable.trendingUp', { defaultValue: 'Trending up by' })} {trend.toFixed(1)}% <TrendingUp className="h-4 w-4" />
              </div>
            )}
            {trend !== null && trend < 0 && (
              <div className="flex gap-2 leading-none font-medium text-red-600 dark:text-red-400">
                {t('usersTable.trendingDown', { defaultValue: 'Trending down by' })} {Math.abs(trend).toFixed(1)}%
              </div>
            )}
            {processedChartData.length > 0 && (
              <div className="text-muted-foreground leading-none">
                {t('statistics.usageDuringPeriod', { defaultValue: 'Usage During Period' })}:{' '}
                <span dir="ltr" className="font-mono">
                  {totalUsageDuringPeriod.toFixed(2)} GB
                </span>
              </div>
            )}
            <div className="text-muted-foreground leading-none">{t('usersTable.usageSummary', { defaultValue: 'Showing total usage for the selected period.' })}</div>
          </CardFooter>
        </Card>
      </DialogContent>

      {/* Node Stats Modal */}
      <NodeStatsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        data={selectedData}
        chartConfig={chartConfig}
        period={backendPeriod}
        allChartData={processedChartData || []}
        currentIndex={currentDataIndex}
        onNavigate={handleModalNavigate}
        hideUplinkDownlink={true}
      />
    </Dialog>
  )
}

export default UsageModal
