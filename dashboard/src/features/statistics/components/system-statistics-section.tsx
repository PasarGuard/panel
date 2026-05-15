import { Card, CardContent } from '@/components/ui/card'
import { SystemStats, NodeRealtimeStats } from '@/service/api'
import { useTranslation } from 'react-i18next'
import { Clock3, Cpu, MemoryStick, HardDrive, Database, Upload, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { formatBytes } from '@/utils/formatByte'
import { formatDuration } from '@/utils/formatDuration'
import { CircularProgress } from '@/components/ui/circular-progress'

interface SystemStatisticsSectionProps {
  currentStats?: SystemStats | NodeRealtimeStats | null
}

export default function SystemStatisticsSection({ currentStats }: SystemStatisticsSectionProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  const formatMbpsPair = (bytesPerSecond: number, decimals = 1) => {
    const mbps = (bytesPerSecond * 8) / (1024 * 1024)
    const mbpsText = mbps.toFixed(decimals).replace(/\.0$/, '')
    const mbPerSec = bytesPerSecond / (1024 * 1024)
    const mbPerSecText = mbPerSec.toFixed(decimals).replace(/\.0$/, '')

    return { mbpsText, mbPerSecText }
  }

  // Helper to check if stats are from a node (realtime stats)
  const isNodeStats = (stats: SystemStats | NodeRealtimeStats): stats is NodeRealtimeStats => {
    return 'incoming_bandwidth_speed' in stats
  }

  const getTotalTrafficValue = () => {
    if (!currentStats) return 0

    if (isNodeStats(currentStats)) {
      // Node stats - use bandwidth speed
      return Number(currentStats.incoming_bandwidth_speed) + Number(currentStats.outgoing_bandwidth_speed)
    } else {
      // Master server stats - use total traffic
      return Number(currentStats.incoming_bandwidth) + Number(currentStats.outgoing_bandwidth)
    }
  }

  const getIncomingBandwidth = () => {
    if (!currentStats) return 0

    if (isNodeStats(currentStats)) {
      return Number(currentStats.incoming_bandwidth_speed) || 0
    } else {
      return Number(currentStats.incoming_bandwidth) || 0
    }
  }

  const getOutgoingBandwidth = () => {
    if (!currentStats) return 0

    if (isNodeStats(currentStats)) {
      return Number(currentStats.outgoing_bandwidth_speed) || 0
    } else {
      return Number(currentStats.outgoing_bandwidth) || 0
    }
  }

  const getMemoryUsage = () => {
    if (!currentStats) return { used: 0, total: 0, percentage: 0 }

    const memUsed = Number(currentStats.mem_used) || 0
    const memTotal = Number(currentStats.mem_total) || 0
    const percentage = memTotal > 0 ? (memUsed / memTotal) * 100 : 0

    return { used: memUsed, total: memTotal, percentage }
  }

  const getDiskUsage = () => {
    if (!currentStats || isNodeStats(currentStats)) return { used: 0, total: 0, percentage: 0 }

    const diskUsed = Number(currentStats.disk_used) || 0
    const diskTotal = Number(currentStats.disk_total) || 0
    const percentage = diskTotal > 0 ? (diskUsed / diskTotal) * 100 : 0

    return { used: diskUsed, total: diskTotal, percentage }
  }

  const getCpuInfo = () => {
    if (!currentStats) return { usage: 0, cores: 0 }

    let cpuUsage = Number(currentStats.cpu_usage) || 0
    const cpuCores = Number(currentStats.cpu_cores) || 0

    // CPU usage is already in percentage (0-100), no need to multiply
    // Just ensure it's within reasonable bounds
    cpuUsage = Math.min(Math.max(cpuUsage, 0), 100)

    return { usage: Math.round(cpuUsage * 10) / 10, cores: cpuCores } // Round to 1 decimal place
  }

  const getUptimeSeconds = () => {
    if (!currentStats) return null

    return isNodeStats(currentStats) ? currentStats.uptime : currentStats.uptime_seconds
  }

  const memory = getMemoryUsage()
  const disk = getDiskUsage()
  const cpu = getCpuInfo()
  const memoryPercent = Math.min(Math.max(memory.percentage, 0), 100)
  const diskPercent = Math.min(Math.max(disk.percentage, 0), 100)
  const nodeStatsMode = !!currentStats && isNodeStats(currentStats)
  const incomingSpeed = formatMbpsPair(getIncomingBandwidth() || 0)
  const outgoingSpeed = formatMbpsPair(getOutgoingBandwidth() || 0)
  const uptimeSeconds = getUptimeSeconds()
  const uptime = uptimeSeconds !== null ? formatDuration(uptimeSeconds, t) : null

  return (
    <div
      className={cn(
        'grid h-full w-full gap-3 sm:gap-4 lg:gap-6',
        // Responsive grid: 1 column on mobile, 2 columns on tablet/desktop
        'grid-cols-1 sm:grid-cols-2',
        // Ensure equal height for all cards
        'auto-rows-fr',
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
                  <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.cpuUsage')}</p>
                </div>
              </div>
              <CircularProgress value={cpu.usage} size={38} strokeWidth={4} showValue={false} className="shrink-0 opacity-90" />
            </div>

            <div className="flex items-end justify-between gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
                <span dir="ltr" className="text-xl font-bold leading-tight transition-all duration-300 sm:text-2xl lg:text-3xl">
                  {cpu.usage}%
                </span>
              </div>

              {cpu.cores > 0 && (
                <div className="flex shrink-0 items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-xs text-muted-foreground sm:px-2 sm:text-sm">
                  <Cpu className="h-3 w-3" />
                  <span className="font-medium sm:whitespace-nowrap">
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
                  <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.ramUsage')}</p>
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
              <span dir="ltr" className="whitespace-nowrap rounded-md bg-muted/60 px-1.5 py-1 text-xs font-medium text-muted-foreground sm:px-2">
                {memoryPercent.toFixed(1)}%
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Disk Usage (All Nodes / master view) */}
      {!nodeStatsMode && (
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
                    <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.diskUsage')}</p>
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
                <span dir="ltr" className="whitespace-nowrap rounded-md bg-muted/60 px-1.5 py-1 text-xs font-medium text-muted-foreground sm:px-2">
                  {diskPercent.toFixed(1)}%
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {nodeStatsMode ? (
        <>
          {/* Uplink */}
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
                      <Upload className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.uplink')}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-end justify-between gap-2">
                  <span dir="ltr" className="truncate text-lg font-bold transition-all duration-300 sm:text-xl lg:text-2xl">
                    <span className="whitespace-nowrap">{outgoingSpeed.mbPerSecText} MB/s</span>
                  </span>
                  <span dir="ltr" className="whitespace-nowrap rounded-md bg-muted/60 px-1.5 py-1 text-xs font-medium text-muted-foreground sm:px-2">
                    {outgoingSpeed.mbpsText} Mb/s
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Downlink */}
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
                      <Download className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.downlink')}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-end justify-between gap-2">
                  <span dir="ltr" className="truncate text-lg font-bold transition-all duration-300 sm:text-xl lg:text-2xl">
                    <span className="whitespace-nowrap">{incomingSpeed.mbPerSecText} MB/s</span>
                  </span>
                  <span dir="ltr" className="whitespace-nowrap rounded-md bg-muted/60 px-1.5 py-1 text-xs font-medium text-muted-foreground sm:px-2">
                    {incomingSpeed.mbpsText} Mb/s
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Node Uptime */}
          <div className="h-full w-full animate-fade-in sm:col-span-2" style={{ animationDuration: '600ms', animationDelay: '450ms' }}>
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
                      <Clock3 className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.uptime')}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-end justify-between gap-2">
                  <span className="truncate text-lg font-bold leading-tight transition-all duration-300 sm:text-xl lg:text-2xl">
                    {uptime}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <>
          {/* Total Traffic */}
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
                      <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.totalTraffic')}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-end justify-between gap-2">
                  <div className={cn(dir === 'rtl' && 'text-right', 'min-w-0 flex-1')} dir="ltr">
                    <span className="text-lg font-bold leading-tight sm:text-xl lg:text-2xl">{formatBytes(getTotalTrafficValue() || 0, 1)}</span>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-1.5 text-xs sm:gap-2">
                    <div className="inline-flex items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-green-600 dark:text-green-400">
                      <Download className="h-3 w-3" />
                      <span dir="ltr" className="whitespace-nowrap font-semibold">
                        {formatBytes(getIncomingBandwidth() || 0, 1)}
                      </span>
                    </div>
                    <div className="inline-flex items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-blue-600 dark:text-blue-400">
                      <Upload className="h-3 w-3" />
                      <span dir="ltr" className="whitespace-nowrap font-semibold">
                        {formatBytes(getOutgoingBandwidth() || 0, 1)}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Panel Uptime */}
          <div className="h-full w-full animate-fade-in sm:col-span-2" style={{ animationDuration: '600ms', animationDelay: '450ms' }}>
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
                      <Clock3 className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">{t('statistics.uptime')}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-end justify-between gap-2">
                  <span className="truncate text-lg font-bold leading-tight transition-all duration-300 sm:text-xl lg:text-2xl">
                    {uptime}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
