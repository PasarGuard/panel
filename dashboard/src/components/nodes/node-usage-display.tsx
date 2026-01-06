import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { Progress } from '@/components/ui/progress'
import { formatBytes } from '@/utils/formatByte'
import { NodeResponse } from '@/service/api'
import { ArrowUp, ArrowDown } from 'lucide-react'
import { statusColors } from '@/constants/UserSettings'

interface NodeUsageDisplayProps {
  node: NodeResponse
}

export default function NodeUsageDisplay({ node }: NodeUsageDisplayProps) {
  const { t } = useTranslation()
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

  // Determine progress color based on usage (using same colors as active users)
  const getProgressColor = () => {
    if (isUnlimited) return ''
    if (progressValue >= 90) return statusColors.limited.sliderColor // bg-red-600
    if (progressValue >= 70) return statusColors.expired.sliderColor // bg-amber-600
    return statusColors.active.sliderColor // bg-emerald-600
  }

  if (totalUsed === 0 && !dataLimit && totalLifetime === 0) {
    return null
  }

  return (
    <div className={cn('space-y-1.5', isRTL ? 'text-right' : 'text-left')}>
      {/* Progress Bar */}
      {!isUnlimited && dataLimit && (
        <Progress value={progressValue} className="h-1" indicatorClassName={getProgressColor()} />
      )}

      {/* Main Usage Info */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5">
        <div className={cn('flex items-center gap-1.5', isRTL && 'flex-row-reverse')}>
          <span dir="ltr" className={cn("text-xs font-medium text-foreground", isRTL && 'justify-end')}>
            {formatBytes(totalUsed)}
          </span>
          {!isUnlimited && dataLimit && (
            <>
              <span className="text-muted-foreground/60">/</span>
              <span dir="ltr" className="text-xs text-muted-foreground">
                {formatBytes(dataLimit)}
              </span>
            </>
          )}
        </div>
        {totalLifetime > 0 && (
          <div className='flex items-center gap-1'>
            <span className="text-[10px] text-muted-foreground">
              {t('usersTable.total', { defaultValue: 'Total' })}:
            </span>
            <span dir="ltr" className="text-[10px] font-medium text-muted-foreground">
              {formatBytes(totalLifetime)}
            </span>
          </div>
        )}
      </div>

      {/* Upload/Download Stats */}
      {(uplink > 0 || downlink > 0) && (
        <div className={cn('flex flex-wrap items-center gap-x-3 gap-y-1', isRTL ? 'justify-end' : 'justify-start')}>
          {uplink > 0 && (
            <div className={cn('flex items-center gap-1', isRTL && 'flex-row-reverse')}>
              <ArrowUp className="h-3 w-3 sm:h-3.5 sm:w-3.5 shrink-0 text-blue-500 dark:text-blue-400" strokeWidth={2} />
              <span dir="ltr" className="text-[10px] font-medium text-blue-500 dark:text-blue-400">
                {formatBytes(uplink)}
              </span>
            </div>
          )}
          {downlink > 0 && (
            <div className={cn('flex items-center gap-1', isRTL && 'flex-row-reverse')}>
              <ArrowDown className="h-3 w-3 sm:h-3.5 sm:w-3.5 shrink-0 text-emerald-500 dark:text-emerald-400" strokeWidth={2} />
              <span dir="ltr" className="text-[10px] font-medium text-emerald-500 dark:text-emerald-400">
                {formatBytes(downlink)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
