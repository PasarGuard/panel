import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CircleCheck, CircleX, Gauge, Loader2 } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { CoreEditorFormDialog } from '@/features/core-editor/components/shared/core-editor-form-dialog'
import { NodeOutboundLatency, NodeStatus, nodeOutboundsLatency, useGetNodes } from '@/service/api'
import dayjs from '@/lib/dayjs'
import { dateUtils } from '@/utils/dateFormatter'
import { cn } from '@/lib/utils'

interface OutboundLatencyTestDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scope: { mode: 'single'; outboundTag: string } | { mode: 'all' } | null
  coreId: number | null
}

type LatencyHealth = 'ok' | 'down'

const getLatencyHealth = (item: NodeOutboundLatency): LatencyHealth => {
  if (!item.alive || item.delay < 0) return 'down'
  return 'ok'
}

const getLatencyClassName = (health: LatencyHealth) => {
  return health === 'ok' ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300' : 'border-destructive/30 bg-destructive/10 text-destructive'
}

const formatTimestamp = (timestamp: number, t: (key: string, options?: Record<string, unknown>) => string) => {
  if (!timestamp) return t('never', { defaultValue: 'Never' })
  return `${dayjs.unix(timestamp).fromNow()} (${dateUtils.formatDate(timestamp)})`
}

const getErrorMessage = (error: unknown, fallback: string) => {
  if (!error || typeof error !== 'object') return fallback
  const maybeError = error as { data?: { detail?: string }; message?: string }
  return maybeError.data?.detail || maybeError.message || fallback
}

export function OutboundLatencyTestDialog({ open, onOpenChange, scope, coreId }: OutboundLatencyTestDialogProps) {
  const { t } = useTranslation()
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [timeoutInput, setTimeoutInput] = useState('5')
  const [latencies, setLatencies] = useState<NodeOutboundLatency[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const { data: nodesResponse, isLoading: isLoadingNodes } = useGetNodes(
    {
      status: NodeStatus.connected,
      core_id: coreId ?? undefined,
      limit: 1000,
      offset: 0,
    },
    {
      query: {
        enabled: open && coreId !== null,
        refetchOnWindowFocus: false,
        staleTime: 5000,
      },
    },
  )

  const nodes = useMemo(() => {
    if (coreId === null) return []
    const list = nodesResponse?.nodes ?? []
    return [...list].sort((a, b) => Number(a.id) - Number(b.id))
  }, [coreId, nodesResponse?.nodes])
  const mode = scope?.mode ?? 'single'
  const isSingleMode = mode === 'single'
  const outboundTag = scope?.mode === 'single' ? scope.outboundTag : ''
  const scopeLabel = isSingleMode
    ? outboundTag || t('coreEditor.outbound.latency.untagged', { defaultValue: 'Untagged outbound' })
    : t('coreEditor.outbound.latency.allOutbounds', { defaultValue: 'All outbounds' })

  useEffect(() => {
    if (!open) return
    if (selectedNodeId && nodes.some(node => String(node.id) === selectedNodeId)) return
    setSelectedNodeId(nodes[0] ? String(nodes[0].id) : '')
  }, [nodes, open, selectedNodeId])

  useEffect(() => {
    if (!open) {
      setLatencies([])
      setErrorMessage(null)
      setIsTesting(false)
    }
  }, [open])

  const sortedLatencies = useMemo(
    () =>
      [...latencies].sort((a, b) => {
        if (a.alive !== b.alive) return a.alive ? -1 : 1
        return (a.delay < 0 ? Number.MAX_SAFE_INTEGER : a.delay) - (b.delay < 0 ? Number.MAX_SAFE_INTEGER : b.delay)
      }),
    [latencies],
  )

  const aliveCount = sortedLatencies.filter(item => item.alive).length
  const averageDelay = useMemo(() => {
    const aliveItems = sortedLatencies.filter(item => item.alive && item.delay >= 0)
    if (!aliveItems.length) return null
    return Math.round(aliveItems.reduce((sum, item) => sum + item.delay, 0) / aliveItems.length)
  }, [sortedLatencies])

  const runTest = async () => {
    const nodeId = Number(selectedNodeId)
    if (!Number.isFinite(nodeId) || nodeId <= 0) return

    setIsTesting(true)
    setErrorMessage(null)
    try {
      const parsedTimeout = Number(timeoutInput)
      const response = await nodeOutboundsLatency(nodeId, {
        ...(isSingleMode ? { name: outboundTag } : {}),
        timeout: Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : undefined,
      })
      setLatencies(response.latencies ?? [])
    } catch (error) {
      setLatencies([])
      setErrorMessage(
        getErrorMessage(
          error,
          t('coreEditor.outbound.latency.errorDescription', {
            defaultValue: 'Unable to retrieve outbound latency for this node.',
          }),
        ),
      )
    } finally {
      setIsTesting(false)
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    runTest()
  }

  const isNewCore = coreId === null
  const noConnectedNodes = !isLoadingNodes && (isNewCore || nodes.length === 0)
  const canTest = !isLoadingNodes && !noConnectedNodes && !!selectedNodeId && !isTesting

  return (
    <CoreEditorFormDialog
      isDialogOpen={open}
      onOpenChange={onOpenChange}
      title={t('coreEditor.outbound.latency.title', { defaultValue: 'Test outbound latency' })}
      leadingIcon={<Gauge className="h-5 w-5 shrink-0" />}
      size="lg"
      inlinePersistValidation={false}
      footerExtra={
        <Button type="submit" form="outbound-latency-test-form" disabled={!canTest}>
          {isTesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Gauge className="h-4 w-4" />}
          <span>{isSingleMode ? t('coreEditor.outbound.latency.test', { defaultValue: 'Test' }) : t('coreEditor.outbound.latency.testAll', { defaultValue: 'Test all' })}</span>
        </Button>
      }
    >
      <div className="space-y-4">
        {!isSingleMode ? (
          <div className="bg-muted/20 rounded-md border px-3 py-2 text-sm">
            <span className="text-muted-foreground">{t('coreEditor.outbound.latency.outbound', { defaultValue: 'Outbound' })}</span>
            <span className="text-muted-foreground mx-2">/</span>
            <span dir="ltr">{scopeLabel}</span>
          </div>
        ) : null}

        <form id="outbound-latency-test-form" onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_160px]">
          <div className="flex min-w-0 flex-col gap-2">
            <Label>{t('coreEditor.outbound.latency.node', { defaultValue: 'Connected node' })}</Label>
            <Select value={selectedNodeId} onValueChange={setSelectedNodeId} disabled={isLoadingNodes || noConnectedNodes || isTesting}>
              <SelectTrigger className="h-10 min-w-0" dir="ltr">
                <SelectValue placeholder={isLoadingNodes ? t('loading') : t('coreEditor.outbound.latency.selectNode', { defaultValue: 'Select a connected node' })} />
              </SelectTrigger>
              <SelectContent>
                {nodes.map(node => (
                  <SelectItem key={node.id} value={String(node.id)}>
                    <span dir="ltr">{node.name}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <Label>{t('coreEditor.outbound.latency.timeout', { defaultValue: 'Timeout' })}</Label>
            <Input className="h-10" value={timeoutInput} onChange={event => setTimeoutInput(event.target.value)} inputMode="numeric" type="number" min={1} disabled={isTesting} dir="ltr" />
          </div>
        </form>

        {noConnectedNodes && (
          <Alert>
            <AlertDescription>
              {coreId
                ? t('coreEditor.outbound.latency.noConnectedNodesForCore', { defaultValue: 'No connected nodes are using this core.' })
                : t('coreEditor.outbound.latency.saveCoreFirst', { defaultValue: 'Save this core and connect a node to it before testing outbound latency.' })}
            </AlertDescription>
          </Alert>
        )}

        {!isSingleMode ? (
          <div className="grid overflow-hidden rounded-md border sm:grid-cols-3">
            <div className="border-b p-3 sm:border-e sm:border-b-0">
              <div className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">{t('coreEditor.outbound.latency.total', { defaultValue: 'Total' })}</div>
              <div className="mt-1 text-lg font-semibold tabular-nums">{sortedLatencies.length}</div>
            </div>
            <div className="border-b p-3 sm:border-e sm:border-b-0">
              <div className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">{t('coreEditor.outbound.latency.alive', { defaultValue: 'Alive' })}</div>
              <div className="mt-1 text-lg font-semibold tabular-nums">
                {aliveCount}/{sortedLatencies.length || 0}
              </div>
            </div>
            <div className="p-3">
              <div className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">{t('coreEditor.outbound.latency.average', { defaultValue: 'Average delay' })}</div>
              <div dir="ltr" className="mt-1 text-lg font-semibold tabular-nums">
                {averageDelay === null ? '-' : `${averageDelay} ms`}
              </div>
            </div>
          </div>
        ) : null}

        {errorMessage && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        )}

        <div>
          {isTesting && !sortedLatencies.length ? (
            <div className="flex min-h-48 items-center justify-center rounded-md border border-dashed">
              <div className="text-muted-foreground flex items-center gap-2 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                {isSingleMode
                  ? t('coreEditor.outbound.latency.loading', { defaultValue: 'Testing outbound...' })
                  : t('coreEditor.outbound.latency.loadingAll', { defaultValue: 'Testing outbounds...' })}
              </div>
            </div>
          ) : sortedLatencies.length ? (
            <div className="overflow-hidden rounded-md border">
              {sortedLatencies.map(item => {
                const health = getLatencyHealth(item)
                return (
                  <div key={`${item.name}-${item.source}-${item.link}`} className="border-b p-3 last:border-b-0">
                    <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div className="min-w-0 space-y-2">
                        <div className="flex min-w-0 flex-wrap items-center gap-2">
                          {item.alive ? <CircleCheck className="h-4 w-4 shrink-0 text-green-500" /> : <CircleX className="text-destructive h-4 w-4 shrink-0" />}
                          <span className="min-w-0 truncate text-sm font-semibold" dir="ltr">
                            {item.name}
                          </span>
                        </div>
                        {item.link && item.link !== item.name ? (
                          <div className="text-muted-foreground line-clamp-2 font-mono text-xs break-all" dir="ltr">
                            {item.link}
                          </div>
                        ) : null}
                      </div>
                      <Badge dir="ltr" variant="outline" className={cn('w-fit shrink-0 font-mono text-xs', getLatencyClassName(health))}>
                        {!item.alive || item.delay < 0 ? t('coreEditor.outbound.latency.unreachable', { defaultValue: 'Unreachable' }) : `${item.delay} ms`}
                      </Badge>
                    </div>

                    <Separator className="my-3" />

                    <div className="text-muted-foreground grid gap-2 text-xs sm:grid-cols-2">
                      <div className="min-w-0">
                        <span>{t('coreEditor.outbound.latency.lastTry', { defaultValue: 'Last try' })}: </span>
                        <span className="text-foreground" dir="ltr">
                          {formatTimestamp(item.last_try_time, t)}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <span>{t('coreEditor.outbound.latency.lastSeen', { defaultValue: 'Last seen' })}: </span>
                        <span className="text-foreground" dir="ltr">
                          {formatTimestamp(item.last_seen_time, t)}
                        </span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-muted-foreground flex min-h-48 items-center justify-center rounded-md border border-dashed px-4 text-center text-sm">
              {isSingleMode
                ? t('coreEditor.outbound.latency.empty', { defaultValue: 'Select a connected node and run the test.' })
                : t('coreEditor.outbound.latency.emptyAll', { defaultValue: 'Select a connected node and test all outbounds.' })}
            </div>
          )}
        </div>
      </div>
    </CoreEditorFormDialog>
  )
}
