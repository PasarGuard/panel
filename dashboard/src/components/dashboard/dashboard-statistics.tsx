import { Skeleton } from '@/components/ui/skeleton'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { SystemStats } from '@/service/api'
import { formatBytes } from '@/utils/formatByte'
import { Cpu, Database, Download, HardDrive, MemoryStick, Upload, UserCheck, Users, Wifi } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { CircularProgress } from '../ui/circular-progress'
import { Card, CardContent } from '../ui/card'

const DashboardStatistics = ({ systemData }: { systemData: SystemStats | undefined }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  // Show skeleton loader while data is being fetched
  if (!systemData) {
    return (
      <div className={cn('grid h-full w-full gap-3 sm:gap-4 lg:gap-6', 'grid-cols-1 sm:grid-cols-2', dir === 'rtl' && 'lg:grid-flow-col-reverse')}>
        {[...Array(5)].map((_, i) => (
          <Card key={i} className={cn('h-full overflow-hidden border', i === 4 && 'sm:col-span-2')}>
            <CardContent className="flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
              <div className="mb-2 flex items-start justify-between sm:mb-3">
                <div className="flex items-center gap-2 sm:gap-3">
                  <Skeleton className="h-7 w-7 rounded-lg sm:h-9 sm:w-9" />
                  <Skeleton className="h-4 w-24 sm:h-5" />
                </div>
              </div>
              {i === 4 ? (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 sm:gap-3">
                  {[...Array(3)].map((_, metricIndex) => (
                    <div key={metricIndex} className="rounded-lg border bg-background/60 p-3 sm:p-4">
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
    if (!systemData) return 0

    // For master server stats - use total traffic
    return Number(systemData.incoming_bandwidth) + Number(systemData.outgoing_bandwidth)
  }

  const getIncomingBandwidth = () => {
    if (!systemData) return 0
    return Number(systemData.incoming_bandwidth) || 0
  }

  const getOutgoingBandwidth = () => {
    if (!systemData) return 0
    return Number(systemData.outgoing_bandwidth) || 0
  }

  const getMemoryUsage = () => {
    if (!systemData) return { used: 0, total: 0, percentage: 0 }

    const memUsed = Number(systemData.mem_used) || 0
    const memTotal = Number(systemData.mem_total) || 0
    const percentage = memTotal > 0 ? (memUsed / memTotal) * 100 : 0

    return { used: memUsed, total: memTotal, percentage }
  }

  const getDiskUsage = () => {
    if (!systemData) return { used: 0, total: 0, percentage: 0 }

    const diskUsed = Number(systemData.disk_used) || 0
    const diskTotal = Number(systemData.disk_total) || 0
    const percentage = diskTotal > 0 ? (diskUsed / diskTotal) * 100 : 0

    return { used: diskUsed, total: diskTotal, percentage }
  }

  const getCpuInfo = () => {
    if (!systemData) return { usage: 0, cores: 0 }

    let cpuUsage = Number(systemData.cpu_usage) || 0
    const cpuCores = Number(systemData.cpu_cores) || 0

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
  const totalUsers = Number(systemData.total_user) || 0
  const activeUsers = Number(systemData.active_users) || 0
  const onlineUsers = Number(systemData.online_users) || 0
  const activeUsersPercent = totalUsers > 0 ? Math.min(Math.max((activeUsers / totalUsers) * 100, 0), 100) : 0
  const onlineUsersPercent = totalUsers > 0 ? Math.min(Math.max((onlineUsers / totalUsers) * 100, 0), 100) : 0

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
      <div className="h-full w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '50ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="rounded-lg bg-primary/10 p-1.5 sm:p-2">
                  <Cpu className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-muted-foreground sm:text-sm">{t('statistics.cpuUsage')}</p>
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
                <div className="flex shrink-0 items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-xs text-muted-foreground sm:px-2 sm:text-sm">
                  <Cpu className="h-3 w-3 text-primary" />
                  <span className="whitespace-nowrap font-medium">
                    {cpu.cores} {t('statistics.cores')}
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Memory Usage */}
      <div className="h-full w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '150ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="rounded-lg bg-primary/10 p-1.5 sm:p-2">
                  <MemoryStick className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-muted-foreground sm:text-sm">{t('statistics.ramUsage')}</p>
                </div>
              </div>
              <CircularProgress value={memoryPercent} size={38} strokeWidth={4} showValue={false} className="shrink-0 opacity-90" />
            </div>

            <div className="flex items-center gap-1 sm:gap-2">
              <span dir="ltr" className="truncate text-lg font-bold transition-all duration-300 sm:text-xl lg:text-2xl">
                <span className="whitespace-nowrap">
                  {formatBytes(memory.used, 1, false, false, 'GB')}/{formatBytes(memory.total, 1, true, false, 'GB')}
                  <span className="ml-1 text-sm font-medium text-muted-foreground">({memoryPercent.toFixed(1)}%)</span>
                </span>
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Disk Usage */}
      <div className="h-full w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '250ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="rounded-lg bg-primary/10 p-1.5 sm:p-2">
                  <HardDrive className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-muted-foreground sm:text-sm">
                    {t('statistics.diskUsage', { defaultValue: 'Disk Usage' })}
                  </p>
                </div>
              </div>
              <CircularProgress value={diskPercent} size={38} strokeWidth={4} showValue={false} className="shrink-0 opacity-90" />
            </div>

            <div className="flex items-center gap-1 sm:gap-2">
              <span dir="ltr" className="truncate text-lg font-bold transition-all duration-300 sm:text-xl lg:text-2xl">
                <span className="whitespace-nowrap">
                  {formatBytes(disk.used, 1, false, false, 'GB')}/{formatBytes(disk.total, 1, true, false, 'GB')}
                  <span className="ml-1 text-sm font-medium text-muted-foreground">({diskPercent.toFixed(1)}%)</span>
                </span>
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Total Traffic with Incoming/Outgoing Details */}
      <div className="h-full w-full animate-fade-in" style={{ animationDuration: '600ms', animationDelay: '350ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="rounded-lg bg-primary/10 p-1.5 sm:p-2">
                  <Database className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-muted-foreground sm:text-sm">{t('statistics.totalTraffic')}</p>
                </div>
              </div>
            </div>

            <div className="flex items-end justify-between gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
                <span dir="ltr" className="truncate text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                  {formatBytes(getTotalTrafficValue() || 0, 1)}
                </span>
              </div>

              {/* Incoming/Outgoing Details */}
              <div className="flex shrink-0 items-center gap-2 text-xs">
                <div className="flex items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-green-600 dark:text-green-400">
                  <Download className="h-3 w-3" />
                  <span dir="ltr" className="font-medium">
                    {formatBytes(getIncomingBandwidth() || 0, 1)}
                  </span>
                </div>
                <div className="flex items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-blue-600 dark:text-blue-400">
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

      {/* Users Overview */}
      <div className={cn('h-full w-full animate-fade-in', 'sm:col-span-2')} style={{ animationDuration: '600ms', animationDelay: '450ms' }}>
        <Card dir={dir} className="group relative h-full w-full overflow-hidden rounded-lg border transition-all duration-300 hover:shadow-lg">
          <div
            className={cn(
              'absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-500',
              'dark:from-primary/5 dark:to-transparent',
              'group-hover:opacity-100',
            )}
          />
          <CardContent className="relative z-10 flex h-full flex-col justify-between p-4 sm:p-5 lg:p-6">
            <div className="mb-2 flex items-start justify-between sm:mb-3">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="rounded-lg bg-primary/10 p-1.5 sm:p-2">
                  <Users className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-muted-foreground sm:text-sm">{t('statistics.users')}</p>
                </div>
              </div>
              {totalUsers > 0 && (
                <div dir="ltr" className="shrink-0 rounded-md bg-muted/60 px-2 py-1 text-xs font-medium text-muted-foreground sm:text-sm">
                  {activeUsersPercent.toFixed(1)}%
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 sm:gap-3">
              <div className="rounded-lg border bg-background/60 p-3 sm:p-4">
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground sm:gap-2 sm:text-sm">
                  <Users className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
                  <span>{t('statistics.users')}</span>
                </div>
                <span dir="ltr" className="text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                  {totalUsers}
                </span>
              </div>

              <div className="rounded-lg border bg-background/60 p-3 sm:p-4">
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground sm:gap-2 sm:text-sm">
                  <UserCheck className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
                  <span>{t('statistics.activeUsers')}</span>
                </div>
                <div className="flex items-end justify-between gap-2">
                  <span dir="ltr" className="text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                    {activeUsers}
                  </span>
                  {totalUsers > 0 && (
                    <span dir="ltr" className="whitespace-nowrap rounded-md bg-muted/60 px-1.5 py-1 text-xs font-medium text-muted-foreground sm:px-2">
                      {activeUsersPercent.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>

              <div className="rounded-lg border bg-background/60 p-3 sm:p-4">
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground sm:gap-2 sm:text-sm">
                  <Wifi className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
                  <span>{t('statistics.onlineUsers')}</span>
                </div>
                <div className="flex items-end justify-between gap-2">
                  <span dir="ltr" className="text-xl font-bold transition-all duration-300 sm:text-2xl lg:text-3xl">
                    {onlineUsers}
                  </span>
                  {totalUsers > 0 && (
                    <span dir="ltr" className="whitespace-nowrap rounded-md bg-muted/60 px-1.5 py-1 text-xs font-medium text-muted-foreground sm:px-2">
                      {onlineUsersPercent.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default DashboardStatistics
