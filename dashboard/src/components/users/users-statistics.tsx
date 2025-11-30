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
    <div className="flex flex-col gap-y-4">
      <div className={cn('flex flex-col items-center justify-between gap-x-4 gap-y-4 lg:flex-row', dir === 'rtl' && 'lg:flex-row-reverse')}>
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
            <CardTitle className="relative z-10 flex items-center justify-between gap-x-4">
              <div className="flex items-center gap-x-4">
                <div className="min-h-[10px] min-w-[10px] rounded-full bg-green-500 shadow-sm" />
                <span className="">{t('statistics.onlineUsers')}</span>
              </div>
              <span className={cn('mx-2 text-3xl transition-all duration-500', isIncreased.online_users ? 'animate-zoom-out' : '')} style={{ animationDuration: '400ms' }}>
                {data ? <CountUp end={data.online_users} /> : 0}
              </span>
            </CardTitle>
          </Card>
        </div>

        <div className="w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '150ms' }}>
          <Card dir={dir} className="group relative w-full overflow-hidden rounded-md px-4 py-6 transition-all duration-500">
            <div
              className={cn(
                'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
                'dark:from-primary/5 dark:to-transparent',
                'group-hover:opacity-100',
              )}
            />
            <CardTitle className="relative z-10 flex items-center justify-between gap-x-4">
              <div className="flex items-center gap-x-4">
                <Wifi className="h-5 w-5" />
                <span className="">{t('statistics.activeUsers')}</span>
              </div>
              <span className={cn('mx-2 text-3xl transition-all duration-500', isIncreased.active_users ? 'animate-zoom-out' : '')} style={{ animationDuration: '400ms' }}>
                {data ? <CountUp end={data.active_users} /> : 0}
              </span>
            </CardTitle>
          </Card>
        </div>

        <div className="w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '250ms' }}>
          <Card dir={dir} className="group relative w-full overflow-hidden rounded-md px-4 py-6 transition-all duration-500">
            <div
              className={cn(
                'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
                'dark:from-primary/5 dark:to-transparent',
                'group-hover:opacity-100',
              )}
            />
            <CardTitle className="relative z-10 flex items-center justify-between gap-x-4">
              <div className="flex items-center gap-x-4">
                <Users className="h-5 w-5" />
                <span className="">{t('statistics.users')}</span>
              </div>
              <span className={cn('mx-2 text-3xl transition-all duration-500', isIncreased.total_user ? 'animate-zoom-out' : '')} style={{ animationDuration: '400ms' }}>
                {data ? <CountUp end={data.total_user} /> : 0}
              </span>
            </CardTitle>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default UsersStatistics
