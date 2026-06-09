import { AdminDetails, SystemUsersStats, useGetAdmins } from '@/service/api'
import AdminStatisticsCard from './admin-statistics-card'

const DashboardAdminStatistics = ({ currentAdmin, systemStats }: { currentAdmin: AdminDetails | undefined; systemStats: SystemUsersStats | undefined }) => {
  const { data } = useGetAdmins(undefined, {
    query: {
      refetchInterval: false,
    },
  })

  if (!data || !currentAdmin) return null

  const admins = data.admins ?? []

  if (admins.length === 1) {
    return <AdminStatisticsCard showAdminInfo={false} admin={currentAdmin} systemStats={systemStats} skipStatsFetch />
  }

  return (
    <div className="flex flex-col gap-4">
      {admins.map((admin: AdminDetails) => (
        <AdminStatisticsCard key={admin.username} admin={admin} systemStats={undefined} />
      ))}
    </div>
  )
}

export default DashboardAdminStatistics
