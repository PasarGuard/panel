import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Card, CardContent } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { useTranslation } from 'react-i18next'
import { formatBytes, gbToBytes } from '@/utils/formatByte'
import { Upload, Download, Calendar, Activity, ChevronLeft, ChevronRight } from 'lucide-react'
import { dateUtils } from '@/utils/dateFormatter'
import useDirDetection from '@/hooks/use-dir-detection'

interface NodeStatsModalProps {
  open: boolean
  onClose: () => void
  data: any
  chartConfig: any
  period: string
  allChartData?: any[]
  currentIndex?: number
  onNavigate?: (index: number) => void
  hideUplinkDownlink?: boolean
}

const NodeStatsModal = ({ open, onClose, data, chartConfig, period, allChartData = [], currentIndex = 0, onNavigate, hideUplinkDownlink = false }: NodeStatsModalProps) => {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()

  if (!data) return null

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
      } else if (period === 'day') {
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
        })
        .replace(',', '')
    }
  }

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
  // Calculate total usage - if uplink/downlink are available use them, otherwise convert usage from GB to bytes
  const totalUsage = totalUplink + totalDownlink > 0 
    ? totalUplink + totalDownlink 
    : activeNodes.reduce((sum, node) => sum + (gbToBytes(node.usage) || 0), 0)

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md sm:max-w-lg md:max-w-xl" dir={dir}>
        <DialogHeader>
          <div className="flex flex-col items-center gap-3">
            <DialogTitle className={`flex items-center gap-2 text-sm sm:text-base`}>
              <Activity className="h-4 w-4 sm:h-5 sm:w-5" />
              {t('statistics.nodeStats', { defaultValue: 'Node Statistics' })}
            </DialogTitle>
            {hasNavigation && (
              <div className="flex items-center gap-1">
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

        <Card className="border-none bg-transparent shadow-none">
          <CardContent className="space-y-4 p-0">
            {/* Date and Total Usage */}
            <div className={`flex items-center justify-between ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
              <div className={`flex items-center gap-2 ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
                <Calendar className="h-3 w-3 text-muted-foreground sm:h-4 sm:w-4" />
                <span className="max-w-[120px] truncate text-xs font-medium sm:max-w-none sm:text-sm" dir="ltr">
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

              <div dir="ltr" className="grid max-h-80 gap-2 overflow-y-auto sm:gap-3">
                {activeNodes.map(node => (
                  <div key={node.name} className={`flex items-center justify-between rounded-lg border p-2 sm:p-3`}>
                    <div className={`flex min-w-0 flex-1 items-center gap-2 sm:gap-3`}>
                      <div className="h-2 w-2 flex-shrink-0 rounded-full sm:h-3 sm:w-3" style={{ backgroundColor: node.color }} />
                      <div className="min-w-0 flex-1">
                        <div className={`truncate text-xs font-medium sm:text-sm`}>{node.name}</div>
                        <div className={`text-xs text-muted-foreground`}>{node.usage.toFixed(2)} GB</div>
                      </div>
                    </div>

                    {!hideUplinkDownlink && (
                      <div className={`flex items-center gap-1 text-xs sm:gap-2`}>
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

            {/* Summary */}
            <div className={`text-xs leading-tight text-muted-foreground ${isRTL ? 'text-right' : 'text-left'}`}>
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
