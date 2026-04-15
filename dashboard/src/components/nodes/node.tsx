import { Card } from '../ui/card'
import { AlertCircle, Link2, Package, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { CoresSimpleResponse, NodeResponse, useGetCoreConfig } from '@/service/api'
import { useXrayReleases } from '@/hooks/use-xray-releases'
import { useNodeReleases } from '@/hooks/use-node-releases'
import NodeUsageDisplay from './node-usage-display'
import NodeActionsMenu from './node-actions-menu'
import type { ReactNode } from 'react'

interface NodeProps {
  node: NodeResponse
  onEdit: (node: NodeResponse) => void
  onToggleStatus: (node: NodeResponse) => Promise<void>
  coresData?: CoresSimpleResponse
  selectionControl?: ReactNode
  selected?: boolean
}

export default function Node({ node, onEdit, onToggleStatus, coresData, selectionControl, selected = false }: NodeProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { latestVersion: latestXrayVersion, hasUpdate: hasXrayUpdate } = useXrayReleases()
  const { latestVersion: latestNodeVersion, hasUpdate: hasNodeUpdate } = useNodeReleases()
  const { data: coreConfig } = useGetCoreConfig(node.core_config_id || 0, {
    query: {
      enabled: !!node.core_config_id,
      staleTime: 5 * 60 * 1000,
    },
  })
  const coreVersion = node.core_version ?? node.xray_version
  const resolvedCoreType =
    coreConfig?.type ?? coresData?.cores?.find((c) => c.id === node.core_config_id)?.type ?? null
  const isWireGuardCore = resolvedCoreType === 'wg'
  const isXrayBackend =
    resolvedCoreType === 'xray' || (resolvedCoreType === null && (coreConfig?.type || 'xray') === 'xray')
  const hasCoreUpdate = !!(isXrayBackend && coreVersion && latestXrayVersion && hasXrayUpdate(coreVersion))
  const hasNodeVersionUpdate =
    !isWireGuardCore && !!latestNodeVersion && !!node.node_version && hasNodeUpdate(node.node_version)

  const getStatusConfig = () => {
    switch (node.status) {
      case 'connected':
        return {
          label: t('nodeModal.status.connected', { defaultValue: 'Connected' }),
        }
      case 'connecting':
        return {
          label: t('nodeModal.status.connecting', { defaultValue: 'Connecting' }),
        }
      case 'error':
        return {
          label: t('nodeModal.status.error', { defaultValue: 'Error' }),
        }
      case 'limited':
        return {
          label: t('status.limited', { defaultValue: 'Limited' }),
        }
      default:
        return {
          label: t('nodeModal.status.disabled', { defaultValue: 'Disabled' }),
        }
    }
  }

  const statusConfig = getStatusConfig()

  const getStatusDotColor = () => {
    switch (node.status) {
      case 'connected':
        return 'bg-green-500'
      case 'connecting':
        return 'bg-amber-500'
      case 'error':
        return 'bg-destructive'
      case 'limited':
        return 'bg-orange-500'
      default:
        return 'bg-gray-400 dark:bg-gray-600'
    }
  }

  const uplink = node.uplink || 0
  const downlink = node.downlink || 0
  const totalUsed = uplink + downlink
  const lifetimeUplink = node.lifetime_uplink || 0
  const lifetimeDownlink = node.lifetime_downlink || 0
  const totalLifetime = lifetimeUplink + lifetimeDownlink
  const hasUsageDisplay = !(totalUsed === 0 && !node.data_limit && totalLifetime === 0)

  return (
    <TooltipProvider>
      <Card className={cn('group relative h-full cursor-pointer overflow-hidden border transition-colors hover:bg-accent', selected && 'border-primary/50 bg-accent/30')} onClick={() => onEdit(node)}>
        <div className="flex items-start gap-3 p-3">
          {selectionControl ? <div className="pt-1">{selectionControl}</div> : null}
          <div className="min-w-0 flex-1">
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="mb-0.5 flex items-center gap-1.5">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className={cn('h-2 w-2 shrink-0 rounded-full', getStatusDotColor())} />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{statusConfig.label}</p>
                  </TooltipContent>
                </Tooltip>
                <h3 className="truncate text-sm font-semibold leading-tight tracking-tight sm:text-base">{node.name}</h3>
                {node.status === 'error' && node.message ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <AlertCircle className="h-3.5 w-3.5 shrink-0 cursor-help text-destructive sm:h-4 sm:w-4" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs" side="top">
                      <p className="text-xs">{node.message}</p>
                    </TooltipContent>
                  </Tooltip>
                ) : null}
              </div>
            </div>
            <NodeActionsMenu node={node} onEdit={onEdit} onToggleStatus={onToggleStatus} coresData={coresData} />
          </div>

          {/* Connection Info */}
          <div className="mb-2 space-y-1.5">
            <div className={cn('flex items-center gap-1.5 text-[10px] text-muted-foreground sm:text-xs', dir === 'rtl' ? 'flex-row-reverse justify-end' : 'flex-row')}>
              <Link2 className="h-3 w-3 shrink-0 opacity-70 sm:h-3.5 sm:w-3.5" />
              <span dir="ltr" className="truncate font-mono">
                {node.address}:{node.port}
              </span>
            </div>

            {/* Version Info */}
            {(coreVersion || node.node_version) && (
              <div className="flex flex-wrap items-center gap-3">
                {coreVersion && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className={cn('group/version inline-flex items-center', dir === 'rtl' ? 'flex-row-reverse gap-1' : 'gap-1')}>
                        <Package className={cn('h-3 w-3 shrink-0 transition-colors sm:h-3.5 sm:w-3.5', hasCoreUpdate ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')} />
                        <span className={cn('font-mono text-[10px] font-medium sm:text-[11px]', hasCoreUpdate ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground')}>{coreVersion}</span>
                        {hasCoreUpdate && <div className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      <div className="space-y-2 text-xs">
                        <div className="font-semibold">{t('node.coreVersion', { defaultValue: 'Core' })}</div>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4">
                            <span>{t('version.currentVersion', { defaultValue: 'Current' })}</span>
                            <span className="font-mono font-medium">{coreVersion}</span>
                          </div>
                          {isXrayBackend && latestXrayVersion && (
                            <div className="flex items-center justify-between gap-4">
                              <span>{t('version.latestVersion', { defaultValue: 'Latest' })}</span>
                              <span className="font-mono font-medium">{latestXrayVersion}</span>
                            </div>
                          )}
                          {hasCoreUpdate && (
                            <>
                              <Separator className="my-1.5" />
                              <span>{t('nodeModal.updateAvailable', { defaultValue: 'Update available' })}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                )}
                {node.node_version && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className={cn('group/version inline-flex items-center', dir === 'rtl' ? 'flex-row-reverse gap-1' : 'gap-1')}>
                        <Server
                          className={cn(
                            'h-3 w-3 shrink-0 transition-colors sm:h-3.5 sm:w-3.5',
                            hasNodeVersionUpdate ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground',
                          )}
                        />
                        <span
                          className={cn(
                            'font-mono text-[10px] font-medium sm:text-[11px]',
                            hasNodeVersionUpdate ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground',
                          )}
                        >
                          {node.node_version}
                        </span>
                        {hasNodeVersionUpdate && <div className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      <div className="space-y-2 text-xs">
                        <div className="font-semibold">{t('node.coreVersion', { defaultValue: 'Node Core' })}</div>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4">
                            <span>{t('version.currentVersion', { defaultValue: 'Current' })}</span>
                            <span className="font-mono font-medium">{node.node_version}</span>
                          </div>
                          {!isWireGuardCore && latestNodeVersion && (
                            <div className="flex items-center justify-between gap-4">
                              <span>{t('version.latestVersion', { defaultValue: 'Latest' })}</span>
                              <span className="font-mono font-medium">{latestNodeVersion}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
            )}
          </div>

          {hasUsageDisplay && (
            <>
              <Separator className="my-2 opacity-50" />
              {/* Usage Display */}
              <NodeUsageDisplay node={node} />
            </>
          )}
          </div>
        </div>
      </Card>
    </TooltipProvider>
  )
}
