import { useEffect, useState, useMemo, useCallback } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import { DateRange } from 'react-day-picker'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { getUsage, Period, type NodeUsageStat } from '@/service/api'
import { formatBytes } from '@/utils/formatByte'
import { Skeleton } from '@/components/ui/skeleton'
import { TimeRangeSelector } from '@/components/common/TimeRangeSelector'
import { EmptyState } from './EmptyState'
import { TrendingUp, Upload, Download, Calendar } from 'lucide-react'
import { dateUtils } from '@/utils/dateFormatter'
import { TooltipProps } from 'recharts'
import { useGetNodes, NodeResponse } from '@/service/api'
import { useTheme } from '@/components/theme-provider'
import TimeSelector from './TimeSelector'


// Helper function to determine period (copied from CostumeBarChart)
const getPeriodFromDateRange = (range?: DateRange): Period => {
  if (!range?.from || !range?.to) {
    return Period.hour // Default to hour if no range
  }
  const diffTime = Math.abs(range.to.getTime() - range.from.getTime())
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
  if (diffDays <= 2) {
    return Period.hour
  }
  return Period.day
}

function CustomTooltip({ active, payload, chartConfig, dir, period }: TooltipProps<any, any> & { chartConfig?: ChartConfig, dir: string, period?: string }) {
  const { t, i18n } = useTranslation()
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
      if (period === 'day' && isToday) {
        formattedDate = new Date().toLocaleString('fa-IR', {
          year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
        }).replace(',', '')
      } else if (period === 'day') {
        const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
        formattedDate = localDate.toLocaleString('fa-IR', {
          year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
        }).replace(',', '')
      } else {
        // hourly or other: use actual time from data
        formattedDate = d.toDate().toLocaleString('fa-IR', {
          year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
        }).replace(',', '')
      }
    } catch {
      formattedDate = d.format('YYYY/MM/DD HH:mm')
    }
  } else {
    if (period === 'day' && isToday) {
      const now = new Date()
      formattedDate = now.toLocaleString('en-US', {
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
      }).replace(',', '')
    } else if (period === 'day') {
      const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
      formattedDate = localDate.toLocaleString('en-US', {
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
      }).replace(',', '')
    } else {
      // hourly or other: use actual time from data
      formattedDate = d.toDate().toLocaleString('en-US', {
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
      }).replace(',', '')
    }
  }

  // Get node color from chart config
  const getNodeColor = (nodeName: string) => {
    return chartConfig?.[nodeName]?.color || 'hsl(var(--chart-1))'
  }

  const isRTL = dir === 'rtl'

  return (
    <div
      className={`rounded border border-border bg-background shadow min-w-[140px] text-[11px] p-2 ${isRTL ? 'text-right' : 'text-left'}`}
      dir={isRTL ? 'rtl' : 'ltr'}
    >
      <div className={`mb-1.5 font-semibold text-[11px] opacity-70 ${isRTL ? 'text-right' : 'text-center'}`}>
        <span dir="ltr" className="inline-block">{formattedDate}</span>
      </div>
      <div className={`mb-1.5 text-muted-foreground text-[11px] ${isRTL ? 'text-right' : 'text-center'}`}>
        <span>{t('statistics.totalUsage', { defaultValue: 'Total' })}: </span>
        <span dir="ltr" className="inline-block font-mono">
          {Object.keys(data).reduce((sum, key) => {
            if (key.startsWith('_uplink_') || key.startsWith('_downlink_') || key === 'time' || key === '_period_start') return sum
            return sum + (data[key] || 0)
          }, 0).toFixed(2)} GB
        </span>
      </div>
      <div className={`grid gap-1 ${Object.keys(data).filter(key => !key.startsWith('_') && key !== 'time' && key !== '_period_start').length > 6 ? 'grid-cols-2' : 'grid-cols-1'}`}>
        {Object.keys(data).map(key => {
          if (key.startsWith('_uplink_') || key.startsWith('_downlink_') || key === 'time' || key === '_period_start') return null
          const nodeName = key
          const uplinkKey = `_uplink_${nodeName}`
          const downlinkKey = `_downlink_${nodeName}`
          const usage = data[key] || 0
          if (usage === 0) return null
          return (
            <div key={nodeName} className={`flex flex-col gap-0.5 ${isRTL ? 'items-end' : 'items-start'}`}>
              <span className={`font-semibold text-[11px] flex items-center gap-1 ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <div 
                  className="w-2 h-2 rounded-full flex-shrink-0" 
                  style={{ backgroundColor: getNodeColor(nodeName) }}
                />
                <span>{nodeName}</span>
              </span>
              <span className={`flex items-center gap-1 text-muted-foreground text-[10px] ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <Upload className="h-3 w-3 flex-shrink-0" />
                <span dir="ltr" className="inline-block font-mono">{formatBytes(data[uplinkKey] || 0)}</span>
                <span className={`opacity-60 ${isRTL ? 'mx-1' : 'mx-1'}`}>|</span>
                <Download className="h-3 w-3 flex-shrink-0" />
                <span dir="ltr" className="inline-block font-mono">{formatBytes(data[downlinkKey] || 0)}</span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function AllNodesStackedBarChart() {
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined)
  const [selectedTime, setSelectedTime] = useState<string>('1w')
  const [showCustomRange, setShowCustomRange] = useState(false)
  const [chartData, setChartData] = useState<any[] | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [totalUsage, setTotalUsage] = useState('0')

  const { t } = useTranslation()
  const dir = useDirDetection()
  const { data: nodesData } = useGetNodes(undefined, { query: { enabled: true } })
  const { resolvedTheme } = useTheme()

  // Build color palette for nodes
  const nodeList: NodeResponse[] = useMemo(() => (Array.isArray(nodesData) ? nodesData : []), [nodesData])
  

  // Function to generate distinct colors based on theme
  const generateDistinctColor = useCallback((index: number, _totalNodes: number, isDark: boolean): string => {
    // Define a more distinct color palette with better contrast
    const distinctHues = [
      0,    // Red
      30,   // Orange
      60,   // Yellow
      120,  // Green
      180,  // Cyan
      210,  // Blue
      240,  // Indigo
      270,  // Purple
      300,  // Magenta
      330,  // Pink
      15,   // Red-orange
      45,   // Yellow-orange
      75,   // Yellow-green
      150,  // Green-cyan
      200,  // Cyan-blue
      225,  // Blue-indigo
      255,  // Indigo-purple
      285,  // Purple-magenta
      315,  // Magenta-pink
      345,  // Pink-red
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

  useEffect(() => {
    let isCancelled = false
    let timeoutId: NodeJS.Timeout
    
    const fetchUsageData = async () => {
      if (!dateRange?.from || !dateRange?.to) {
        setChartData(null)
        setTotalUsage('0')
        return
      }
      setIsLoading(true)
      setError(null)
      try {
        const startDate = dateRange.from
        const endDate = dateRange.to
        const period = getPeriodFromDateRange(dateRange)
        
        // Always use end of day for daily period to avoid extra bars
        const endTime = period === Period.day ? dateUtils.toDayjs(endDate).endOf('day').toISOString() : new Date().toISOString()
        
        const params: Parameters<typeof getUsage>[0] = {
          period: period,
          start: startDate.toISOString(),
          end: endTime,
          group_by_node: true,
        }
        const response = await getUsage(params)
        
        // Check if component is still mounted
        if (isCancelled) return

        // API response and nodes list logged
        
        // Handle the response format exactly like CostumeBarChart
        let statsByNode: Record<string, NodeUsageStat[]> = {}
        if (response && response.stats) {
          if (typeof response.stats === 'object' && !Array.isArray(response.stats)) {
            // This is the expected format when no node_id is provided
            statsByNode = response.stats
          } else if (Array.isArray(response.stats)) {
            // fallback: old format - not expected for all nodes
            console.warn('Unexpected array format for all nodes usage')
          }
        }

        // Stats by node processed
        
        // Build a map from node id to node name for quick lookup
        const nodeIdToName = nodeList.reduce((acc, node) => {
          acc[node.id] = node.name
          return acc
        }, {} as Record<string, string>)

        // Node ID to name mapping created
        
        // Check if we have data for individual nodes or aggregated data
        const hasIndividualNodeData = Object.keys(statsByNode).some(key => key !== '-1')
        
        if (!hasIndividualNodeData && statsByNode['-1']) {
          // API returned aggregated data for all nodes combined
          // Using aggregated data for all nodes
          const aggregatedStats = statsByNode['-1']
          
          if (aggregatedStats.length > 0) {
            const data = aggregatedStats.map((point: NodeUsageStat) => {
              const d = dateUtils.toDayjs(point.period_start)
              let timeFormat
              if (period === Period.hour) {
                timeFormat = d.format('HH:mm')
              } else {
                timeFormat = d.format('MM/DD')
              }
              const usageInGB = (point.uplink + point.downlink) / (1024 * 1024 * 1024)
              
              // Create entry with all nodes having the same usage (aggregated)
              const entry: any = { 
                time: timeFormat,
                _period_start: point.period_start
              }
              nodeList.forEach((node) => {
                // Distribute usage equally among nodes or show as total
                const nodeUsage = parseFloat((usageInGB / nodeList.length).toFixed(2))
                entry[node.name] = nodeUsage
                // Store uplink and downlink for tooltip (distributed equally)
                entry[`_uplink_${node.name}`] = point.uplink / nodeList.length
                entry[`_downlink_${node.name}`] = point.downlink / nodeList.length
              })
              return entry
            })

            // Final chart data (aggregated) processed
            if (!isCancelled) {
              setChartData(data)
              
              // Calculate total usage
              const total = aggregatedStats.reduce((sum: number, point: NodeUsageStat) => sum + point.uplink + point.downlink, 0)
              const formattedTotal = formatBytes(total, 2)
              if (typeof formattedTotal === 'string') setTotalUsage(formattedTotal)
            }
          } else {
            setChartData(null)
            setTotalUsage('0')
          }
        } else {
          // Handle individual node data (existing logic)
          // Build a set of all period_start values
          const allPeriods = new Set<string>()
          Object.values(statsByNode).forEach((arr) => arr.forEach((stat) => allPeriods.add(stat.period_start)))
          // Sort periods
          const sortedPeriods = Array.from(allPeriods).sort()

          // All periods and period type processed
          
          if (sortedPeriods.length > 0) {
            // Build chart data: [{ time, [nodeName]: usage, ... }]
            const data = sortedPeriods.map((periodStart) => {
              const d = dateUtils.toDayjs(periodStart)
              let timeFormat
              if (period === Period.hour) {
                timeFormat = d.format('HH:mm')
              } else {
                timeFormat = d.format('MM/DD')
              }
              const entry: any = { 
                time: timeFormat,
                _period_start: periodStart
              }
              
              Object.entries(statsByNode).forEach(([nodeId, statsArr]) => {
                if (nodeId === '-1') return // Skip aggregated data
                const nodeName = nodeIdToName[nodeId]
                if (!nodeName) {
                  console.warn('No node name found for ID:', nodeId)
                  return
                }
                const nodeStats = statsArr.find((s) => s.period_start === periodStart)
                if (nodeStats) {
                  const usageInGB = (nodeStats.uplink + nodeStats.downlink) / (1024 * 1024 * 1024)
                  entry[nodeName] = parseFloat(usageInGB.toFixed(2))
                  // Store uplink and downlink for tooltip
                  entry[`_uplink_${nodeName}`] = nodeStats.uplink
                  entry[`_downlink_${nodeName}`] = nodeStats.downlink
                  // Node usage processed
                } else {
                  entry[nodeName] = 0
                  entry[`_uplink_${nodeName}`] = 0
                  entry[`_downlink_${nodeName}`] = 0
                }
              })
              return entry
            })

            // Final chart data processed
            if (!isCancelled) {
              setChartData(data)
              
              // Calculate total usage
              let total = 0
              Object.values(statsByNode).forEach((arr) => arr.forEach((stat) => { total += stat.uplink + stat.downlink }))
              const formattedTotal = formatBytes(total, 2)
              if (typeof formattedTotal === 'string') setTotalUsage(formattedTotal)
            }
          } else {
            // No periods found, setting empty data
            setChartData(null)
            setTotalUsage('0')
          }
        }
      } catch (err) {
        setError(err as Error)
        setChartData(null)
        setTotalUsage('0')
        console.error('Error fetching usage data:', err)
      } finally {
        if (!isCancelled) {
          setIsLoading(false)
        }
      }
    }
    
    // Debounce the API call to prevent excessive requests during zoom
    timeoutId = setTimeout(() => {
      fetchUsageData()
    }, 300)
    
    return () => {
      isCancelled = true
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }, [dateRange, nodeList])

  // Add effect to update dateRange when selectedTime changes
  useEffect(() => {
    if (!showCustomRange) {
      const now = new Date()
      let from: Date | undefined
      if (selectedTime === '12h') {
        from = new Date(now.getTime() - 12 * 60 * 60 * 1000)
      } else if (selectedTime === '24h') {
        from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
      } else if (selectedTime === '3d') {
        from = new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000)
      } else if (selectedTime === '1w') {
        from = new Date(now.getTime() - 6 * 24 * 60 * 60 * 1000)
      }
      if (from) {
        // For 1w and 3d, set to end of current day to avoid extra bar
        const to = (selectedTime === '1w' || selectedTime === '3d') ? dateUtils.toDayjs(now).endOf('day').toDate() : now
        setDateRange({ from, to })
      }
    }
  }, [selectedTime, showCustomRange])

  return (
    <Card>
      <CardHeader className="flex flex-col items-stretch space-y-0 border-b p-0 sm:flex-row">
        <div className="flex flex-1 flex-col sm:flex-row gap-1 px-6 py-6 sm:py-6 border-b">
          <div className="flex flex-1 flex-col justify-center align-middle gap-1 px-1 py-1">
            <CardTitle>{t('statistics.trafficUsage')}</CardTitle>
            <CardDescription>{t('statistics.trafficUsageDescription')}</CardDescription>
          </div>
          <div className="px-1 py-1 flex justify-center align-middle flex-col gap-2">
            <div className="flex gap-2 items-center">
              {showCustomRange ? (
                <TimeRangeSelector onRangeChange={range => { setDateRange(range); setShowCustomRange(true); }} initialRange={dateRange} />
              ) : (
                <TimeSelector selectedTime={selectedTime} setSelectedTime={v => { setSelectedTime(v); setShowCustomRange(false); }} />
              )}
              <button type="button" aria-label="Custom Range" className={`rounded p-1 border ${showCustomRange ? 'bg-muted' : ''}`} onClick={() => setShowCustomRange(v => !v)}>
                <Calendar className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
        <div className="sm:border-l p-6 m-0 flex flex-col justify-center px-4 ">
          <span className="text-muted-foreground text-xs sm:text-sm">{t('statistics.usageDuringPeriod')}</span>
          <span dir='ltr' className="text-foreground text-lg flex justify-center">{isLoading ? <Skeleton className="h-5 w-20" /> : totalUsage}</span>
        </div>
      </CardHeader>
      <CardContent dir={dir} className="pt-8">
        {isLoading ? (
          <div className="max-h-[400px] min-h-[200px] w-full flex items-center justify-center">
            <Skeleton className="h-[300px] w-full" />
          </div>
        ) : error ? (
          <EmptyState type="error" className="max-h-[400px] min-h-[200px]" />
        ) : !dateRange ? (
          <EmptyState 
            type="no-data" 
            title={t('statistics.selectTimeRange')}
            description={t('statistics.selectTimeRangeDescription')}
            icon={<TrendingUp className="h-12 w-12 text-muted-foreground/50" />} 
            className="max-h-[400px] min-h-[200px]" 
          />
        ) : (
          <div className="w-full max-w-7xl mx-auto">
            <ChartContainer 
              dir={'ltr'} 
              config={chartConfig} 
              className="max-h-[400px] min-h-[200px] w-full"
            >
              {chartData && chartData.length > 0 ? (
                <BarChart 
                  accessibilityLayer 
                  data={chartData}
                  margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
                >
                  <CartesianGrid direction={'ltr'} vertical={false} />
                  <XAxis 
                    direction={'ltr'} 
                    dataKey="time" 
                    tickLine={false} 
                    tickMargin={10} 
                    axisLine={false} 
                    minTickGap={5}
                  />
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
                  {/* When using ChartTooltip, pass period as a prop */}
                  <ChartTooltip cursor={false} content={<CustomTooltip chartConfig={chartConfig} dir={dir} period={getPeriodFromDateRange(dateRange)} />} />
                  {nodeList.map((node, idx) => (
                    <Bar
                      key={node.id}
                      dataKey={node.name}
                      stackId="a"
                      fill={chartConfig[node.name]?.color || `hsl(var(--chart-${(idx % 5) + 1}))`}
                      radius={nodeList.length === 1 ? [4, 4, 4, 4] : idx === 0 ? [0, 0, 4, 4] : idx === nodeList.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                    />
                  ))}
                </BarChart>
              ) : (
                <EmptyState 
                  type="no-data" 
                  title={t('statistics.noDataInRange')}
                  description={t('statistics.noDataInRangeDescription')}
                  className="max-h-[400px] min-h-[200px]" 
                />
              )}
            </ChartContainer>
            {/* Separate scrollable legend */}
            {chartData && chartData.length > 0 && (
              <div className="overflow-x-auto pt-3">
                <div className="flex items-center justify-center gap-4 min-w-max">
                  {nodeList.map((node) => {
                    const itemConfig = chartConfig[node.name]
                    return (
                      <div key={node.id} className="flex items-center gap-1.5 [&>svg]:h-3 [&>svg]:w-3 [&>svg]:text-muted-foreground">
                        <div
                          className="h-2 w-2 shrink-0 rounded-[2px]"
                          style={{
                            backgroundColor: itemConfig?.color || 'hsl(var(--chart-1))',
                          }}
                        />
                        <span className="whitespace-nowrap text-xs">{node.name}</span>
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
  )
} 