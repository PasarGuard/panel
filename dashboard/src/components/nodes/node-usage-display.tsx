import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { Progress } from '@/components/ui/progress'
import { formatBytes } from '@/utils/formatByte'
import { NodeResponse } from '@/service/api'
import { Upload, Download } from 'lucide-react'
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
    <div className={cn('mt-2 space-y-1.5', isRTL ? 'text-right' : 'text-left')}>
      {!isUnlimited && dataLimit && <Progress value={progressValue} className="h-1.5" indicatorClassName={getProgressColor()} />}
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <div className={cn('flex items-center gap-2', isRTL && 'flex-row-reverse')}>
          <span dir="ltr" className="font-medium">
            {formatBytes(totalUsed)}
          </span>
          {!isUnlimited && dataLimit && (
            <span dir="ltr" className="text-muted-foreground/70">
              / {formatBytes(dataLimit)}
            </span>
          )}
        </div>
        {totalLifetime > 0 && (
          <div className={cn('flex items-center gap-1')}>
            <span className="text-[10px]">{t('usersTable.total', { defaultValue: 'Total' })}:</span>
            <span dir="ltr" className="text-[10px]">
              {formatBytes(totalLifetime)}
            </span>
          </div>
        )}
      </div>
      {(uplink > 0 || downlink > 0) && (
        <div className={cn('flex items-center gap-3 text-[10px]', isRTL ? 'justify-end' : 'justify-start')}>
          {uplink > 0 && (
            <div className={cn('flex items-center gap-1', isRTL && 'flex-row-reverse')}>
              <Upload className="h-3 w-3 flex-shrink-0 text-blue-500" />
              <span dir="ltr" className="text-blue-500">
                {formatBytes(uplink)}
              </span>
            </div>
          )}
          {downlink > 0 && (
            <div className={cn('flex items-center gap-1', isRTL && 'flex-row-reverse')}>
              <Download className="h-3 w-3 flex-shrink-0 text-green-500" />
              <span dir="ltr" className="text-green-500">
                {formatBytes(downlink)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
