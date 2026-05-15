import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DOCUMENTATION } from '@/constants/Project'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { useGetWorkersHealth } from '@/service/api'
import { ChevronDown, ChevronRight, Clock, HelpCircle, Server, ServerCog } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

type WorkerStatusVariant = 'green' | 'yellow' | 'red' | 'blue' | 'blank'

const statusLabelMap: Record<string, { label: string; variant: WorkerStatusVariant }> = {
  healthy: { label: 'Healthy', variant: 'green' },
  ok: { label: 'Healthy', variant: 'green' },
  running: { label: 'Running', variant: 'green' },
  available: { label: 'Available', variant: 'green' },
  degraded: { label: 'Degraded', variant: 'yellow' },
  warning: { label: 'Warning', variant: 'yellow' },
  unavailable: { label: 'Unavailable', variant: 'red' },
  error: { label: 'Error', variant: 'red' },
  down: { label: 'Down', variant: 'red' },
}

const normalizeStatus = (status?: string) => (status || 'unknown').toLowerCase().trim()

const formatResponseTime = (value?: number | null) => {
  if (value === null || value === undefined) return '--'
  if (Number.isNaN(value)) return '--'
  return `${Math.round(value)} ms`
}

const dotClassMap: Record<WorkerStatusVariant, string> = {
  green: 'bg-emerald-500/80',
  yellow: 'bg-amber-500/80',
  red: 'bg-rose-500/80',
  blue: 'bg-blue-500/80',
  blank: 'bg-muted-foreground/40',
}

const WorkersHealthCard = () => {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const [pauseRefetch, setPauseRefetch] = useState(false)
  const [isCollapsed, setIsCollapsed] = useState(true)
  const { data, isLoading, isError } = useGetWorkersHealth({
    query: {
      refetchInterval: pauseRefetch ? false : 5000,
      retry: false,
    },
  })

  const scheduler = data?.scheduler
  const node = data?.node
  const schedulerStatus = normalizeStatus(scheduler?.status)
  const nodeStatus = normalizeStatus(node?.status)
  const schedulerMeta = statusLabelMap[schedulerStatus] ?? { label: scheduler?.status || 'Unknown', variant: 'blank' }
  const nodeMeta = statusLabelMap[nodeStatus] ?? { label: node?.status || 'Unknown', variant: 'blank' }
  const natsDisabled = [scheduler?.error, node?.error].some(error => error?.toLowerCase().includes('nats is disabled'))
  const workerHealthDocsUrl = useMemo(() => {
    const locale = i18n.resolvedLanguage || i18n.language || 'en'
    const normalizedLocale = locale.split('-')[0]
    return `${DOCUMENTATION}/${normalizedLocale}/learn/multi-worker/`
  }, [i18n.language, i18n.resolvedLanguage])
  const summaryStatus = useMemo(() => {
    if (!scheduler && !node) return { label: t('workersHealth.status.unknown', { defaultValue: 'Unknown' }), variant: 'blank' as WorkerStatusVariant }
    if (schedulerStatus === 'unavailable' || nodeStatus === 'unavailable') return { label: t('workersHealth.status.unavailable', { defaultValue: 'Unavailable' }), variant: 'red' as WorkerStatusVariant }
    if (schedulerStatus === 'degraded' || nodeStatus === 'degraded' || schedulerStatus === 'warning' || nodeStatus === 'warning') {
      return { label: t('workersHealth.status.degraded', { defaultValue: 'Degraded' }), variant: 'yellow' as WorkerStatusVariant }
    }
    if (schedulerStatus === 'error' || nodeStatus === 'error' || schedulerStatus === 'down' || nodeStatus === 'down') {
      return { label: t('workersHealth.status.error', { defaultValue: 'Error' }), variant: 'red' as WorkerStatusVariant }
    }
    return { label: t('workersHealth.status.healthy', { defaultValue: 'Healthy' }), variant: 'green' as WorkerStatusVariant }
  }, [node, nodeStatus, scheduler, schedulerStatus, t])

  const isUnavailable = schedulerStatus === 'unavailable' || nodeStatus === 'unavailable'
  const workersDisabled = schedulerStatus === 'disabled' && nodeStatus === 'disabled'

  useEffect(() => {
    if (!pauseRefetch && isUnavailable) {
      setPauseRefetch(true)
    }
  }, [isUnavailable, pauseRefetch])

  if (!isLoading && !isError && workersDisabled) return null

  return (
    <Card className="border bg-card/80" dir={dir}>
      <CardHeader className="p-2">
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-2 text-left sm:items-center p-2">
            <div className="rounded-md bg-primary/10 p-1.5">
              <ServerCog className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0">
              <div className={cn('flex items-center gap-1', dir === 'rtl' && 'justify-end')}>
                <CardTitle className={cn(dir === 'rtl' && 'text-right', 'truncate text-sm font-semibold')}>{t('workersHealth.title', { defaultValue: 'Workers Health' })}</CardTitle>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <a
                        href={workerHealthDocsUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md border-0 text-primary transition-colors hover:border-2 hover:border-primary/40 hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        aria-label={t('tutorial', { defaultValue: 'View tutorial' })}
                      >
                        <HelpCircle className="h-4 w-4" />
                      </a>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>{t('tutorial', { defaultValue: 'View tutorial' })}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <p className="truncate text-xs text-muted-foreground">{t('workersHealth.subtitle', { defaultValue: 'Scheduler and node worker status' })}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            className="h-auto w-full px-2 py-2 sm:w-auto"
            onClick={() => setIsCollapsed(prev => !prev)}
            aria-label={t('workersHealth.toggle', { defaultValue: 'Toggle details' })}
          >
            <div className="flex w-full items-center justify-between gap-2 text-xs text-muted-foreground sm:justify-end">
              <div className="flex items-center gap-2">
                <Badge variant={summaryStatus.variant}>{summaryStatus.label}</Badge>
                <div className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  <span dir="ltr">{formatResponseTime(scheduler?.response_time_ms ?? node?.response_time_ms ?? null)}</span>
                </div>
              </div>
              {isCollapsed ? <ChevronRight className={cn('h-4 w-4', dir === 'rtl' && 'rotate-180')} /> : <ChevronDown className="h-4 w-4" />}
            </div>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-4">
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            {!isCollapsed && <Skeleton className="h-8 w-full" />}
          </div>
        ) : isError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {t('workersHealth.error', { defaultValue: 'Unable to load worker health.' })}
          </div>
        ) : (
          <div className="space-y-2">
            {isCollapsed ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-1">
                    <span className={cn('h-2 w-2 rounded-full', dotClassMap[schedulerMeta.variant])} />
                    <span className="text-muted-foreground">{t('workersHealth.scheduler', { defaultValue: 'Scheduler' })}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className={cn('h-2 w-2 rounded-full', dotClassMap[nodeMeta.variant])} />
                    <span className="text-muted-foreground">{t('workersHealth.node', { defaultValue: 'Node Worker' })}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs">
                  <div className="flex items-center gap-2">
                    <ServerCog className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium">{t('workersHealth.scheduler', { defaultValue: 'Scheduler' })}</span>
                    <Badge variant={schedulerMeta.variant}>{t(`workersHealth.status.${schedulerStatus}`, { defaultValue: schedulerMeta.label })}</Badge>
                  </div>
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <Clock className="h-3.5 w-3.5" />
                    <span dir="ltr">{formatResponseTime(scheduler?.response_time_ms)}</span>
                  </div>
                </div>
                {scheduler?.error && <div className="px-1 text-xs text-muted-foreground">{scheduler.error}</div>}

                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs">
                  <div className="flex items-center gap-2">
                    <Server className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium">{t('workersHealth.node', { defaultValue: 'Node Worker' })}</span>
                    <Badge variant={nodeMeta.variant}>{t(`workersHealth.status.${nodeStatus}`, { defaultValue: nodeMeta.label })}</Badge>
                  </div>
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <Clock className="h-3.5 w-3.5" />
                    <span dir="ltr">{formatResponseTime(node?.response_time_ms)}</span>
                  </div>
                </div>
                {node?.error && <div className="px-1 text-xs text-muted-foreground">{node.error}</div>}
              </div>
            )}
          </div>
        )}

        {natsDisabled && (
          <div className={cn('rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700', 'dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200')}>
            {t('workersHealth.natsDisabled', { defaultValue: 'NATS is disabled. Worker health checks are unavailable.' })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default WorkersHealthCard
