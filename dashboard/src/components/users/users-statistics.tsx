import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useGetSystemStats } from '@/service/api'
import { Users, Wifi } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardTitle } from '@/components/ui/card'
import { CountUp } from '@/components/ui/count-up'

const UsersStatistics = () => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [prevData, setPrevData] = useState<any>(null)
  const [isIncreased, setIsIncreased] = useState<Record<string, boolean>>({})

  const { data } = useGetSystemStats(undefined, {
    query: {
      refetchInterval: 5000,
    },
  })

  useEffect(() => {
    if (prevData && data) {
      setIsIncreased({
        online_users: data.online_users > prevData.online_users,
        active_users: data.active_users > prevData.active_users,
        total_user: data.total_user > prevData.total_user,
      })
    }
    setPrevData(data)
  }, [data])

  return (
    <div
      className={cn(
        'grid w-full gap-3 sm:gap-4',
        'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
        'auto-rows-fr',
        dir === 'rtl' && 'lg:grid-flow-col-reverse',
      )}
    >
      {/* Online Users */}
      <div className="w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '50ms' }}>
        <Card dir={dir} className="group relative w-full overflow-hidden rounded-md px-4 py-6 transition-all duration-500">
            <div
              className={cn(
                'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
                'dark:from-primary/5 dark:to-transparent',
                'group-hover:opacity-100',
              )}
            />
            <CardTitle className="relative z-10 flex min-w-0 items-center justify-between gap-x-4 overflow-hidden">
              <div className="flex min-w-0 flex-1 items-center gap-x-4 overflow-hidden">
                <div className="min-h-[10px] min-w-[10px] shrink-0 rounded-full bg-green-500 shadow-sm" />
                <span className="truncate">{t('statistics.onlineUsers')}</span>
              </div>
              <span className={cn('mx-2 shrink-0 text-3xl transition-all duration-500', isIncreased.online_users ? 'animate-zoom-out' : '')} style={{ animationDuration: '400ms' }}>
                {data ? <CountUp end={data.online_users} /> : 0}
              </span>
            </CardTitle>
          </Card>
        </div>

      {/* Active Users */}
      <div className="w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '150ms' }}>
        <Card dir={dir} className="group relative w-full overflow-hidden rounded-md px-4 py-6 transition-all duration-500">
            <div
              className={cn(
                'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
                'dark:from-primary/5 dark:to-transparent',
                'group-hover:opacity-100',
              )}
            />
            <CardTitle className="relative z-10 flex min-w-0 items-center justify-between gap-x-4 overflow-hidden">
              <div className="flex min-w-0 flex-1 items-center gap-x-4 overflow-hidden">
                <Wifi className="h-5 w-5 shrink-0" />
                <span className="truncate">{t('statistics.activeUsers')}</span>
              </div>
              <span className={cn('mx-2 shrink-0 text-3xl transition-all duration-500', isIncreased.active_users ? 'animate-zoom-out' : '')} style={{ animationDuration: '400ms' }}>
                {data ? <CountUp end={data.active_users} /> : 0}
              </span>
            </CardTitle>
          </Card>
        </div>

      {/* Total Users */}
      <div className="w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '250ms' }}>
        <Card dir={dir} className="group relative w-full overflow-hidden rounded-md px-4 py-6 transition-all duration-500">
            <div
              className={cn(
                'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
                'dark:from-primary/5 dark:to-transparent',
                'group-hover:opacity-100',
              )}
            />
            <CardTitle className="relative z-10 flex min-w-0 items-center justify-between gap-x-4 overflow-hidden">
              <div className="flex min-w-0 flex-1 items-center gap-x-4 overflow-hidden">
                <Users className="h-5 w-5 shrink-0" />
                <span className="truncate">{t('statistics.users')}</span>
              </div>
              <span className={cn('mx-2 shrink-0 text-3xl transition-all duration-500', isIncreased.total_user ? 'animate-zoom-out' : '')} style={{ animationDuration: '400ms' }}>
                {data ? <CountUp end={data.total_user} /> : 0}
              </span>
            </CardTitle>
          </Card>
        </div>
    </div>
  )
}

export default UsersStatistics
