import { statusColors } from '@/constants/UserSettings'
import { cn } from '@/lib/utils'
import { formatBytes } from '@/utils/formatByte'
import { useTranslation } from 'react-i18next'
import { Progress } from '@/components/ui/progress'
import useDirDetection from '@/hooks/use-dir-detection'

type UsageSliderProps = {
  used: number
  total: number | null | undefined
  totalUsedTraffic: number | undefined
  status: string
  isMobile?: boolean
}

const UsageSliderCompact: React.FC<UsageSliderProps> = ({ used, total = 0, status, totalUsedTraffic, isMobile }) => {
  const isUnlimited = total === 0 || total === null
  const progressValue = isUnlimited ? 100 : (used / total) * 100
  const color = statusColors[status]?.sliderColor
  const { t } = useTranslation()
  const isRTL = useDirDetection() === 'rtl'
  return (
    <div className={cn('flex w-full flex-col justify-between gap-y-1 text-left text-xs font-medium text-muted-foreground', isRTL ? 'md:text-end' : 'md:text-start')}>
      <Progress indicatorClassName={color} value={progressValue} className={cn(isMobile ? 'block' : 'hidden md:block')} />
      <div className="flex w-full items-center justify-between">
        <span className={isMobile ? 'hidden' : 'w-full'} dir="ltr">
          {formatBytes(used)} / {isUnlimited ? <span className="font-system-ui">∞</span> : formatBytes(total)}
        </span>
        <div className={cn(isMobile ? 'block' : 'hidden md:block')}>
          <span>{t('usersTable.total')}:</span> <span dir="ltr">{formatBytes(totalUsedTraffic || 0)}</span>
        </div>
      </div>
    </div>
  )
}
export default UsageSliderCompact
