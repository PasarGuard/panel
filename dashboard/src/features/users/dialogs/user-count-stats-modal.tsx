import { Cell, Pie, PieChart, TooltipProps } from 'recharts'
import { useTranslation } from 'react-i18next'
import { Activity, Calendar, ChevronLeft, ChevronRight } from 'lucide-react'

import useDirDetection from '@/hooks/use-dir-detection'
import { Period } from '@/service/api'
import { formatTooltipDate } from '@/utils/chart-period-utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { type ChartConfig, ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export type UserCountStatsModalData = {
  time: string
  _period_start: string
  [key: string]: string | number
}

export type UserCountStatsModalSeries = {
  key: string
  label: string
  color: string
}

type UserCountStatsModalProps = {
  open: boolean
  onClose: () => void
  data: UserCountStatsModalData | null
  period: Period
  metricLabel: string
  series: UserCountStatsModalSeries[]
  allChartData?: UserCountStatsModalData[]
  currentIndex?: number
  onNavigate?: (index: number) => void
}

type PieDataPoint = {
  name: string
  count: number
  percentage: number
  fill: string
}

function CountDistributionTooltip({ active, payload }: TooltipProps<number, string>) {
  const { t } = useTranslation()

  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as PieDataPoint

  return (
    <div className="border-border bg-background/95 rounded-lg border p-2 text-xs shadow-sm backdrop-blur-sm">
      <div className="mb-1 flex items-center gap-1.5">
        <div className="border-border/20 h-2.5 w-2.5 rounded-full border" style={{ backgroundColor: data.fill }} />
        <span className="text-foreground font-medium">{data.name}</span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.totalUsers', { defaultValue: 'Total' })}</span>
        <span dir="ltr" className="text-foreground font-mono font-semibold">
          {data.count.toLocaleString()}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-3">
        <span className="text-muted-foreground">{t('statistics.percentage', { defaultValue: 'Percentage' })}</span>
        <span dir="ltr" className="text-foreground font-mono">{`${data.percentage.toFixed(1)}%`}</span>
      </div>
    </div>
  )
}

export default function UserCountStatsModal({ open, onClose, data, period, metricLabel, series, allChartData = [], currentIndex = 0, onNavigate }: UserCountStatsModalProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()

  if (!data) return null

  const isRTL = dir === 'rtl'
  const formattedDate = data._period_start ? formatTooltipDate(data._period_start, period, i18n.language) : data.time
  const rows = series
    .map(item => ({
      ...item,
      count: Number(data[item.key] || 0),
    }))
    .filter(item => item.count > 0)
    .sort((a, b) => b.count - a.count)
  const total = rows.reduce((sum, item) => sum + item.count, 0)
  const pieData: PieDataPoint[] = rows.map(item => ({
    name: item.label,
    count: item.count,
    percentage: total > 0 ? (item.count * 100) / total : 0,
    fill: item.color,
  }))
  const pieChartConfig = pieData.reduce<ChartConfig>((acc, item) => {
    acc[item.name] = { label: item.name, color: item.fill }
    return acc
  }, {})
  const piePaddingAngle = pieData.length > 1 ? 1 : 0

  const hasNavigation = allChartData.length > 1
  const canGoPrevious = hasNavigation && currentIndex > 0
  const canGoNext = hasNavigation && currentIndex < allChartData.length - 1

  const handlePrevious = () => {
    if (canGoPrevious) onNavigate?.(currentIndex - 1)
  }

  const handleNext = () => {
    if (canGoNext) onNavigate?.(currentIndex + 1)
  }

  const handleLeftButton = isRTL ? handleNext : handlePrevious
  const handleRightButton = isRTL ? handlePrevious : handleNext
  const canGoLeft = isRTL ? canGoNext : canGoPrevious
  const canGoRight = isRTL ? canGoPrevious : canGoNext

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="flex max-h-[95dvh] w-[96vw] max-w-md flex-col overflow-hidden sm:max-w-2xl md:max-w-3xl" dir={dir}>
        <DialogHeader>
          <div className="flex flex-col items-start gap-3">
            <DialogTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 sm:h-5 sm:w-5" />
              {t('statistics.userCountDetails', { defaultValue: 'User Count Details' })}
            </DialogTitle>
            {hasNavigation && (
              <div className="flex w-full items-center justify-center gap-1">
                <Button variant="outline" size="sm" onClick={handleLeftButton} disabled={!canGoLeft} className="h-8 w-8 p-0">
                  <ChevronLeft className={`h-4 w-4 ${isRTL ? 'rotate-180' : ''}`} />
                </Button>
                <span dir="ltr" className="text-muted-foreground min-w-[60px] text-center text-sm font-medium">
                  {currentIndex + 1} / {allChartData.length}
                </span>
                <Button variant="outline" size="sm" onClick={handleRightButton} disabled={!canGoRight} className="h-8 w-8 p-0">
                  <ChevronRight className={`h-4 w-4 ${isRTL ? 'rotate-180' : ''}`} />
                </Button>
              </div>
            )}
          </div>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-3 overflow-x-hidden overflow-y-auto pr-1 sm:space-y-4">
          <div className={`flex items-center justify-between gap-3 ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
            <div className={`flex min-w-0 items-center gap-2 ${isRTL ? 'flex-row-reverse' : 'flex-row'}`}>
              <Calendar className="text-muted-foreground h-3 w-3 shrink-0 sm:h-4 sm:w-4" />
              <span className="truncate text-xs font-medium sm:text-sm" dir="ltr">
                {formattedDate}
              </span>
            </div>
            <Badge dir="ltr" variant="secondary" className="px-2 py-1 font-mono text-xs sm:text-sm">
              {total.toLocaleString()}
            </Badge>
          </div>

          <div className="text-muted-foreground text-xs font-medium">{metricLabel}</div>

          {pieData.length > 0 ? (
            <div className="flex flex-col gap-3 md:flex-row md:items-start">
              <div className="flex justify-center md:w-[200px] md:flex-shrink-0">
                <ChartContainer config={pieChartConfig} className="h-[132px] w-[132px] sm:h-[160px] sm:w-[160px] md:h-[180px] md:w-[180px] [&_.recharts-text]:fill-transparent">
                  <PieChart>
                    <ChartTooltip content={<CountDistributionTooltip />} />
                    <Pie data={pieData} dataKey="count" nameKey="name" innerRadius="58%" outerRadius="96%" paddingAngle={piePaddingAngle} strokeWidth={1.5}>
                      {pieData.map(item => (
                        <Cell key={item.name} fill={item.fill} />
                      ))}
                    </Pie>
                  </PieChart>
                </ChartContainer>
              </div>

              <div dir="ltr" className="grid max-h-[36dvh] min-w-0 flex-1 gap-2 overflow-x-hidden overflow-y-auto sm:gap-3 md:max-h-80">
                {pieData.map(item => (
                  <div key={item.name} className="flex items-center justify-between gap-3 rounded-lg border p-2 sm:p-3">
                    <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
                      <div className="h-2 w-2 shrink-0 rounded-full sm:h-3 sm:w-3" style={{ backgroundColor: item.fill }} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span dir="ltr" className="text-foreground font-mono text-[10px] font-bold sm:text-xs">
                            {item.percentage.toFixed(1)}%
                          </span>
                          <div className="truncate text-xs font-medium break-all sm:text-sm">{item.name}</div>
                        </div>
                      </div>
                    </div>
                    <span dir="ltr" className="shrink-0 font-mono text-xs font-semibold sm:text-sm">
                      {item.count.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground rounded-md border border-dashed p-3 text-center text-xs">{t('statistics.noDataInRange', { defaultValue: 'No data in selected range' })}</div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
