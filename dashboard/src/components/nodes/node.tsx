import { Card } from '../ui/card'
import { AlertCircle, Link2, Package, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { NodeResponse } from '@/service/api'
import { useXrayReleases } from '@/hooks/use-xray-releases'
import { useNodeReleases } from '@/hooks/use-node-releases'
import NodeUsageDisplay from './node-usage-display'
import NodeActionsMenu from './node-actions-menu'

interface NodeProps {
  node: NodeResponse
  onEdit: (node: NodeResponse) => void
  onToggleStatus: (node: NodeResponse) => Promise<void>
}

export default function Node({ node, onEdit, onToggleStatus }: NodeProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { latestVersion: latestXrayVersion, hasUpdate: hasXrayUpdate } = useXrayReleases()
  const { latestVersion: latestNodeVersion, hasUpdate: hasNodeUpdate } = useNodeReleases()

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

  return (
    <TooltipProvider>
      <Card className="group relative h-full cursor-pointer overflow-hidden border transition-colors hover:bg-accent" onClick={() => onEdit(node)}>
        <div className="p-3">
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="mb-0.5 flex items-center gap-1.5">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className={cn('h-2 w-2 rounded-full shrink-0', getStatusDotColor())} />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{statusConfig.label}</p>
                  </TooltipContent>
                </Tooltip>
                <h3 className="truncate text-sm sm:text-base font-semibold leading-tight tracking-tight">{node.name}</h3>
                {node.status === 'error' && node.message ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <AlertCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4 shrink-0 cursor-help text-destructive" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs" side="top">
                      <p className="text-xs">{node.message}</p>
                    </TooltipContent>
                  </Tooltip>
                ) : null}
              </div>
            </div>
            <NodeActionsMenu node={node} onEdit={onEdit} onToggleStatus={onToggleStatus} />
          </div>

          {/* Connection Info */}
          <div className="mb-2 space-y-1.5">
            <div className={cn("flex items-center gap-1.5 text-[10px] sm:text-xs text-muted-foreground", dir === 'rtl' ? 'flex-row-reverse justify-end' : 'flex-row')}>
              <Link2 className="h-3 w-3 sm:h-3.5 sm:w-3.5 shrink-0 opacity-70" />
              <span dir="ltr" className="truncate font-mono">
                {node.address}:{node.port}
              </span>
            </div>

            {/* Version Info */}
            {(node.xray_version || node.node_version) && (
              <div className="flex flex-wrap items-center gap-3">
                {node.xray_version && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div
                        className={cn(
                          'group/version inline-flex items-center',
                          dir === 'rtl' ? 'flex-row-reverse gap-1' : 'gap-1',
                        )}
                      >
                        <Package className={cn('h-3 w-3 sm:h-3.5 sm:w-3.5 shrink-0 transition-colors', latestXrayVersion && hasXrayUpdate(node.xray_version) ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')} />
                        <span className={cn('text-[10px] sm:text-[11px] font-medium font-mono', latestXrayVersion && hasXrayUpdate(node.xray_version) ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground')}>
                          {node.xray_version}
                        </span>
                        {latestXrayVersion && hasXrayUpdate(node.xray_version) && (
                          <div className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
                        )}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      <div className="space-y-2 text-xs">
                        <div className="font-semibold">{t('node.xrayVersion', { defaultValue: 'Xray Core' })}</div>
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between gap-4">
                            <span>{t('version.currentVersion', { defaultValue: 'Current' })}</span>
                            <span className="font-mono font-medium">{node.xray_version}</span>
                          </div>
                          {latestXrayVersion && (
                            <div className="flex items-center justify-between gap-4">
                              <span>{t('version.latestVersion', { defaultValue: 'Latest' })}</span>
                              <span className="font-mono font-medium">{latestXrayVersion}</span>
                            </div>
                          )}
                          {latestXrayVersion && hasXrayUpdate(node.xray_version) && (
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
                      <div
                        className={cn(
                          'group/version inline-flex items-center',
                          dir === 'rtl' ? 'flex-row-reverse gap-1' : 'gap-1',
                        )}
                      >
                        <Server className={cn('h-3 w-3 sm:h-3.5 sm:w-3.5 shrink-0 transition-colors', latestNodeVersion && hasNodeUpdate(node.node_version) ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')} />
                        <span className={cn('text-[10px] sm:text-[11px] font-medium font-mono', latestNodeVersion && hasNodeUpdate(node.node_version) ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground')}>
                          {node.node_version}
                        </span>
                        {latestNodeVersion && hasNodeUpdate(node.node_version) && (
                          <div className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
                        )}
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
                          {latestNodeVersion && (
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

          <Separator className="my-2 opacity-50" />

          {/* Usage Display */}
          <NodeUsageDisplay node={node} />
        </div>
      </Card>

    </TooltipProvider>
  )
}
