import { Card, CardContent } from '@/components/ui/card'
import { SystemStats, NodeRealtimeStats } from '@/service/api'
import { useTranslation } from 'react-i18next'
import { Cpu, MemoryStick, Database, Upload, Download, Activity } from 'lucide-react'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { formatBytes } from '@/utils/formatByte'
import { CircularProgress } from '@/components/ui/circular-progress'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

interface SystemStatisticsSectionProps {
  currentStats?: SystemStats | NodeRealtimeStats | null
}

interface SpeedValueHintProps {
  primary: string
  secondary: string
  className?: string
}

function SpeedValueHint({ primary, secondary, className }: SpeedValueHintProps) {
  return (
    <TooltipProvider delayDuration={120}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className="inline cursor-default rounded-sm p-0 text-left align-baseline">
            <span dir="ltr" className={className}>
              {primary}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent>{secondary}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
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

  const getCpuInfo = () => {
    if (!currentStats) return { usage: 0, cores: 0 }

    let cpuUsage = Number(currentStats.cpu_usage) || 0
    const cpuCores = Number(currentStats.cpu_cores) || 0

    // CPU usage is already in percentage (0-100), no need to multiply
    // Just ensure it's within reasonable bounds
    cpuUsage = Math.min(Math.max(cpuUsage, 0), 100)

    return { usage: Math.round(cpuUsage * 10) / 10, cores: cpuCores } // Round to 1 decimal place
  }

  const memory = getMemoryUsage()
  const cpu = getCpuInfo()
  const memoryPercent = Math.min(Math.max(memory.percentage, 0), 100)
  const totalSpeed = formatMbpsPair(getTotalTrafficValue() || 0)
  const incomingSpeed = formatMbpsPair(getIncomingBandwidth() || 0)
  const outgoingSpeed = formatMbpsPair(getOutgoingBandwidth() || 0)

  return (
    <div
      className={cn(
        'grid h-full w-full gap-3 sm:gap-4 lg:gap-6',
        // Responsive grid: 1 column on mobile, 2 on small tablet, 3 on large tablet and desktop
        'grid-cols-1 sm:grid-cols-2 xl:grid-cols-3',
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

            <div className="flex items-center gap-1 sm:gap-2">
              <span dir="ltr" className="text-base font-bold leading-tight transition-all duration-300 sm:text-xl lg:text-2xl">
                {currentStats ? (
                  <span className="whitespace-normal sm:whitespace-nowrap">
                    {formatBytes(memory.used, 1, false, false, 'GB')}/{formatBytes(memory.total, 1, true, false, 'GB')}
                    <span className="ml-1 text-sm font-medium text-muted-foreground">({memoryPercent.toFixed(1)}%)</span>
                  </span>
                ) : (
                  0
                )}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Total Traffic / Network Speed (depends on whether it's master or node stats) */}
      <div className="h-full w-full animate-fade-in sm:col-span-2 lg:col-span-1" style={{ animationDuration: '600ms', animationDelay: '250ms' }}>
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
                  {currentStats && isNodeStats(currentStats) ? <Activity className="h-4 w-4 text-primary sm:h-5 sm:w-5" /> : <Database className="h-4 w-4 text-primary sm:h-5 sm:w-5" />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium leading-tight text-muted-foreground sm:truncate sm:text-sm">
                    {currentStats && isNodeStats(currentStats) ? t('statistics.networkSpeed') : t('statistics.totalTraffic')}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-end justify-between gap-2">
              <div className={cn(dir === "rtl" && "text-right", "min-w-0 flex-1")} dir="ltr">
                {currentStats && isNodeStats(currentStats) ? (
                  <SpeedValueHint
                    primary={`${totalSpeed.mbPerSecText} MB/s`}
                    secondary={`${totalSpeed.mbpsText} Mb/s`}
                    className="inline-block whitespace-nowrap text-xl font-bold leading-tight sm:text-2xl lg:text-3xl"
                  />
                ) : (
                  <span className="text-xl font-bold leading-tight sm:text-2xl lg:text-3xl">{formatBytes(getTotalTrafficValue() || 0, 1)}</span>
                )}
              </div>

              {/* Incoming/Outgoing Details */}
              <div className="flex shrink-0 flex-wrap items-center gap-1.5 text-xs sm:gap-2">
                <div className="inline-flex items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-green-600 dark:text-green-400">
                  <Download className="h-3 w-3" />
                  {currentStats && isNodeStats(currentStats) ? (
                    <SpeedValueHint primary={`${incomingSpeed.mbPerSecText} MB/s`} secondary={`${incomingSpeed.mbpsText} Mb/s`} className="whitespace-nowrap font-semibold" />
                  ) : (
                    <span dir="ltr" className="whitespace-nowrap font-semibold">{formatBytes(getIncomingBandwidth() || 0, 1)}</span>
                  )}
                </div>
                <div className="inline-flex items-center gap-1 rounded-md bg-muted/50 px-1.5 py-1 text-blue-600 dark:text-blue-400">
                  <Upload className="h-3 w-3" />
                  {currentStats && isNodeStats(currentStats) ? (
                    <SpeedValueHint primary={`${outgoingSpeed.mbPerSecText} MB/s`} secondary={`${outgoingSpeed.mbpsText} Mb/s`} className="whitespace-nowrap font-semibold" />
                  ) : (
                    <span dir="ltr" className="whitespace-nowrap font-semibold">{formatBytes(getOutgoingBandwidth() || 0, 1)}</span>
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
