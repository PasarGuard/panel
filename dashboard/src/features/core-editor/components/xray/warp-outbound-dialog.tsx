import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Cloud, Gauge, Loader2, RefreshCw, Server } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { CoreEditorFormDialog } from '@/features/core-editor/components/shared/core-editor-form-dialog'
import { selectCoreEditorHasActualChanges } from '@/features/core-editor/kit/core-editor-change-state'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import {
  NodeStatus,
  getGetCurrentAdminUrl,
  getGetCurrentAdminQueryKey,
  getNodeOutboundsLatencyUrl,
  retryCoreWarp,
  useGetCoreWarp,
  type AdminDetails,
  type NodeOutboundsLatencyResponse,
  type WarpNodeResponse,
} from '@/service/api'
import { orvalFetcher } from '@/service/http'
import { hasPermission } from '@/utils/rbac'
import { cn } from '@/lib/utils'

interface WarpOutboundDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type TestResult = { alive: boolean; delay?: number; error?: string }

export function WarpOutboundDialog({ open, onOpenChange }: WarpOutboundDialogProps) {
  const { t } = useTranslation()
  const { data: admin } = useQuery({
    queryKey: getGetCurrentAdminQueryKey(),
    queryFn: ({ signal }) => orvalFetcher<AdminDetails>(getGetCurrentAdminUrl(), { signal }),
    staleTime: 5 * 60 * 1000,
  })
  const coreId = useCoreEditorStore(s => s.coreId)
  const tag = useCoreEditorStore(s => s.warpOutboundTag)
  const hasChanges = useCoreEditorStore(selectCoreEditorHasActualChanges)
  const [tagInput, setTagInput] = useState('warp')
  const [tagError, setTagError] = useState('')
  const [busy, setBusy] = useState<number | 'all' | null>(null)
  const [testing, setTesting] = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, TestResult>>({})
  const canUpdate = hasPermission(admin, 'cores', coreId === null ? 'create' : 'update')
  const canTest = hasPermission(admin, 'nodes', 'stats')
  const saved = coreId !== null && tag !== null && !hasChanges
  const { data, isLoading, isError, refetch } = useGetCoreWarp(coreId ?? 0, {
    query: { enabled: open && saved, refetchInterval: open && saved ? 5000 : false, refetchOnWindowFocus: false },
  })
  const nodes = data?.outbound_tag === tag ? data.nodes : []
  const applied = nodes.filter(n => n.status === 'applied').length

  useEffect(() => {
    if (!open) return
    setTagInput(tag ?? 'warp')
    setTagError('')
    setTestResults({})
  }, [open, tag])

  const addOutbound = () => {
    if (!canUpdate) return
    const value = tagInput.trim()
    const state = useCoreEditorStore.getState()
    if (!value || value.length > 256) {
      setTagError(t('coreEditor.warp.tagRequired'))
      return
    }
    if (state.xrayProfile?.outbounds?.some(o => o.tag === value)) {
      setTagError(t('coreEditor.warp.tagDuplicate'))
      return
    }
    if (!state.xrayProfile || state.warpOutboundTag) return
    // Credentials are substituted per node by the backend; the template safely blocks unresolved WARP.
    state.updateXrayProfile(p => ({ ...p, outbounds: [...(p.outbounds ?? []), { tag: value, protocol: 'blackhole', settings: {} }] }))
    state.setWarpOutboundTag(value)
    onOpenChange(false)
    toast.success(t('coreEditor.warp.added'))
  }

  const retry = async (nodeId?: number) => {
    if (!saved || coreId === null || busy !== null) return
    setBusy(nodeId ?? 'all')
    try {
      await retryCoreWarp(coreId, { node_id: nodeId })
      toast.success(t('coreEditor.warp.retryStarted'))
      await refetch()
    } catch {
      toast.error(t('coreEditor.warp.retryFailed'))
    } finally {
      setBusy(null)
    }
  }

  const test = async (node: WarpNodeResponse) => {
    if (!saved || !tag || testing !== null) return
    setTesting(node.node_id)
    try {
      const result = await orvalFetcher<NodeOutboundsLatencyResponse>(getNodeOutboundsLatencyUrl(node.node_id, { name: tag, timeout: 5 }))
      const latency = result.latencies.find(item => item.name === tag)
      setTestResults(prev => ({ ...prev, [node.node_id]: { alive: latency?.alive === true, delay: latency?.delay } }))
    } catch {
      setTestResults(prev => ({ ...prev, [node.node_id]: { alive: false, error: t('coreEditor.warp.testFailed') } }))
    } finally {
      setTesting(null)
    }
  }

  return (
    <CoreEditorFormDialog
      isDialogOpen={open}
      onOpenChange={onOpenChange}
      title={tag ? t('coreEditor.warp.manageTitle') : t('coreEditor.warp.addTitle')}
      leadingIcon={<Cloud className="h-5 w-5 shrink-0" />}
      size="lg"
      className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto]"
      inlinePersistValidation={false}
      footerExtra={
        !tag ? (
          <Button type="button" onClick={addOutbound} disabled={!canUpdate}>
            {t('coreEditor.warp.addButton')}
          </Button>
        ) : saved ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => retry()}
            disabled={!canUpdate || busy !== null || !nodes.some(n => n.node_status === NodeStatus.connected && n.status !== 'applied' && n.status !== 'registering')}
          >
            {busy === 'all' ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            {t('coreEditor.warp.retryPending')}
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-4">
        <div className="bg-muted/30 flex items-start gap-3 rounded-md border p-4">
          <Server className="text-muted-foreground mt-0.5 size-5 shrink-0" />
          <div className="space-y-1">
            <p className="text-sm font-medium">{t('coreEditor.warp.allNodes')}</p>
            <p className="text-muted-foreground text-sm leading-relaxed">{t('coreEditor.warp.independentProfiles')}</p>
          </div>
        </div>
        {!tag ? (
          <form
            onSubmit={e => {
              e.preventDefault()
              addOutbound()
            }}
            className="space-y-2"
          >
            <Label htmlFor="warp-outbound-tag">{t('coreEditor.field.tag', { defaultValue: 'Tag' })}</Label>
            <Input
              id="warp-outbound-tag"
              disabled={!canUpdate}
              value={tagInput}
              maxLength={256}
              dir="ltr"
              onChange={e => {
                setTagInput(e.target.value)
                setTagError('')
              }}
              aria-invalid={!!tagError}
              aria-describedby={tagError ? 'warp-tag-error' : undefined}
            />
            {tagError && (
              <p id="warp-tag-error" role="alert" className="text-destructive text-sm">
                {tagError}
              </p>
            )}
          </form>
        ) : (
          <div className="flex items-center justify-between gap-3 rounded-md border px-4 py-3">
            <span className="text-muted-foreground text-sm">{t('coreEditor.field.tag', { defaultValue: 'Tag' })}</span>
            <code dir="ltr" className="min-w-0 truncate text-sm">
              {tag}
            </code>
          </div>
        )}
        <Alert>
          <AlertDescription>{t('coreEditor.warp.routingHint')}</AlertDescription>
        </Alert>
        {tag && !saved && (
          <Alert>
            <AlertDescription>{t('coreEditor.warp.saveFirst')}</AlertDescription>
          </Alert>
        )}
        {tag && saved && (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-medium">{t('coreEditor.warp.nodeProfiles')}</h3>
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{t('coreEditor.warp.appliedCount', { count: applied, total: nodes.length })}</Badge>
                <Button type="button" size="icon" variant="ghost" onClick={() => refetch()} aria-label={t('refresh')}>
                  <RefreshCw className="size-4" />
                </Button>
              </div>
            </div>
            <p className="text-muted-foreground text-xs">{t('coreEditor.warp.appliedHint')}</p>
            {isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : isError ? (
              <Alert variant="destructive">
                <AlertDescription>{t('coreEditor.warp.statusFailed')}</AlertDescription>
              </Alert>
            ) : nodes.length === 0 ? (
              <div className="text-muted-foreground rounded-md border border-dashed p-6 text-center text-sm">{t('coreEditor.warp.noNodes')}</div>
            ) : (
              <div className="space-y-2">
                {nodes.map(node => {
                  const online = node.node_status === NodeStatus.connected
                  const result = testResults[node.node_id]
                  return (
                    <div key={node.node_id} className="space-y-2 rounded-md border p-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="min-w-0 flex-1 space-y-1">
                          <p className="truncate text-sm font-medium" title={node.name}>
                            {node.name}
                          </p>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <Badge variant={node.status === 'error' ? 'destructive' : 'secondary'}>{t(`coreEditor.warp.status.${node.status}`)}</Badge>
                            {!online && <span className="text-muted-foreground">{t(`nodeModal.status.${node.node_status}`, { defaultValue: node.node_status })}</span>}
                            {node.status === 'registering' && <Loader2 className="size-3 animate-spin" />}
                          </div>
                        </div>
                        <div className="flex shrink-0 gap-2">
                          {canUpdate && node.status !== 'applied' && (
                            <Button type="button" size="sm" variant="outline" onClick={() => retry(node.node_id)} disabled={!online || busy !== null || node.status === 'registering'}>
                              {busy === node.node_id ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
                              {t('coreEditor.warp.retry')}
                            </Button>
                          )}
                          {canTest && (
                            <Button type="button" size="sm" variant="outline" onClick={() => test(node)} disabled={!online || node.status !== 'applied' || testing !== null}>
                              {testing === node.node_id ? <Loader2 className="size-3.5 animate-spin" /> : <Gauge className="size-3.5" />}
                              {t('coreEditor.warp.test')}
                            </Button>
                          )}
                        </div>
                      </div>
                      {!online && <p className="text-muted-foreground text-xs">{t('coreEditor.warp.offlineHint')}</p>}
                      {node.last_error && (
                        <p role="alert" className="text-destructive text-xs break-words">
                          {node.last_error}
                        </p>
                      )}
                      {result && (
                        <p role="status" className={cn('text-xs', result.alive ? 'text-green-700 dark:text-green-300' : 'text-destructive')}>
                          {result.alive ? t('coreEditor.warp.testSuccess', { delay: result.delay ?? 0 }) : (result.error ?? t('coreEditor.warp.testFailed'))}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </CoreEditorFormDialog>
  )
}
