import { AdminDetails, SystemUsersStats, useGetSystemUsersStats } from '@/service/api'
import { UserCog, Users } from 'lucide-react'
import { Suspense, lazy, useEffect, useState, type ComponentProps } from 'react'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/skeleton'
import UserStatisticsCard from './users-statistics-card'

const DataUsageChart = lazy(() => import('./data-usage-chart'))

type DashboardAdmin = Pick<AdminDetails, 'id' | 'username'>

function DataUsageChartSkeleton() {
  return (
    <div className="rounded-lg border bg-card/80 p-4">
      <div className="flex items-center justify-between gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-20" />
      </div>
      <Skeleton className="mt-4 h-[240px] w-full sm:h-[320px]" />
    </div>
  )
}

function DeferredDataUsageChart(props: ComponentProps<typeof DataUsageChart>) {
  const [shouldLoad, setShouldLoad] = useState(false)

  useEffect(() => {
    const id = window.setTimeout(() => setShouldLoad(true), 250)
    return () => window.clearTimeout(id)
  }, [])

  if (!shouldLoad) return <DataUsageChartSkeleton />

  return (
    <Suspense fallback={<DataUsageChartSkeleton />}>
      <DataUsageChart {...props} />
    </Suspense>
  )
}

const AdminStatisticsCard = ({
  admin,
  systemStats,
  showAdminInfo = true,
}: {
  admin: DashboardAdmin | undefined
  systemStats: SystemUsersStats | undefined
  showAdminInfo?: boolean
  currentAdmin?: AdminDetails | undefined
}) => {
  const { t } = useTranslation()
  if (!admin) return null

  // Send admin_username for specific admin stats, except for 'Total' which shows global stats
  const systemStatsParams = admin.username !== 'Total' ? { admin_username: admin.username } : undefined

  // Fetch system stats specific to this admin
  const { data: adminSystemStats } = useGetSystemUsersStats(systemStatsParams, {
    query: {
      enabled: !systemStats && admin.username !== 'Total',
      refetchInterval: 5000,
    },
  })

  // The dashboard parent already fetches `/api/system` with the selected admin scope.
  const statsToUse = systemStats || adminSystemStats

  // Users usage API filters by admin username (`admin` query alias), not admin id.
  const shouldScopeAdminData = admin.username !== 'Total'

  if (showAdminInfo)
    return (
      <div className="flex flex-col gap-6 rounded-lg py-4">
        <div className="flex flex-row items-center justify-between">
          <div className="flex min-w-0 flex-row items-center gap-2">
            {admin.username === 'Total' ? (
              <Users className="size-6 text-muted-foreground md:size-7" />
            ) : (
              <UserCog className="size-6 text-muted-foreground md:size-7" />
            )}
            <span className="truncate text-lg font-bold md:text-xl">
              {admin.username === 'Total' ? t('admins.total') : admin.username}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <UserStatisticsCard data={statsToUse} />
          <DeferredDataUsageChart adminUsername={shouldScopeAdminData ? admin.username : undefined} />
        </div>
      </div>
    )

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <UserStatisticsCard data={statsToUse} />
      <DeferredDataUsageChart adminUsername={shouldScopeAdminData ? admin.username : undefined} />
    </div>
  )
}

export default AdminStatisticsCard
