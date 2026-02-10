import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Card, CardContent } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { type ChartConfig, ChartContainer, ChartTooltip } from '../ui/chart'
import { useTranslation } from 'react-i18next'
import { formatBytes, gbToBytes } from '@/utils/formatByte'
import { Upload, Download, Calendar, Activity, ChevronLeft, ChevronRight } from 'lucide-react'
import { Period } from '@/service/api'
import useDirDetection from '@/hooks/use-dir-detection'
import { Cell, Pie, PieChart } from 'recharts'
import { formatTooltipDate } from '@/utils/chart-period-utils'

interface NodeStatsModalProps {
  open: boolean
  onClose: () => void
  data: any
  chartConfig: any
  period: Period
  allChartData?: any[]
  currentIndex?: number
  onNavigate?: (index: number) => void
  hideUplinkDownlink?: boolean
}

interface NodeTrafficTooltipProps {
  active?: boolean
  payload?: Array<{
    payload: {
      name: string
      bytes: number
      percentage: number
      fill: string
    }
  }>
}

function NodeTrafficTooltip({ active, payload }: NodeTrafficTooltipProps) {
  const { t } = useTranslation()

  if (!active || !payload?.length) {
    return null
  }

  const point = payload[0].payload

  return (
    <div className="rounded-lg border bg-background/95 p-2 shadow-sm backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <div className="h-2.5 w-2.5 rounded-full border border-border/20" style={{ backgroundColor: point.fill }} />
        <span className="text-xs font-medium text-foreground">{point.name}</span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-3 text-xs">
        <span className="text-muted-foreground">{t('statistics.totalUsage', { defaultValue: 'Total Usage' })}</span>
        <span dir="ltr" className="font-mono font-semibold text-foreground">
          {formatBytes(point.bytes)}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-3 text-xs">
        <span className="text-muted-foreground">{t('statistics.percentage', { defaultValue: 'Percentage' })}</span>
        <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
          {point.percentage.toFixed(1)}%
        </Badge>
      </div>
    </div>
  )
}

const NodeStatsModal = ({ open, onClose, data, chartConfig, period, allChartData = [], currentIndex = 0, onNavigate, hideUplinkDownlink = false }: NodeStatsModalProps) => {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()

  if (!data) return null

  const formattedDate = data._period_start ? formatTooltipDate(data._period_start, period, i18n.language) : ''

  const isRTL = dir === 'rtl'

  // Navigation logic
  const hasNavigation = allChartData.length > 1
  const canGoPrevious = hasNavigation && currentIndex > 0
  const canGoNext = hasNavigation && currentIndex < allChartData.length - 1

  const handlePrevious = () => {
    if (canGoPrevious && onNavigate) {
      onNavigate(currentIndex - 1)
    }
  }

  const handleNext = () => {
    if (canGoNext && onNavigate) {
      onNavigate(currentIndex + 1)
    }
  }

  // In RTL, swap the button actions for intuitive navigation
  const handleLeftButton = isRTL ? handleNext : handlePrevious
  const handleRightButton = isRTL ? handlePrevious : handleNext
  const canGoLeft = isRTL ? canGoNext : canGoPrevious
  const canGoRight = isRTL ? canGoPrevious : canGoNext

  // Get nodes with usage > 0
  const activeNodes = Object.keys(data)
    .filter(key => !key.startsWith('_') && key !== 'time' && key !== '_period_start' && (data[key] || 0) > 0)
    .map(nodeName => ({
      name: nodeName,
      usage: data[nodeName] || 0,
      uplink: data[`_uplink_${nodeName}`] || 0,
      downlink: data[`_downlink_${nodeName}`] || 0,
      color: chartConfig?.[nodeName]?.color || 'hsl(var(--chart-1))',
    }))
    .sort((a, b) => b.usage - a.usage) // Sort by usage descending

  // Calculate total uplink and downlink from activeNodes
  const totalUplink = activeNodes.reduce((sum, node) => sum + (node.uplink || 0), 0)
  const totalDownlink = activeNodes.reduce((sum, node) => sum + (node.downlink || 0), 0)
  const nodesWithBytes = activeNodes.map(node => {
    const directionalTotal = Number(node.uplink || 0) + Number(node.downlink || 0)
    const bytes = directionalTotal > 0 ? directionalTotal : Number(gbToBytes(node.usage) || 0)
    return { ...node, bytes }
  })
  const totalUsage = nodesWithBytes.reduce((sum, node) => sum + node.bytes, 0)
  const nodesWithDistribution = nodesWithBytes.map(node => ({
    ...node,
    percentage: totalUsage > 0 ? (node.bytes * 100) / totalUsage : 0,
  }))
  const pieData = nodesWithDistribution.map(node => ({
    name: node.name,
    bytes: node.bytes,
    percentage: node.percentage,
    fill: node.color,
    uplink: node.uplink,
    downlink: node.downlink,
  }))
  const pieChartConfig: ChartConfig = pieData.reduce<ChartConfig>((acc, node) => {
    acc[node.name] = { label: node.name, color: node.fill }
    return acc
  }, {})
  const piePaddingAngle = pieData.length > 1 ? 1 : 0

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="flex max-h-[95dvh] w-[96vw] max-w-md flex-col overflow-hidden p-3 sm:max-w-2xl sm:p-4 md:max-w-3xl lg:max-w-4xl" dir={dir}>
        <DialogHeader className={isRTL ? 'text-right' : 'text-left'}>
          <div className="flex flex-col items-start gap-3">
            <DialogTitle className={`flex items-center gap-2 text-sm sm:text-base`}>
              <Activity className="h-4 w-4 sm:h-5 sm:w-5" />
              {t('statistics.nodeStats', { defaultValue: 'Node Statistics' })}
            </DialogTitle>
            {hasNavigation && (
              <div className="flex w-full items-center justify-center gap-1">
                <Button variant="outline" size="sm" onClick={handleLeftButton} disabled={!canGoLeft} className="h-8 w-8 p-0">
                  <ChevronLeft className={`h-4 w-4 ${isRTL ? 'rotate-180' : ''}`} />
                </Button>
                <span dir="ltr" className="min-w-[60px] text-center text-sm font-medium text-muted-foreground">
                  {currentIndex + 1} / {allChartData.length}
                </span>
                <Button variant="outline" size="sm" onClick={handleRightButton} disabled={!canGoRight} className="h-8 w-8 p-0">
                  <ChevronRight className={`h-4 w-4 ${isRTL ? 'rotate-180' : ''}`} />
                </Button>
              </div>
            )}
          </div>
        </DialogHeader>

        <Card className="min-h-0 flex-1 border-none bg-transparent shadow-none">
          <CardContent className="min-h-0 space-y-3 overflow-x-hidden overflow-y-auto p-0 pr-1 sm:space-y-4">
            {/* Date and Total Usage */}
            <div className={`flex items-center justify-between ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
              <div className={`flex items-center gap-2 ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <Calendar className="h-3 w-3 text-muted-foreground sm:h-4 sm:w-4" />
                <span className="max-w-[150px] truncate text-xs font-medium sm:max-w-none sm:text-sm" dir="ltr">
                  {formattedDate}
                </span>
              </div>
              <Badge dir="ltr" variant="secondary" className="px-2 py-1 font-mono text-xs sm:text-sm">
                {formatBytes(totalUsage)}
              </Badge>
            </div>

            {/* Total Upload/Download */}
            {!hideUplinkDownlink && (
              <div className={`flex items-center gap-2 text-xs sm:gap-3 ${isRTL ? 'flex-row-reverse justify-end' : 'flex-row justify-start'}`}>
                <div className={`flex items-center gap-1`}>
                  <Upload className="h-3 w-3 text-green-500" />
                  <span dir="ltr" className="font-mono text-muted-foreground">
                    {formatBytes(totalUplink)}
                  </span>
                </div>
                <div className={`flex items-center gap-1`}>
                  <Download className="h-3 w-3 text-blue-500" />
                  <span dir="ltr" className="font-mono text-muted-foreground">
                    {formatBytes(totalDownlink)}
                  </span>
                </div>
              </div>
            )}

            {/* Node Statistics */}
            <div className="space-y-2 sm:space-y-3">
              <h4 className={`text-xs font-semibold text-foreground sm:text-sm`}>{t('statistics.nodeTrafficDistribution', { defaultValue: 'Node Traffic Distribution' })}</h4>

              {pieData.length > 0 ? (
                <div className="flex flex-col gap-3 md:flex-row md:items-start">
                  <div className="flex justify-center md:w-[200px] md:flex-shrink-0">
                    <ChartContainer config={pieChartConfig} className="h-[132px] w-[132px] sm:h-[160px] sm:w-[160px] md:h-[180px] md:w-[180px] [&_.recharts-text]:fill-transparent">
                      <PieChart>
                        <ChartTooltip content={<NodeTrafficTooltip />} />
                        <Pie data={pieData} dataKey="bytes" nameKey="name" innerRadius="58%" outerRadius="96%" paddingAngle={piePaddingAngle} strokeWidth={1.5}>
                          {pieData.map(node => (
                            <Cell key={node.name} fill={node.fill} />
                          ))}
                        </Pie>
                      </PieChart>
                    </ChartContainer>
                  </div>

                  <div dir="ltr" className="grid max-h-[32dvh] min-w-0 flex-1 gap-2 overflow-x-hidden overflow-y-auto sm:max-h-[36dvh] sm:gap-3 md:max-h-80">
                    {nodesWithDistribution.map(node => (
                      <div key={node.name} className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2 sm:flex-nowrap sm:p-3`}>
                        <div className={`flex min-w-0 flex-1 items-center gap-2 sm:gap-3`}>
                          <div className="h-2 w-2 flex-shrink-0 rounded-full sm:h-3 sm:w-3" style={{ backgroundColor: node.color }} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span dir="ltr" className="text-[10px] font-mono font-bold text-foreground sm:text-xs">
                                {node.percentage.toFixed(1)}%
                              </span>
                              <div className={`truncate break-all text-xs font-medium sm:text-sm`}>{node.name}</div>
                            </div>
                            <div className={`text-xs text-muted-foreground`}>{formatBytes(node.bytes)}</div>
                          </div>
                        </div>

                        {!hideUplinkDownlink && (
                          <div className={`flex w-full items-center justify-end gap-1 text-xs sm:w-auto sm:gap-2`}>
                            <div className={`flex items-center gap-1`}>
                              <Upload className="h-2 w-2 text-green-500 sm:h-3 sm:w-3" />
                              <span dir="ltr" className="max-w-[60px] truncate font-mono text-xs sm:max-w-none">
                                {formatBytes(node.uplink)}
                              </span>
                            </div>
                            <div className={`flex items-center gap-1`}>
                              <Download className="h-2 w-2 text-blue-500 sm:h-3 sm:w-3" />
                              <span dir="ltr" className="max-w-[60px] truncate font-mono text-xs sm:max-w-none">
                                {formatBytes(node.downlink)}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">
                  {t('statistics.noDataInRange', { defaultValue: 'No data in selected range' })}
                </div>
              )}
            </div>

            {/* Summary */}
            <div className={`hidden text-xs leading-tight text-muted-foreground sm:block ${isRTL ? 'text-right' : 'text-left'}`}>
              {t('statistics.nodeStatsDescription', {
                defaultValue: 'Detailed traffic statistics for each node at this time period. Click on bars in the chart to view more details.',
              })}
            </div>
          </CardContent>
        </Card>
      </DialogContent>
    </Dialog>
  )
}

export default NodeStatsModal
