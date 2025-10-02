import { AdminDetails, SystemStats, useGetSystemStats } from '@/service/api'
import { UserCircleIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import UserStatisticsCard from './users-statistics-card'
import DataUsageChart from './data-usage-chart'

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
      <div className="flex flex-col gap-6 rounded-lg border px-2.5 py-4 shadow-lg md:px-4">
        <div className="flex flex-row items-center justify-between">
          <div className="flex flex-row items-center gap-2">
            <UserCircleIcon className="size-7 text-muted-foreground" />
            <span className="text-xl font-bold">{admin.username === 'Total' ? t('admins.total') : admin.username}</span>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <UserStatisticsCard data={statsToUse} />
          <DataUsageChart admin_username={shouldPassAdminUsername ? admin.username : undefined} />
        </div>
      </div>
    )

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <UserStatisticsCard data={statsToUse} />
      <DataUsageChart admin_username={shouldPassAdminUsername ? admin.username : undefined} />
    </div>
  )
}

export default AdminStatisticsCard
