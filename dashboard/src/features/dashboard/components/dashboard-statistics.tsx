import { Skeleton } from '@/components/ui/skeleton'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { SystemResourceStats, SystemUsersStats } from '@/service/api'
import { formatBytes } from '@/utils/formatByte'
import { formatDuration } from '@/utils/formatDuration'
import { Clock3, Cpu, Database, Download, HardDrive, MemoryStick, Upload, UserCheck, Users, Wifi } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { CircularProgress } from '@/components/ui/circular-progress'
import { Card, CardContent } from '@/components/ui/card'

const DashboardStatistics = ({ resourceData, usersData }: { resourceData: SystemResourceStats | undefined; usersData: SystemUsersStats | undefined }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  // Show skeleton loader while data is being fetched
  if (!resourceData && !usersData) {
    return (
      <div className={cn('grid h-full w-full gap-3 sm:gap-4 lg:gap-6', 'grid-cols-1 sm:grid-cols-2', dir === 'rtl' && 'lg:grid-flow-col-reverse')}>
        {[...Array(6)].map((_, i) => (
          <Card key={i} className={cn('h-full overflow-hidden border', (i === 4 || i === 5) && 'sm:col-span-2')}>
            <CardContent className="flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
              <div className="mb-2 flex items-start justify-between sm:mb-3">
                <div className="flex items-center gap-2 sm:gap-3">
                  <Skeleton className="h-7 w-7 rounded-lg sm:h-9 sm:w-9" />
                  <Skeleton className="h-4 w-24 sm:h-5" />
                </div>
              </div>
              {i === 5 ? (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3">
                  {[...Array(3)].map((_, metricIndex) => (
                    <div key={metricIndex} className="bg-background/60 rounded-lg border p-3 sm:p-4">
                      <Skeleton className="mb-2 h-4 w-24 sm:h-5 sm:w-28" />
                      <Skeleton className="h-8 w-20 sm:h-10 sm:w-24" />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-end justify-between gap-2">
                  <Skeleton className="h-8 w-20 sm:h-10 sm:w-32 lg:h-12 lg:w-40" />
                  <Skeleton className="h-6 w-16 sm:h-7 sm:w-20" />
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  const getTotalTrafficValue = () => {
    if (!usersData) return 0

    // For master server stats - use total traffic
    return Number(usersData.incoming_bandwidth) + Number(usersData.outgoing_bandwidth)
  }

  const getIncomingBandwidth = () => {
    if (!usersData) return 0
    return Number(usersData.incoming_bandwidth) || 0
  }

  const getOutgoingBandwidth = () => {
    if (!usersData) return 0
    return Number(usersData.outgoing_bandwidth) || 0
  }

  const getMemoryUsage = () => {
    if (!resourceData) return { used: 0, total: 0, percentage: 0 }

    const memUsed = Number(resourceData.mem_used) || 0
    const memTotal = Number(resourceData.mem_total) || 0
    const percentage = memTotal > 0 ? (memUsed / memTotal) * 100 : 0

    return { used: memUsed, total: memTotal, percentage }
  }

  const getDiskUsage = () => {
    if (!resourceData) return { used: 0, total: 0, percentage: 0 }

    const diskUsed = Number(resourceData.disk_used) || 0
    const diskTotal = Number(resourceData.disk_total) || 0
    const percentage = diskTotal > 0 ? (diskUsed / diskTotal) * 100 : 0

    return { used: diskUsed, total: diskTotal, percentage }
  }

  const getCpuInfo = () => {
    if (!resourceData) return { usage: 0, cores: 0 }

    let cpuUsage = Number(resourceData.cpu_usage) || 0
    const cpuCores = Number(resourceData.cpu_cores) || 0

    // CPU usage is already in percentage (0-100), no need to multiply
    // Just ensure it's within reasonable bounds
    cpuUsage = Math.min(Math.max(cpuUsage, 0), 100)

    return { usage: Math.round(cpuUsage * 10) / 10, cores: cpuCores } // Round to 1 decimal place
  }

  const memory = getMemoryUsage()
  const disk = getDiskUsage()
  const cpu = getCpuInfo()
  const memoryPercent = Math.min(Math.max(memory.percentage, 0), 100)
  const diskPercent = Math.min(Math.max(disk.percentage, 0), 100)
  const totalUsers = Number(usersData?.total_user) || 0
  const activeUsers = Number(usersData?.active_users) || 0
  const onlineUsers = Number(usersData?.online_users) || 0
  const activeUsersPercent = totalUsers > 0 ? Math.min(Math.max((activeUsers / totalUsers) * 100, 0), 100) : 0
  const onlineUsersPercent = activeUsers > 0 ? Math.min(Math.max((onlineUsers / activeUsers) * 100, 0), 100) : 0
  const uptime = resourceData ? formatDuration(resourceData.uptime_seconds, t) : null

  return (
    <div
      className={cn(
        'grid h-full w-full gap-3 sm:gap-4 lg:gap-6',
        // Responsive grid: 1 column on mobile, 2 on tablet, 4 on desktop
        'grid-cols-1 sm:grid-cols-2',
        dir === 'rtl' && 'lg:grid-flow-col-reverse',
      )}
    >
      {/* CPU Usage */}
      <div className="animate-fade-in h-full w-full" style={{ animationDuration: '600ms', animationDelay: '50ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'from-primary/10 absolute inset-0 bg-gradient-to-r to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="bg-primary/10 rounded-lg p-1.5 sm:p-2">
                  <Cpu className="text-primary h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-muted-foreground truncate text-xs font-medium sm:text-sm">{t('statistics.cpuUsage')}</p>
                </div>
              </div>
              <CircularProgress value={cpu.usage} size={38} strokeWidth={4} showValue={false} className="shrink-0 opacity-90" />
            </div>

            <div className="flex items-end justify-between gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
                <span dir="ltr" className="truncate text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                  {cpu.usage}%
                </span>
              </div>

              {cpu.cores > 0 && (
                <div className="bg-muted/50 text-muted-foreground flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs sm:px-2 sm:text-sm">
                  <Cpu className="text-primary h-3 w-3" />
                  <span className="font-medium whitespace-nowrap">
                    {cpu.cores} {t('statistics.cores')}
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Memory Usage */}
      <div className="animate-fade-in h-full w-full" style={{ animationDuration: '600ms', animationDelay: '150ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'from-primary/10 absolute inset-0 bg-gradient-to-r to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="bg-primary/10 rounded-lg p-1.5 sm:p-2">
                  <MemoryStick className="text-primary h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-muted-foreground truncate text-xs font-medium sm:text-sm">{t('statistics.ramUsage')}</p>
                </div>
              </div>
              <CircularProgress value={memoryPercent} size={38} strokeWidth={4} showValue={false} className="shrink-0 opacity-90" />
            </div>

            <div className="flex items-end justify-between gap-2">
              <span dir="ltr" className="truncate text-lg font-bold transition-all duration-300 sm:text-xl lg:text-2xl">
                <span className="whitespace-nowrap">
                  {formatBytes(memory.used, 1, false, false, 'GB')}/{formatBytes(memory.total, 1, true, false, 'GB')}
                </span>
              </span>
              <span dir="ltr" className="bg-muted/60 text-muted-foreground rounded-md px-1.5 py-1 text-xs font-medium whitespace-nowrap sm:px-2">
                {memoryPercent.toFixed(1)}%
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Disk Usage */}
      <div className="animate-fade-in h-full w-full" style={{ animationDuration: '600ms', animationDelay: '250ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'from-primary/10 absolute inset-0 bg-gradient-to-r to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="bg-primary/10 rounded-lg p-1.5 sm:p-2">
                  <HardDrive className="text-primary h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-muted-foreground truncate text-xs font-medium sm:text-sm">{t('statistics.diskUsage')}</p>
                </div>
              </div>
              <CircularProgress value={diskPercent} size={38} strokeWidth={4} showValue={false} className="shrink-0 opacity-90" />
            </div>

            <div className="flex items-end justify-between gap-2">
              <span dir="ltr" className="truncate text-lg font-bold transition-all duration-300 sm:text-xl lg:text-2xl">
                <span className="whitespace-nowrap">
                  {formatBytes(disk.used, 1, false, false, 'GB')}/{formatBytes(disk.total, 1, true, false, 'GB')}
                </span>
              </span>
              <span dir="ltr" className="bg-muted/60 text-muted-foreground rounded-md px-1.5 py-1 text-xs font-medium whitespace-nowrap sm:px-2">
                {diskPercent.toFixed(1)}%
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {usersData && (
        <>
          {/* Total Traffic with Incoming/Outgoing Details */}
          <div className="animate-fade-in h-full w-full" style={{ animationDuration: '600ms', animationDelay: '350ms' }}>
            <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
              <div
                className={cn(
                  'from-primary/10 absolute inset-0 bg-gradient-to-r to-transparent opacity-0 transition-opacity duration-500',
                  'dark:from-primary/5 dark:to-transparent',
                  'group-hover:opacity-100',
                )}
              />
              <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
                <div className="mb-2 flex items-start justify-between sm:mb-3">
                  <div className="flex items-center gap-2 sm:gap-3">
                    <div className="bg-primary/10 rounded-lg p-1.5 sm:p-2">
                      <Database className="text-primary h-4 w-4 sm:h-5 sm:w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-muted-foreground truncate text-xs font-medium sm:text-sm">{t('statistics.totalTraffic')}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-end justify-between gap-2">
                  <div className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
                    <span dir="ltr" className="truncate text-lg font-bold transition-all duration-300 sm:text-xl lg:text-2xl">
                      {formatBytes(getTotalTrafficValue() || 0, 1)}
                    </span>
                  </div>

                  {/* Incoming/Outgoing Details */}
                  <div className="flex shrink-0 items-center gap-2 text-xs">
                    <div className="bg-muted/50 flex items-center gap-1 rounded-md px-1.5 py-1 text-green-600 dark:text-green-400">
                      <Download className="h-3 w-3" />
                      <span dir="ltr" className="font-medium">
                        {formatBytes(getIncomingBandwidth() || 0, 1)}
                      </span>
                    </div>
                    <div className="bg-muted/50 flex items-center gap-1 rounded-md px-1.5 py-1 text-blue-600 dark:text-blue-400">
                      <Upload className="h-3 w-3" />
                      <span dir="ltr" className="font-medium">
                        {formatBytes(getOutgoingBandwidth() || 0, 1)}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {/* Panel Uptime */}
      <div className="animate-fade-in h-full w-full sm:col-span-2" style={{ animationDuration: '600ms', animationDelay: '450ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'from-primary/10 absolute inset-0 bg-gradient-to-r to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="bg-primary/10 rounded-lg p-1.5 sm:p-2">
                  <Clock3 className="text-primary h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-muted-foreground truncate text-xs font-medium sm:text-sm">{t('statistics.uptime')}</p>
                </div>
              </div>
            </div>

            <div className="flex items-end justify-between gap-2">
              <span className="truncate text-lg leading-tight font-bold transition-all duration-300 sm:text-xl lg:text-2xl">{uptime}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {usersData && (
        <>
          {/* Users Overview */}
          <div className={cn('animate-fade-in h-full w-full', 'sm:col-span-2')} style={{ animationDuration: '600ms', animationDelay: '550ms' }}>
            <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
              <div
                className={cn(
                  'from-primary/10 absolute inset-0 bg-gradient-to-r to-transparent opacity-0 transition-opacity duration-500',
                  'dark:from-primary/5 dark:to-transparent',
                  'group-hover:opacity-100',
                )}
              />
              <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
                <div className="mb-2 flex items-start justify-between sm:mb-3">
                  <div className="flex items-center gap-2 sm:gap-3">
                    <div className="bg-primary/10 rounded-lg p-1.5 sm:p-2">
                      <Users className="text-primary h-4 w-4 sm:h-5 sm:w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-muted-foreground truncate text-xs font-medium sm:text-sm">{t('statistics.users')}</p>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-3">
                  <div className="bg-background/60 rounded-lg border p-3 sm:p-4">
                    <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium sm:gap-2 sm:text-sm">
                      <Users className="text-primary h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span>{t('statistics.users')}</span>
                    </div>
                    <span dir="ltr" className="text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                      {totalUsers}
                    </span>
                  </div>

                  <div className="bg-background/60 rounded-lg border p-3 sm:p-4">
                    <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium sm:gap-2 sm:text-sm">
                      <UserCheck className="text-primary h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span>{t('statistics.activeUsers')}</span>
                    </div>
                    <div className="flex items-end justify-between gap-2">
                      <span dir="ltr" className="text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                        {activeUsers}
                      </span>
                      {totalUsers > 0 && (
                        <span dir="ltr" className="bg-muted/60 text-muted-foreground rounded-md px-1.5 py-1 text-xs font-medium whitespace-nowrap sm:px-2">
                          {activeUsersPercent.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="bg-background/60 rounded-lg border p-3 sm:col-span-2 sm:p-4 lg:col-span-1">
                    <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium sm:gap-2 sm:text-sm">
                      <Wifi className="text-primary h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span>{t('statistics.onlineUsers')}</span>
                    </div>
                    <div className="flex items-end justify-between gap-2">
                      <span dir="ltr" className="text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                        {onlineUsers}
                      </span>
                      {activeUsers > 0 && (
                        <span dir="ltr" className="bg-muted/60 text-muted-foreground rounded-md px-1.5 py-1 text-xs font-medium whitespace-nowrap sm:px-2">
                          {onlineUsersPercent.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

export default DashboardStatistics
