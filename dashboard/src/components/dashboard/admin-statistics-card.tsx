import { AdminDetails, SystemStats, useGetSystemStats } from '@/service/api'
import { UserCog, Users } from 'lucide-react'
import { Suspense, lazy, useEffect, useState, type ComponentProps } from 'react'
import { useTranslation } from 'react-i18next'
import UserStatisticsCard from './users-statistics-card'

const DataUsageChart = lazy(() => import('./data-usage-chart'))

function DataUsageChartSkeleton() {
  return (
    <div className="rounded-lg border bg-card/80 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        <div className="h-4 w-20 animate-pulse rounded bg-muted" />
      </div>
      <div className="mt-4 h-[240px] w-full animate-pulse rounded bg-muted sm:h-[320px]" />
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
  admin: AdminDetails | undefined
  systemStats: SystemStats | undefined
  showAdminInfo?: boolean
  currentAdmin?: AdminDetails | undefined
}) => {
  const { t } = useTranslation()
  if (!admin) return null

  // Send admin_username for specific admin stats, except for 'Total' which shows global stats
  const systemStatsParams = admin.username !== 'Total' ? { admin_username: admin.username } : undefined

  // Fetch system stats specific to this admin
  const { data: adminSystemStats } = useGetSystemStats(systemStatsParams, {
    query: {
      refetchInterval: 5000,
    },
  })

  // Use admin-specific stats if available, otherwise fall back to global stats
  const statsToUse = adminSystemStats || systemStats

  // For DataUsageChart: pass admin_username for specific admin data, except for 'Total' which shows global data
  const shouldPassAdminUsername = admin.username !== 'Total'

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
          <DeferredDataUsageChart admin_username={shouldPassAdminUsername ? admin.username : undefined} />
        </div>
      </div>
    )

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <UserStatisticsCard data={statsToUse} />
      <DeferredDataUsageChart admin_username={shouldPassAdminUsername ? admin.username : undefined} />
    </div>
  )
}

export default AdminStatisticsCard
