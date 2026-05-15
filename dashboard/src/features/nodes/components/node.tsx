import { Card } from '@/components/ui/card'
import { AlertCircle, Link2, Package, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { CoresSimpleResponse, NodeResponse } from '@/service/api'
import { useXrayReleases } from '@/hooks/use-xray-releases'
import { useNodeReleases } from '@/hooks/use-node-releases'
import NodeUsageDisplay from './node-usage-display'
import NodeActionsMenu from './node-actions-menu'
import UpdateCoreDialog from '@/features/nodes/dialogs/update-core-modal'
import { useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'

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
  const [showUpdateCoreDialog, setShowUpdateCoreDialog] = useState(false)
  const { latestVersion: latestXrayVersion, hasUpdate: hasXrayUpdate } = useXrayReleases()
  const { latestVersion: latestNodeVersion, hasUpdate: hasNodeUpdate } = useNodeReleases()
  const coreVersion = node.core_version ?? node.xray_version
  const resolvedCoreType = coresData?.cores?.find(c => c.id === node.core_config_id)?.type ?? null
  const isWireGuardCore = resolvedCoreType === 'wg'
  const isXrayBackend = resolvedCoreType !== 'wg'
  const coreUpdateVersion = node.xray_version ?? coreVersion
  const hasCoreUpdate = !!(isXrayBackend && coreUpdateVersion && latestXrayVersion && hasXrayUpdate(coreUpdateVersion))
  const hasNodeVersionUpdate = !isWireGuardCore && !!latestNodeVersion && !!node.node_version && hasNodeUpdate(node.node_version)

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
  const handleCoreVersionClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (!hasCoreUpdate) return
    event.preventDefault()
    event.stopPropagation()
    setShowUpdateCoreDialog(true)
  }

  return (
    <TooltipProvider>
      <Card className={cn('group hover:bg-accent relative h-full cursor-pointer overflow-hidden border transition-colors', selected && 'border-primary/50 bg-accent/30')} onClick={() => onEdit(node)}>
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
                  <h3 className="truncate text-sm leading-tight font-semibold tracking-tight sm:text-base">{node.name}</h3>
                  {node.status === 'error' && node.message ? (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <AlertCircle className="text-destructive h-3.5 w-3.5 shrink-0 cursor-help sm:h-4 sm:w-4" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-xs" side="top">
                        <p className="text-xs">{node.message}</p>
                      </TooltipContent>
                    </Tooltip>
                  ) : null}
                </div>
              </div>
              <NodeActionsMenu node={node} onEdit={onEdit} onToggleStatus={onToggleStatus} coresData={coresData} isModalHost={false} />
            </div>

            {/* Connection Info */}
            <div className="mb-2 space-y-1.5">
              <div className={cn('text-muted-foreground flex items-center gap-1.5 text-[10px] sm:text-xs', dir === 'rtl' ? 'flex-row-reverse justify-end' : 'flex-row')}>
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
                        <button
                          type="button"
                          onClick={handleCoreVersionClick}
                          className={cn(
                            'group/version inline-flex items-center rounded-sm bg-transparent p-0 text-left',
                            hasCoreUpdate && 'focus-visible:ring-ring cursor-pointer focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none',
                            !hasCoreUpdate && 'cursor-default',
                            dir === 'rtl' ? 'flex-row-reverse gap-1' : 'gap-1',
                          )}
                          aria-label={t('nodeModal.updateCore', { defaultValue: 'Update Core' })}
                        >
                          <Package className={cn('h-3 w-3 shrink-0 transition-colors sm:h-3.5 sm:w-3.5', hasCoreUpdate ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')} />
                          <span className={cn('font-mono text-[10px] font-medium sm:text-[11px]', hasCoreUpdate ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground')}>{coreVersion}</span>
                          {hasCoreUpdate && <div className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <div className="space-y-2 text-xs">
                          <div className="font-semibold">{t('node.xrayVersion', { defaultValue: 'Core' })}</div>
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
                          <Server className={cn('h-3 w-3 shrink-0 transition-colors sm:h-3.5 sm:w-3.5', hasNodeVersionUpdate ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')} />
                          <span className={cn('font-mono text-[10px] font-medium sm:text-[11px]', hasNodeVersionUpdate ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground')}>
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
                            {hasNodeVersionUpdate && (
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
                </div>
              )}
            </div>

            {hasUsageDisplay && (
              <>
                <Separator className="my-1.5 opacity-50" />
                <NodeUsageDisplay node={node} />
              </>
            )}
          </div>
        </div>
      </Card>
      <UpdateCoreDialog node={node} isOpen={showUpdateCoreDialog} onOpenChange={setShowUpdateCoreDialog} />
    </TooltipProvider>
  )
}
