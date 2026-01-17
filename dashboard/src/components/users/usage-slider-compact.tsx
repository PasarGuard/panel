import { statusColors } from '@/constants/UserSettings'
import { cn } from '@/lib/utils'
import { formatBytes } from '@/utils/formatByte'
import { useTranslation } from 'react-i18next'
import { Progress } from '@/components/ui/progress'
import useDirDetection from '@/hooks/use-dir-detection'
import { useState } from 'react'
import { TrafficModal } from './traffic-modal'

type UsageSliderProps = {
  used: number
  total: number | null | undefined
  totalUsedTraffic: number | undefined
  status: string
  isMobile?: boolean
  username?: string
}

const UsageSliderCompact: React.FC<UsageSliderProps> = ({ used, total = 0, status, totalUsedTraffic, isMobile, username }) => {
  const isUnlimited = total === 0 || total === null
  const progressValue = isUnlimited ? 100 : (used / total) * 100
  const color = statusColors[status]?.sliderColor
  const { t } = useTranslation()
  const isRTL = useDirDetection() === 'rtl'
  const [isModalOpen, setIsModalOpen] = useState(false)

  return (
    <div className="w-full" onClick={e => e.stopPropagation()}>
      <div
        className={cn('prevent-edit flex w-full cursor-pointer flex-col justify-between gap-y-1 text-left text-xs font-medium text-muted-foreground', isRTL ? 'md:text-end' : 'md:text-start')}
        onClick={() => {
          if (username) setIsModalOpen(true)
        }}
      >
        <Progress indicatorClassName={color} value={progressValue} className={cn(isMobile ? 'block' : 'hidden md:block')} />
        <div className="flex w-full items-center justify-between gap-2">
          <span className={isMobile ? 'hidden' : ''} dir="ltr">
            {formatBytes(used)} / {isUnlimited ? <span className="font-system-ui">∞</span> : formatBytes(total)}
          </span>
          <div className={cn(isMobile ? 'block' : 'hidden md:block', 'whitespace-nowrap')}>
            <span className="text-muted-foreground/70">{t('usersTable.total')}:</span> <span dir="ltr">{formatBytes(totalUsedTraffic || 0)}</span>
          </div>
        </div>
      </div>
      {username && <TrafficModal username={username} isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />}
    </div>
  )
}

export default UsageSliderCompact
