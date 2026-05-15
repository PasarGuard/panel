import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { Progress } from '@/components/ui/progress'
import { formatBytes } from '@/utils/formatByte'
import { NodeResponse } from '@/service/api'
import { Download, Gauge, HardDrive, Upload } from 'lucide-react'
import { statusColors } from '@/constants/UserSettings'

interface NodeUsageDisplayProps {
  node: NodeResponse
}

export default function NodeUsageDisplay({ node }: NodeUsageDisplayProps) {
  const isRTL = useDirDetection() === 'rtl'
  const uplink = node.uplink || 0
  const downlink = node.downlink || 0
  const totalUsed = uplink + downlink
  const lifetimeUplink = node.lifetime_uplink || 0
  const lifetimeDownlink = node.lifetime_downlink || 0
  const totalLifetime = lifetimeUplink + lifetimeDownlink
  const dataLimit = node.data_limit
  const isUnlimited = dataLimit === null || dataLimit === undefined || dataLimit === 0
  const progressValue = isUnlimited || !dataLimit ? 0 : Math.min((totalUsed / dataLimit) * 100, 100)

  const getProgressColor = () => {
    if (isUnlimited) return ''
    if (progressValue >= 90) return statusColors.limited.sliderColor
    if (progressValue >= 70) return statusColors.expired.sliderColor
    return statusColors.active.sliderColor
  }

  if (totalUsed === 0 && !dataLimit && totalLifetime === 0) {
    return <span className="text-xs text-muted-foreground">-</span>
  }

  return (
    <div className={cn('min-w-0 space-y-1 overflow-x-hidden', isRTL ? 'text-right' : 'text-left')}>
      {!isUnlimited && dataLimit && <Progress value={progressValue} className="h-1" indicatorClassName={getProgressColor()} />}

      <div className={cn('flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] leading-4', isRTL ? 'justify-end' : 'justify-start')}>
        <span dir="ltr" className={cn('inline-flex shrink-0 items-center gap-0.5 font-semibold text-foreground', isRTL && 'flex-row-reverse')}>
          <Gauge className="h-2.5 w-2.5 shrink-0" strokeWidth={2.25} />
          {formatBytes(totalUsed)}
        </span>
        {!isUnlimited && dataLimit && (
          <span dir="ltr" className="shrink-0 text-muted-foreground">
            / {formatBytes(dataLimit)}
          </span>
        )}
        {totalLifetime > 0 && (
          <span dir="ltr" className={cn('inline-flex shrink-0 items-center gap-0.5 text-muted-foreground', isRTL && 'flex-row-reverse')}>
            <HardDrive className="h-2.5 w-2.5 shrink-0" strokeWidth={2.25} />
            {formatBytes(totalLifetime)}
          </span>
        )}
        {(uplink > 0 || downlink > 0) && <span className="hidden h-3 w-px shrink-0 bg-border sm:inline-block" />}
        {uplink > 0 && (
          <span dir="ltr" className={cn('inline-flex shrink-0 items-center gap-0.5 font-medium text-blue-500 dark:text-blue-400', isRTL && 'flex-row-reverse')}>
            <Upload className="h-2.5 w-2.5 shrink-0" strokeWidth={2.25} />
            {formatBytes(uplink)}
          </span>
        )}
        {downlink > 0 && (
          <span dir="ltr" className={cn('inline-flex shrink-0 items-center gap-0.5 font-medium text-emerald-500 dark:text-emerald-400', isRTL && 'flex-row-reverse')}>
            <Download className="h-2.5 w-2.5 shrink-0" strokeWidth={2.25} />
            {formatBytes(downlink)}
          </span>
        )}
      </div>
    </div>
  )
}
