import { FC } from 'react'
import { dateUtils } from '@/utils/dateFormatter'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { useTranslation } from 'react-i18next'
import dayjs from '@/lib/dayjs'

type UserStatusProps = {
  lastOnline?: string | null
}

export const OnlineBadge: FC<UserStatusProps> = ({ lastOnline }) => {
  const { t } = useTranslation()

  const getTooltipText = () => {
    if (!lastOnline) {
      return t('notConnectedYet')
    }

    const currentTime = dayjs()
    const lastOnlineTime = dateUtils.toDayjs(lastOnline)
    const diffInSeconds = currentTime.diff(lastOnlineTime, 'seconds')

    const isOnline = diffInSeconds <= 60

    if (isOnline) {
      return t('online')
    } else {
      // Format the time difference for offline status using calendar-aware diff methods
      const years = Math.abs(currentTime.diff(lastOnlineTime, 'year'))
      const months = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year'), 'month'))
      const days = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month'), 'day'))
      const hours = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month').add(days, 'day'), 'hour'))
      const minutes = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month').add(days, 'day').add(hours, 'hour'), 'minute'))
      const seconds = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month').add(days, 'day').add(hours, 'hour').add(minutes, 'minute'), 'second'))

      const parts: string[] = []

      if (years > 0) {
        parts.push(`${years} ${t(`time.${years !== 1 ? 'years' : 'year'}`)}`)
      }
      if (months > 0) {
        parts.push(`${months} ${t(`time.${months !== 1 ? 'months' : 'month'}`)}`)
      }
      if (days > 0) {
        parts.push(`${days} ${t(`time.${days !== 1 ? 'days' : 'day'}`)}`)
      }
      if (hours > 0 && parts.length < 2) {
        parts.push(`${hours} ${t(`time.${hours !== 1 ? 'hours' : 'hour'}`)}`)
      }
      if (minutes > 0 && parts.length < 2) {
        parts.push(`${minutes} ${t(`time.${minutes !== 1 ? 'mins' : 'min'}`)}`)
      }
      if (seconds > 0 && parts.length === 0) {
        parts.push(`${seconds} ${t(`time.${seconds !== 1 ? 'seconds' : 'second'}`)}`)
      }

      if (parts.length === 0) {
        return t('time.ago')
      }

      const timeText = parts.join(', ')
      return `${timeText} ${t('time.ago')}`
    }
  }

  const renderBadge = () => {
    if (!lastOnline) {
      return <div className="min-h-[10px] min-w-[10px] rounded-full border border-gray-400 shadow-sm dark:border-gray-600" />
    }

    const currentTime = dayjs()
    const lastOnlineTime = dateUtils.toDayjs(lastOnline)
    const diffInSeconds = currentTime.diff(lastOnlineTime, 'seconds')

    const isOnline = diffInSeconds <= 60

    if (isOnline) {
      // Online - green dot
      return <div className="min-h-[10px] min-w-[10px] rounded-full bg-green-500 shadow-sm" />
    } else {
      // Offline - gray dot
      return <div className="min-h-[10px] min-w-[10px] rounded-full bg-gray-400 shadow-sm dark:bg-gray-600" />
    }
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{renderBadge()}</TooltipTrigger>
        <TooltipContent>
          <p>{getTooltipText()}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
