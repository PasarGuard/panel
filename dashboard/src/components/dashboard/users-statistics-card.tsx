import { ActivityIcon, UsersIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { SystemStats } from '@/service/api'

const UserStatisticsCard = ({ data }: { data: SystemStats | undefined }) => {
  const { t } = useTranslation()
  const totalUsers = data?.total_user ?? 0
  const activeUsers = data?.active_users ?? 0
  const percentOfTotal = (value: number | undefined) => {
    if (!totalUsers || value === undefined || value <= 0) return null
    return Math.round((value / totalUsers) * 100)
  }
  const percentOfActive = (value: number | undefined) => {
    if (!activeUsers || value === undefined || value <= 0) return null
    return Math.round((value / activeUsers) * 100)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="truncate">{t('statistics.users')}</CardTitle>
        <CardDescription className="truncate">{t('monitorUsers')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex min-w-0 flex-row items-center gap-2 rounded-lg border p-3 shadow-sm md:gap-3 md:p-4">
          <UsersIcon className="size-5 text-muted-foreground md:size-6" />
          <span className="truncate text-sm md:text-base">{t('statistics.users')}</span>
          <span className="ms-auto font-bold text-sm md:text-base">{totalUsers}</span>
        </div>
        <div className="flex min-w-0 flex-row items-center gap-2 rounded-lg border p-3 shadow-sm md:gap-3 md:p-4">
          <ActivityIcon className="size-5 text-muted-foreground md:size-6" />
          <span className="truncate text-sm md:text-base">{t('statistics.activeUsers')}</span>
          <div className="ms-auto flex items-center gap-2">
            {percentOfTotal(data?.active_users) !== null && (
              <Badge variant="secondary" className="text-[10px] md:text-xs">
                {percentOfTotal(data?.active_users)}%
              </Badge>
            )}
            <span className="font-bold text-sm md:text-base">{data?.active_users || 0}</span>
          </div>
        </div>
        <div className="flex min-w-0 flex-row items-center gap-2 rounded-lg border p-3 shadow-sm md:gap-3 md:p-4">
          <div className="size-2 rounded-full bg-green-600 md:size-3" />
          <span className="truncate text-sm md:text-base">{t('statistics.onlineUsers')}</span>
          <div className="ms-auto flex items-center gap-2">
            {percentOfActive(data?.online_users) !== null && (
              <Badge variant="secondary" className="text-[10px] md:text-xs">
                {percentOfActive(data?.online_users)}%
              </Badge>
            )}
            <span className="font-bold text-sm md:text-base">{data?.online_users || 0}</span>
          </div>
        </div>
        <div className="flex min-w-0 flex-row items-center gap-2 rounded-lg border p-3 shadow-sm md:gap-3 md:p-4">
          <div className="size-2 rounded-full bg-red-600 md:size-3" />
          <span className="truncate text-sm md:text-base">{t('statistics.expiredUsers')}</span>
          <div className="ms-auto flex items-center gap-2">
            {percentOfTotal(data?.expired_users) !== null && (
              <Badge variant="secondary" className="text-[10px] md:text-xs">
                {percentOfTotal(data?.expired_users)}%
              </Badge>
            )}
            <span className="font-bold text-sm md:text-base">{data?.expired_users || 0}</span>
          </div>
        </div>
        <div className="flex min-w-0 flex-row items-center gap-2 rounded-lg border p-3 shadow-sm md:gap-3 md:p-4">
          <div className="size-2 rounded-full bg-orange-600 md:size-3" />
          <span className="truncate text-sm md:text-base">{t('statistics.limitedUsers')}</span>
          <div className="ms-auto flex items-center gap-2">
            {percentOfTotal(data?.limited_users) !== null && (
              <Badge variant="secondary" className="text-[10px] md:text-xs">
                {percentOfTotal(data?.limited_users)}%
              </Badge>
            )}
            <span className="font-bold text-sm md:text-base">{data?.limited_users || 0}</span>
          </div>
        </div>
        <div className="flex min-w-0 flex-row items-center gap-2 rounded-lg border p-3 shadow-sm md:gap-3 md:p-4">
          <div className="size-2 rounded-full bg-purple-600 md:size-3" />
          <span className="truncate text-sm md:text-base">{t('statistics.onHoldUsers')}</span>
          <div className="ms-auto flex items-center gap-2">
            {percentOfTotal(data?.on_hold_users) !== null && (
              <Badge variant="secondary" className="text-[10px] md:text-xs">
                {percentOfTotal(data?.on_hold_users)}%
              </Badge>
            )}
            <span className="font-bold text-sm md:text-base">{data?.on_hold_users || 0}</span>
          </div>
        </div>
        <div className="flex min-w-0 flex-row items-center gap-2 rounded-lg border p-3 shadow-sm md:gap-3 md:p-4">
          <div className="size-2 rounded-full bg-slate-600 md:size-3" />
          <span className="truncate text-sm md:text-base">{t('statistics.disabledUsers')}</span>
          <div className="ms-auto flex items-center gap-2">
            {percentOfTotal(data?.disabled_users) !== null && (
              <Badge variant="secondary" className="text-[10px] md:text-xs">
                {percentOfTotal(data?.disabled_users)}%
              </Badge>
            )}
            <span className="font-bold text-sm md:text-base">{data?.disabled_users || 0}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default UserStatisticsCard
