import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '../ui/dialog'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../ui/card'
import { ChartContainer, ChartTooltip, ChartConfig } from '../ui/chart'
import { PieChart, TrendingUp, Calendar, Info } from 'lucide-react'
import TimeSelector from '../charts/time-selector'
import { useTranslation } from 'react-i18next'
import { Period, useGetUserUsage, useGetNodes, useGetCurrentAdmin, NodeResponse } from '@/service/api'
import { DateRange } from 'react-day-picker'
import { TimeRangeSelector } from '@/components/common/time-range-selector'
import { Button } from '../ui/button'
import { ResponsiveContainer } from 'recharts'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select'
import { dateUtils } from '@/utils/dateFormatter'
import { TooltipProps } from 'recharts'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Cell } from 'recharts'
import useDirDetection from '@/hooks/use-dir-detection'
import { useTheme } from '@/components/common/theme-provider'
import NodeStatsModal from './node-stats-modal'

import { getPeriodFromDateRange } from '@/utils/datePickerUtils'

// Define allowed period keys
const PERIOD_KEYS = ['1h', '12h', '24h', '3d', '1w'] as const
type PeriodKey = (typeof PERIOD_KEYS)[number]

const getPeriodMap = (now: number) => ({
  '1h': { period: Period.minute, start: new Date(now - 60 * 60 * 1000) },
  '12h': { period: Period.hour, start: new Date(now - 12 * 60 * 60 * 1000) },
  '24h': { period: Period.hour, start: new Date(now - 24 * 60 * 60 * 1000) },
  '3d': { period: Period.day, start: new Date(now - 2 * 24 * 60 * 60 * 1000) },
  '1w': { period: Period.day, start: new Date(now - 6 * 24 * 60 * 60 * 1000) },
})

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

function CustomBarTooltip({ active, payload, chartConfig, dir, period }: TooltipProps<any, any> & { chartConfig?: ChartConfig; dir: string; period?: string }) {
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
  const d = dateUtils.toDayjs(data._period_start)

  // Check if this is today's data
  const today = dateUtils.toDayjs(new Date())
  const isToday = d.isSame(today, 'day')

  let formattedDate
  if (i18n.language === 'fa') {
    // Use Persian (Jalali) calendar and Persian locale
    try {
      // If you have dayjs with jalali plugin, use it:
      // formattedDate = d.locale('fa').format('YYYY/MM/DD HH:mm')
      // Otherwise, fallback to toLocaleString
      if (period === Period.day && isToday) {
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
      } else if (period === Period.day) {
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
        // hourly or other: use actual time from data
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
      // hourly or other: use actual time from data
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

      {!isUserUsageData &&(
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
                <span dir="ltr" className="font-mono">{node.usage.toFixed(2)} GB</span>
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

  const [period, setPeriod] = useState<PeriodKey>('1w')
  const [customRange, setCustomRange] = useState<DateRange | undefined>(undefined)
  const [showCustomRange, setShowCustomRange] = useState(false)
  const { t } = useTranslation()
  const { width } = useWindowSize()
  const [selectedNodeId, setSelectedNodeId] = useState<number | undefined>(undefined)
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedData, setSelectedData] = useState<any>(null)
  const [currentDataIndex, setCurrentDataIndex] = useState(0)
  const [chartData, setChartData] = useState<any[] | null>(null)
  const [currentPeriod, setCurrentPeriod] = useState<Period>(Period.hour)

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
  const { data: nodes, isLoading: isLoadingNodes } = useGetNodes(undefined, {
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
  const nodeList: NodeResponse[] = useMemo(() => (Array.isArray(nodes) ? nodes : []), [nodes])

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

  // Memoize periodMap only when modal opens
  const periodMap = useMemo(() => getPeriodMap(nowRef.current), [open])
  let backendPeriod: Period
  let start: Date
  let end: Date | undefined = undefined

  if (showCustomRange && customRange?.from && customRange?.to) {
    // Use the same period logic as other charts
    backendPeriod = getPeriodFromDateRange(customRange)
    start = customRange.from
    end = customRange.to
  } else {
    const map = periodMap[period]
    backendPeriod = map.period
    start = map.start
  }

  // Update current period for tooltip
  useEffect(() => {
    setCurrentPeriod(backendPeriod)
  }, [backendPeriod])

  const userUsageParams = useMemo(() => {
    const baseParams: any = {
      period: backendPeriod,
      start: start.toISOString(),
      node_id: selectedNodeId,
    }

    // Add group_by_node when all nodes are selected for sudo admins (selectedNodeId is undefined)
    if (selectedNodeId === undefined && is_sudo) {
      baseParams.group_by_node = true
    }

    if (showCustomRange && customRange?.from && customRange?.to) {
      return {
        ...baseParams,
        end: dateUtils.toDayjs(customRange.to).endOf('day').toISOString(),
      }
    }

    // For preset periods, set end time for daily periods to avoid extra bars
    const endTime = backendPeriod === Period.day ? dateUtils.toDayjs(new Date()).endOf('day').toISOString() : undefined
    return {
      ...baseParams,
      ...(endTime && { end: endTime }),
    }
  }, [backendPeriod, start, end, period, customRange, showCustomRange, selectedNodeId])

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
          const data = aggregatedStats.map((point: any) => {
            const d = dateUtils.toDayjs(point.period_start)
            let timeFormat
            if (backendPeriod === Period.hour) {
              timeFormat = d.format('HH:mm')
            } else {
              timeFormat = d.format('MM/DD')
            }
            const usageInGB = point.total_traffic / (1024 * 1024 * 1024)
            // Create entry with all nodes having the same usage (aggregated)
            const entry: any = {
              time: timeFormat,
              _period_start: point.period_start,
            }
            nodeList.forEach(node => {
              // Distribute usage equally among nodes
              const nodeUsage = parseFloat((usageInGB / nodeList.length).toFixed(2))
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
            const d = dateUtils.toDayjs(periodStart)
            let timeFormat
            if (backendPeriod === Period.hour) {
              timeFormat = d.format('HH:mm')
            } else {
              timeFormat = d.format('MM/DD')
            }
            const entry: any = {
              time: timeFormat,
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
                entry[nodeName] = parseFloat(usageInGB.toFixed(2))
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
      let filtered = flatStats
      if ((period === '12h' || period === '24h') && !showCustomRange) {
        if (!start || !end)
          return flatStats.map((point: any) => {
            const dateObj = dateUtils.toDayjs(point.period_start)
            let timeFormat
            if (period === '12h' || period === '24h' || (showCustomRange && backendPeriod === Period.hour)) {
              timeFormat = dateObj.format('HH:mm')
            } else {
              timeFormat = dateObj.format('MM/DD')
            }
            const usageInGB = point.total_traffic / (1024 * 1024 * 1024)
            return {
              time: timeFormat,
              usage: parseFloat(usageInGB.toFixed(2)),
              _period_start: point.period_start,
              local_period_start: dateObj.toISOString(),
            }
          })
        const from = dateUtils.toDayjs((start as Date) || new Date(0))
        const to = dateUtils.toDayjs((end as Date) || new Date(0))
        filtered = filtered.filter((point: any) => {
          const pointTime = dateUtils.toDayjs(point.period_start)
          return (pointTime.isSame(from) || pointTime.isAfter(from)) && (pointTime.isSame(to) || pointTime.isBefore(to))
        })
      } else if (showCustomRange && customRange?.from && customRange?.to) {
        filtered = filtered.filter((point: any) => {
          if (!customRange.from || !customRange.to) return false
          const dateObj = dateUtils.toDayjs(point.period_start)
          return dateObj.isAfter(dateUtils.toDayjs(customRange.from).subtract(1, 'minute')) && dateObj.isBefore(dateUtils.toDayjs(customRange.to).add(1, 'minute'))
        })
      }
      return filtered.map((point: any) => {
        const dateObj = dateUtils.toDayjs(point.period_start)
        let timeFormat
        if (period === '12h' || period === '24h' || (showCustomRange && backendPeriod === Period.hour)) {
          timeFormat = dateObj.format('HH:mm')
        } else {
          timeFormat = dateObj.format('MM/DD')
        }
        const usageInGB = point.total_traffic / (1024 * 1024 * 1024)
        return {
          time: timeFormat,
          usage: parseFloat(usageInGB.toFixed(2)),
          _period_start: point.period_start,
          local_period_start: dateObj.toISOString(),
        }
      })
    }
  }, [data, period, showCustomRange, customRange, backendPeriod, start, end, selectedNodeId, nodeList])

  // Update chartData state when processedChartData changes
  useEffect(() => {
    setChartData(processedChartData)
  }, [processedChartData])

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

  // Handlers
  const handleCustomRangeChange = useCallback((range: DateRange | undefined) => {
    setCustomRange(range)
    if (range?.from && range?.to) {
      setShowCustomRange(true)
      const diffHours = (range.to.getTime() - range.from.getTime()) / (1000 * 60 * 60)
      if (diffHours <= 1) setPeriod('1h')
      else if (diffHours <= 12) setPeriod('12h')
      else if (diffHours <= 24) setPeriod('24h')
      else if (diffHours <= 72) setPeriod('3d')
      else setPeriod('1w')
    }
  }, [])

  const handleTimeSelect = useCallback((newPeriod: PeriodKey) => {
    setPeriod(newPeriod)
    setShowCustomRange(false)
    setCustomRange(undefined)
  }, [])

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl p-0.5">
        <DialogTitle className="sr-only">{t('usersTable.usageChart', { defaultValue: 'Usage Chart' })}</DialogTitle>
        <DialogDescription className="sr-only">
          Showing total usage for the selected period
        </DialogDescription>
        <Card className="w-full border-none shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-center text-lg sm:text-xl">{t('usersTable.usageChart', { defaultValue: 'Usage Chart' })}</CardTitle>
            <CardDescription className="flex flex-col items-center gap-4 pt-4">
              <div className="flex w-full items-center justify-center gap-2">
                <TimeSelector selectedTime={period} setSelectedTime={handleTimeSelect as any} />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('usersTable.selectCustomRange', { defaultValue: 'Select custom range' })}
                  className={showCustomRange ? 'text-primary' : ''}
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
                      {nodes?.map(node => (
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
                <div className="flex h-60 w-full items-center justify-center">
                  <div className="h-40 w-full animate-pulse rounded-lg" />
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
                        if (data && data.activePayload && data.activePayload.length > 0 && processedChartData) {
                          const clickedData = data.activePayload[0].payload
                          const activeNodesCount = Object.keys(clickedData).filter(
                            key => !key.startsWith('_') && key !== 'time' && key !== '_period_start' && key !== 'usage' && (clickedData[key] || 0) > 0,
                          ).length
                          // Open modal if there are active nodes (regardless of count)
                          if (activeNodesCount > 0) {
                            // Find the index of the clicked data point
                            const clickedIndex = processedChartData.findIndex(item => item._period_start === clickedData._period_start)
                            setCurrentDataIndex(clickedIndex >= 0 ? clickedIndex : 0)
                            setSelectedData(clickedData)
                            setModalOpen(true)
                          }
                        }
                      }}
                    >
                      <CartesianGrid direction={'ltr'} vertical={false} />
                      <XAxis direction={'ltr'} dataKey="time" tickLine={false} tickMargin={10} axisLine={false} minTickGap={5} />
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
                      <ChartTooltip cursor={false} content={<CustomBarTooltip chartConfig={chartConfig} dir={dir} period={currentPeriod} />} />
                      {selectedNodeId === undefined && is_sudo ? (
                        // All nodes selected for sudo admins - render stacked bars
                        nodeList.map((node, idx) => (
                          <Bar
                            key={node.id}
                            dataKey={node.name}
                            stackId="a"
                            fill={chartConfig[node.name]?.color || `hsl(var(--chart-${(idx % 5) + 1}))`}
                            radius={nodeList.length === 1 ? [4, 4, 4, 4] : idx === 0 ? [0, 0, 4, 4] : idx === nodeList.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                            cursor="pointer"
                          />
                        ))
                      ) : (
                        // Single node selected OR non-sudo admin aggregated data - render single bar
                        <Bar dataKey="usage" radius={6} cursor="pointer">
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
        period={currentPeriod}
        allChartData={processedChartData || []}
        currentIndex={currentDataIndex}
        onNavigate={handleModalNavigate}
        hideUplinkDownlink={true}
      />
    </Dialog>
  )
}

export default UsageModal
