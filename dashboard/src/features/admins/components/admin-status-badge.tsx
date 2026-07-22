import { Badge } from '@/components/ui/badge'
import { statusColors } from '@/constants/UserSettings'
import { cn } from '@/lib/utils'
import { FC } from 'react'
import { useTranslation } from 'react-i18next'

type AdminStatusProps = {
  isSudo: boolean
  status?: string | null
  isDisabled?: boolean
  label?: string
  compact?: boolean
}

export const AdminStatusBadge: FC<AdminStatusProps> = ({ isSudo: _isSudo, status, isDisabled, label, compact }) => {
  const { t } = useTranslation()
  const resolvedStatus = status || (isDisabled ? 'disabled' : 'active')

  const getStatusInfo = () => {
    const baseColor = statusColors[resolvedStatus]?.statusColor || 'bg-gray-400 text-white'
    const baseIcon = statusColors[resolvedStatus]?.icon || null

    if (compact) {
      return {
        color: baseColor,
        icon: baseIcon,
        text: t(`status.${resolvedStatus}`, { defaultValue: resolvedStatus }),
      }
    }

    return {
      color: baseColor,
      icon: baseIcon,
      text: label || t(`status.${resolvedStatus}`, { defaultValue: resolvedStatus }),
    }
  }

  const statusInfo = getStatusInfo()
  const StatusIcon = statusInfo.icon

  return (
    <Badge
      className={cn(
        'pointer-events-none flex w-fit max-w-[150px] items-center justify-center gap-x-2 rounded-full px-0.5 py-0.5 sm:px-2',
        statusInfo.color,
        'h-6 px-1.5 py-2.5 sm:h-auto sm:px-0.5 sm:py-0.5',
      )}
    >
      <div className={cn('flex items-center gap-1 sm:px-1', !compact && 'px-1')}>
        {StatusIcon && <StatusIcon className="h-4 w-4 sm:h-3 sm:w-3" />}
        <span className={cn('text-xs font-medium text-nowrap capitalize', compact ? 'hidden sm:block' : 'block')}>{statusInfo.text}</span>
      </div>
    </Badge>
  )
}
