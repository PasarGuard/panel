import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '../ui/dialog'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../ui/card'
import { ChartContainer, ChartTooltip, ChartConfig } from '../ui/chart'
import { PieChart, TrendingUp, Calendar, Info } from 'lucide-react'
import TimeSelector, { TRAFFIC_TIME_SELECTOR_SHORTCUTS } from '../charts/time-selector'
import { useTranslation } from 'react-i18next'
import { Period, useGetUserUsage, useGetNodesSimple, useGetCurrentAdmin, NodeSimple, GetUserUsageParams } from '@/service/api'
import { DateRange } from 'react-day-picker'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import { Button } from '../ui/button'
import { ResponsiveContainer } from 'recharts'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select'
import { TooltipProps } from 'recharts'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Cell } from 'recharts'
import useDirDetection from '@/hooks/use-dir-detection'
import { useTheme } from '@/components/common/theme-provider'
import NodeStatsModal from './node-stats-modal'
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
  username: string
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

function CustomBarTooltip({ active, payload, chartConfig, dir, period }: TooltipProps<any, any> & { chartConfig?: ChartConfig; dir: string; period: Period }) {
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
      className={`min-w-[120px] max-w-[280px] rounded border border-border bg-background p-1.5 text-[10px] shadow sm:min-w-[140px] sm:max-w-[300px] sm:p-2 sm:text-xs ${isRTL ? 'text-right' : 'text-left'} ${isMobile ? 'max-h-[200px] overflow-y-auto' : ''}`}
      dir={isRTL ? 'rtl' : 'ltr'}
    >
      <div className={`mb-1 text-center text-[10px] font-semibold opacity-70 sm:text-xs`}>
        <span dir="ltr" className="inline-block truncate">
          {formattedDate}
        </span>
      </div>
      <div className={`mb-1.5 flex items-center justify-center gap-1.5 text-center text-[10px] text-muted-foreground sm:text-xs`}>
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
                <span className="max-w-[60px] overflow-hidden truncate text-ellipsis sm:max-w-[80px]" title={node.name}>
                  {node.name}
                </span>
              </span>
              <span className={`flex items-center gap-0.5 text-[9px] text-muted-foreground sm:text-[10px] ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <span dir="ltr" className="font-mono">
                  {node.usage.toFixed(2)} GB
                </span>
              </span>
            </div>
          ))}
          {hasMoreNodes && (
            <div className={`col-span-full mt-1 flex w-full items-center justify-center gap-0.5 text-[9px] text-muted-foreground sm:text-[10px]`}>
              <Info className="h-2.5 w-2.5 flex-shrink-0 sm:h-3 sm:w-3" />
              <span className="text-center">{t('statistics.clickForMore', { defaultValue: 'Click for more details' })}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const UsageModal = ({ open, onClose, username }: UsageModalProps) => {
  // Memoize now only once per modal open
  const nowRef = useRef<number>(Date.now())
  useEffect(() => {
    if (open) nowRef.current = Date.now()
  }, [open])

  const [period, setPeriod] = useState<TrafficShortcutKey>('1w')
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [showCustomRange, setShowCustomRange] = useState(false)
  const { t, i18n } = useTranslation()
  const { width } = useWindowSize()
  const [selectedNodeId, setSelectedNodeId] = useState<number | undefined>(undefined)
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedData, setSelectedData] = useState<any>(null)
  const [currentDataIndex, setCurrentDataIndex] = useState(0)
  const [chartData, setChartData] = useState<any[] | null>(null)

  // Get current admin to check permissions
  const { data: currentAdmin } = useGetCurrentAdmin()
  const is_sudo = currentAdmin?.is_sudo || false
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()

  // Reset node selection for non-sudo admins
  useEffect(() => {
    if (!is_sudo) {
      setSelectedNodeId(undefined) // Non-sudo admins see all nodes (master server data)
    }
  }, [is_sudo])

  // Fetch nodes list - only for sudo admins
  const { data: nodesResponse, isLoading: isLoadingNodes } = useGetNodesSimple({ all: true }, {
    query: {
      enabled: open && is_sudo, // Only fetch nodes for sudo admins when modal is open
    },
  })

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

    return getChartQueryRangeFromShortcut(period, new Date(nowRef.current), { minuteForOneHour: true })
  }, [showCustomRange, customRange, period, open])

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
  const { data, isLoading } = useGetUserUsage(username, userUsageParams, { query: { enabled: open } })

  // Prepare chart data for BarChart with node grouping
  const processedChartData = useMemo(() => {
    if (!data?.stats) return []

    // If all nodes selected for sudo admins (selectedNodeId is undefined and is_sudo), handle like AllNodesStackedBarChart
    if (selectedNodeId === undefined && is_sudo) {
      let statsByNode: Record<string, any[]> = {}
      if (data.stats) {
        if (typeof data.stats === 'object' && !Array.isArray(data.stats)) {
          // This is the expected format when no node_id is provided
          statsByNode = data.stats
        } else if (Array.isArray(data.stats)) {
          // fallback: old format - not expected for all nodes
          console.warn('Unexpected array format for all nodes usage')
        }
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
          const data = aggregatedStats.map((point: any) => {
            const usageInGB = point.total_traffic / (1024 * 1024 * 1024)
            // Create entry with all nodes having the same usage (aggregated)
            const entry: any = {
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
          const data = sortedPeriods.map(periodStart => {
            const entry: any = {
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
      let flatStats: any[] = []
      if (data.stats) {
        if (typeof data.stats === 'object' && !Array.isArray(data.stats)) {
          // Dict format: use nodeId if provided, else '-1', else first key
          const key = selectedNodeId !== undefined ? String(selectedNodeId) : '-1'
          if (data.stats[key] && Array.isArray(data.stats[key])) {
            flatStats = data.stats[key]
          } else {
            const firstKey = Object.keys(data.stats)[0]
            if (firstKey && Array.isArray(data.stats[firstKey])) {
              flatStats = data.stats[firstKey]
            } else {
              flatStats = []
            }
          }
        } else if (Array.isArray(data.stats)) {
          // List format: use node_id === -1, then 0, else first
          let selectedStats = data.stats.find((s: any) => s.node_id === -1)
          if (!selectedStats) selectedStats = data.stats.find((s: any) => s.node_id === 0)
          if (!selectedStats) selectedStats = data.stats[0]
          flatStats = selectedStats?.stats || []
          if (!Array.isArray(flatStats)) flatStats = []
        }
      }
      return flatStats.map((point: any) => {
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

    const getTotalUsage = (dataPoint: any) => {
      if (selectedNodeId === undefined && is_sudo) {
        // All nodes selected - sum all node usages
        return Object.keys(dataPoint)
          .filter(key => !key.startsWith('_') && key !== 'time' && key !== 'usage' && (dataPoint[key] || 0) > 0)
          .reduce((sum, nodeName) => sum + (dataPoint[nodeName] || 0), 0)
      } else {
        // Single node selected - use usage field
        return dataPoint.usage || 0
      }
    }

    return processedChartData.reduce((sum, dataPoint) => sum + getTotalUsage(dataPoint), 0)
  }, [processedChartData, selectedNodeId, is_sudo])

  // Calculate trend (simple: compare last and previous usage)
  const trend = useMemo(() => {
    if (!processedChartData || processedChartData.length < 2) return null

    const getTotalUsage = (dataPoint: any) => {
      if (selectedNodeId === undefined) {
        // All nodes selected - sum all node usages
        return Object.keys(dataPoint)
          .filter(key => !key.startsWith('_') && key !== 'time' && key !== 'usage' && (dataPoint[key] || 0) > 0)
          .reduce((sum, nodeName) => sum + (dataPoint[nodeName] || 0), 0)
      } else {
        // Single node selected - use usage field
        return dataPoint.usage
      }
    }

    const last = getTotalUsage(processedChartData[processedChartData.length - 1])
    const prev = getTotalUsage(processedChartData[processedChartData.length - 2])
    if (prev === 0) return null
    const percent = ((last - prev) / prev) * 100
    return percent
  }, [processedChartData, selectedNodeId])

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

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl p-0.5">
        <DialogTitle className="sr-only">{t('usersTable.usageChart', { defaultValue: 'Usage Chart' })}</DialogTitle>
        <DialogDescription className="sr-only">Showing total usage for the selected period</DialogDescription>
        <Card className="w-full border-none shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-center text-lg sm:text-xl">{t('usersTable.usageChart', { defaultValue: 'Usage Chart' })}</CardTitle>
            <CardDescription className="flex flex-col items-center gap-4 pt-4">
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
            </CardDescription>
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
                              return (
                                <div key={i} className="animate-pulse">
                                  <div className={`w-6 rounded-t-lg bg-muted sm:w-8 ${heightClass}`} />
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      </div>
                      <div className="mt-4 flex justify-between px-2">
                        <div className="h-3 w-12 animate-pulse rounded bg-muted sm:h-4 sm:w-16" />
                        <div className="h-3 w-12 animate-pulse rounded bg-muted sm:h-4 sm:w-16" />
                      </div>
                    </div>
                  </div>
                </div>
              ) : processedChartData.length === 0 ? (
                <div className="flex h-60 flex-col items-center justify-center gap-2 text-muted-foreground">
                  <PieChart className="h-12 w-12 opacity-30" />
                  <div className="text-lg font-medium">{t('usersTable.noUsageData', { defaultValue: 'No usage data available for this period.' })}</div>
                  <div className="text-sm">{t('usersTable.tryDifferentRange', { defaultValue: 'Try a different time range.' })}</div>
                </div>
              ) : (
                <ChartContainer config={chartConfig} dir={'ltr'}>
                  <ResponsiveContainer width="100%" height={width < 500 ? 200 : 320}>
                    <BarChart
                      data={processedChartData}
                      margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
                      onClick={data => {
                        if (!processedChartData || processedChartData.length === 0) return

                        const clickedIndex = typeof data?.activeTooltipIndex === 'number' ? data.activeTooltipIndex : -1
                        const clickedData = data?.activePayload?.[0]?.payload ?? (clickedIndex >= 0 ? processedChartData[clickedIndex] : undefined)
                        if (!clickedData) return

                        if (selectedNodeId === undefined && is_sudo) {
                          const activeNodesCount = Object.keys(clickedData).filter(
                            key => !key.startsWith('_') && key !== 'time' && key !== '_period_start' && key !== 'usage' && Number(clickedData[key] || 0) > 0,
                          ).length
                          if (activeNodesCount === 0) return
                        } else {
                          if (Number(clickedData.usage || 0) <= 0) return
                        }

                        const resolvedIndex = clickedIndex >= 0 ? clickedIndex : processedChartData.findIndex(item => item._period_start === clickedData._period_start)
                        setCurrentDataIndex(resolvedIndex >= 0 ? resolvedIndex : 0)
                        setSelectedData(clickedData)
                        setModalOpen(true)
                      }}
                    >
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
                      <ChartTooltip cursor={false} content={<CustomBarTooltip chartConfig={chartConfig} dir={dir} period={backendPeriod} />} />
                      {selectedNodeId === undefined && is_sudo ? (
                        // All nodes selected for sudo admins - render stacked bars
                        nodeList.map((node, idx) => (
                          <Bar
                            key={node.id}
                            dataKey={node.name}
                            stackId="a"
                            minPointSize={1}
                            fill={chartConfig[node.name]?.color || `hsl(var(--chart-${(idx % 5) + 1}))`}
                            radius={nodeList.length === 1 ? [4, 4, 4, 4] : idx === 0 ? [0, 0, 4, 4] : idx === nodeList.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                            cursor="pointer"
                          />
                        ))
                      ) : (
                        // Single node selected OR non-sudo admin aggregated data - render single bar
                        <Bar dataKey="usage" radius={6} cursor="pointer" minPointSize={2}>
                          {processedChartData.map((_: any, index: number) => (
                            <Cell key={`cell-${index}`} fill={'hsl(var(--primary))'} />
                          ))}
                        </Bar>
                      )}
                    </BarChart>
                  </ResponsiveContainer>
                </ChartContainer>
              )}
            </div>
          </CardContent>
          <CardFooter className="mt-0 flex-col items-start gap-2 text-xs sm:text-sm">
            {trend !== null && trend > 0 && (
              <div className="flex gap-2 font-medium leading-none text-green-600 dark:text-green-400">
                {t('usersTable.trendingUp', { defaultValue: 'Trending up by' })} {trend.toFixed(1)}% <TrendingUp className="h-4 w-4" />
              </div>
            )}
            {trend !== null && trend < 0 && (
              <div className="flex gap-2 font-medium leading-none text-red-600 dark:text-red-400">
                {t('usersTable.trendingDown', { defaultValue: 'Trending down by' })} {Math.abs(trend).toFixed(1)}%
              </div>
            )}
            {processedChartData.length > 0 && (
              <div className="leading-none text-muted-foreground">
                {t('statistics.usageDuringPeriod', { defaultValue: 'Usage During Period' })}: <span dir="ltr" className="font-mono">{totalUsageDuringPeriod.toFixed(2)} GB</span>
              </div>
            )}
            <div className="leading-none text-muted-foreground">{t('usersTable.usageSummary', { defaultValue: 'Showing total usage for the selected period.' })}</div>
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
