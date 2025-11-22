import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { dateUtils } from '@/utils/dateFormatter'
import { FC } from 'react'
import { useTranslation } from 'react-i18next'
import dayjs from '@/lib/dayjs'

type UserStatusProps = {
  lastOnline: string | number | null | undefined
}

export const OnlineStatus: FC<UserStatusProps> = ({ lastOnline }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  if (!lastOnline) {
    return <span className={cn('inline-block text-xs font-medium', dir === 'rtl' ? 'mr-0.5 md:mr-2' : 'ml-0.5 md:ml-2', 'text-gray-600 dark:text-gray-400')}>{t('notConnectedYet')}</span>
  }

  const currentTime = dayjs()
  const lastOnlineTime = dateUtils.toDayjs(lastOnline)
  const diffInSeconds = currentTime.diff(lastOnlineTime, 'seconds')

  const isOnline = diffInSeconds <= 60

  if (isOnline) {
    return <span className={cn('inline-block text-xs font-medium', dir === 'rtl' ? 'mr-0.5 md:mr-2' : 'ml-0.5 md:ml-2', 'text-gray-600 dark:text-gray-400')}>{t('online')}</span>
  } else {
    // Format the time difference for offline status using calendar-aware diff methods
    const years = Math.abs(currentTime.diff(lastOnlineTime, 'year'))
    const months = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year'), 'month'))
    const days = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month'), 'day'))
    const hours = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month').add(days, 'day'), 'hour'))
    const minutes = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month').add(days, 'day').add(hours, 'hour'), 'minute'))
    const seconds = Math.abs(currentTime.diff(lastOnlineTime.add(years, 'year').add(months, 'month').add(days, 'day').add(hours, 'hour').add(minutes, 'minute'), 'second'))

    let timeText = ''

    if (years > 0) {
      timeText = `${years} ${t(`time.${years !== 1 ? 'years' : 'year'}`)} ${t('time.ago')}`
    } else if (months > 0) {
      timeText = `${months} ${t(`time.${months !== 1 ? 'months' : 'month'}`)} ${t('time.ago')}`
    } else if (days > 0) {
      timeText = `${days} ${t(`time.${days !== 1 ? 'days' : 'day'}`)} ${t('time.ago')}`
    } else if (hours > 0) {
      timeText = `${hours} ${t(`time.${hours !== 1 ? 'hours' : 'hour'}`)} ${t('time.ago')}`
    } else if (minutes > 0) {
      timeText = `${minutes} ${t(`time.${minutes !== 1 ? 'mins' : 'min'}`)} ${t('time.ago')}`
    } else {
      timeText = `${seconds} ${t(`time.${seconds !== 1 ? 'seconds' : 'second'}`)} ${t('time.ago')}`
    }

    return <span className={cn('inline-block text-xs font-medium', dir === 'rtl' ? 'mr-0.5 md:mr-2' : 'ml-0.5 md:ml-2', 'text-gray-600 dark:text-gray-400')}>{timeText}</span>
  }
}
