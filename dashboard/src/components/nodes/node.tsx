import { useState } from 'react'
import { Card } from '../ui/card'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '../ui/dropdown-menu'
import { Button } from '../ui/button'
import { MoreVertical, Pencil, Trash2, Power, Activity, RotateCcw, Wifi, Loader2, RefreshCw, Package, Server, AlertCircle, Link2, Map } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import { NodeResponse, useRemoveNode, useSyncNode, useReconnectNode, useResetNodeUsage, useUpdateNode } from '@/service/api'
import { useXrayReleases } from '@/hooks/use-xray-releases'
import { useNodeReleases } from '@/hooks/use-node-releases'
import UserOnlineStatsDialog from '../dialogs/user-online-stats-modal'
import UpdateCoreDialog from '../dialogs/update-core-modal'
import UpdateGeofilesDialog from '../dialogs/update-geofiles-modal'
import NodeUsageDisplay from './node-usage-display'

interface NodeProps {
  node: NodeResponse
  onEdit: (node: NodeResponse) => void
  onToggleStatus: (node: NodeResponse) => Promise<void>
}

const DeleteAlertDialog = ({ node, isOpen, onClose, onConfirm }: { node: NodeResponse; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('nodes.deleteNode')}</AlertDialogTitle>
          <AlertDialogDescription>
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('deleteNode.prompt', { name: node.name }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const ResetUsageAlertDialog = ({ node, isOpen, onClose, onConfirm, isLoading }: { node: NodeResponse; isOpen: boolean; onClose: () => void; onConfirm: () => void; isLoading: boolean }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('nodeModal.resetUsageTitle', { defaultValue: 'Reset Node Usage' })}</AlertDialogTitle>
          <AlertDialogDescription>
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('nodeModal.resetUsagePrompt', { name: node.name, defaultValue: `Are you sure you want to reset usage for node «${node.name}»?` }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose} disabled={isLoading}>
            {t('cancel')}
          </AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} disabled={isLoading}>
            {t('nodeModal.resetUsage', { defaultValue: 'Reset Usage' })}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default function Node({ node, onEdit, onToggleStatus }: NodeProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [isResetUsageDialogOpen, setResetUsageDialogOpen] = useState(false)
  const [showOnlineStats, setShowOnlineStats] = useState(false)
  const [showUpdateCoreDialog, setShowUpdateCoreDialog] = useState(false)
  const [showUpdateGeofilesDialog, setShowUpdateGeofilesDialog] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [resettingUsage, setResettingUsage] = useState(false)
  const [updatingNode, setUpdatingNode] = useState(false)
  const removeNodeMutation = useRemoveNode()
  const syncNodeMutation = useSyncNode()
  const reconnectNodeMutation = useReconnectNode()
  const resetNodeUsageMutation = useResetNodeUsage()
  const updateNodeMutation = useUpdateNode()
  const { latestVersion: latestXrayVersion, hasUpdate: hasXrayUpdate } = useXrayReleases()
  const { latestVersion: latestNodeVersion, hasUpdate: hasNodeUpdate } = useNodeReleases()

  const handleDeleteClick = (event: Event) => {
    event.stopPropagation()
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    try {
      await removeNodeMutation.mutateAsync({
        nodeId: node.id,
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('nodes.deleteSuccess', {
          name: node.name,
          defaultValue: 'Node «{name}» has been deleted successfully',
        }),
      })
      setDeleteDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('nodes.deleteFailed', {
          name: node.name,
          defaultValue: 'Failed to delete node «{name}»',
        }),
      })
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      await syncNodeMutation.mutateAsync({
        nodeId: node.id,
        params: { flush_users: false },
      })
      toast.success(t('nodeModal.syncSuccess'))
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
    } catch (error: any) {
      toast.error(
        t('nodeModal.syncFailed', {
          message: error?.message || 'Unknown error',
        }),
      )
    } finally {
      setSyncing(false)
    }
  }

  const handleReconnect = async () => {
    setReconnecting(true)
    try {
      await reconnectNodeMutation.mutateAsync({
        nodeId: node.id,
      })
      toast.success(t('nodeModal.reconnectSuccess', { defaultValue: 'Node reconnected successfully' }))
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
    } catch (error: any) {
      toast.error(
        t('nodeModal.reconnectFailed', {
          message: error?.message || 'Unknown error',
        }),
      )
    } finally {
      setReconnecting(false)
    }
  }

  const handleResetUsage = () => {
    setResetUsageDialogOpen(true)
  }

  const confirmResetUsage = async () => {
    setResettingUsage(true)
    try {
      await resetNodeUsageMutation.mutateAsync({
        nodeId: node.id,
      })
      toast.success(t('nodeModal.resetUsageSuccess', { defaultValue: 'Node usage reset successfully' }))
      setResetUsageDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
      queryClient.invalidateQueries({ queryKey: [`/api/node/${node.id}`] })
    } catch (error: any) {
      toast.error(
        t('nodeModal.resetUsageFailed', {
          message: error?.message || 'Unknown error',
        }),
      )
    } finally {
      setResettingUsage(false)
    }
  }

  const handleUpdateNode = async () => {
    setUpdatingNode(true)
    try {
      await updateNodeMutation.mutateAsync({
        nodeId: node.id,
      })
      toast.success(t('nodeModal.updateNodeSuccess', { defaultValue: 'Node updated successfully' }))
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
      queryClient.invalidateQueries({ queryKey: [`/api/node/${node.id}`] })
    } catch (error: any) {
      toast.error(
        t('nodeModal.updateNodeFailed', {
          message: error?.message || 'Unknown error',
          defaultValue: 'Failed to update node: {message}',
        }),
      )
    } finally {
      setUpdatingNode(false)
    }
  }

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
            <div onClick={e => e.stopPropagation()}>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8">
                    <MoreVertical className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      onEdit(node)
                    }}
                  >
                    <Pencil className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{t('edit')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      onToggleStatus(node)
                    }}
                  >
                    <Power className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{node.status === 'disabled' ? t('enable') : t('disable')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      setShowOnlineStats(true)
                    }}
                    disabled={syncing || reconnecting || resettingUsage || updatingNode}
                  >
                    <Activity className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{t('nodeModal.onlineStats.button', { defaultValue: 'Stats' })}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      handleSync()
                    }}
                    disabled={syncing || reconnecting || resettingUsage || updatingNode}
                  >
                    {syncing ? <Loader2 className="mr-2 h-4 w-4 shrink-0 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4 shrink-0" />}
                    <span className="min-w-0 truncate">{syncing ? t('nodeModal.syncing') : t('nodeModal.sync')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      handleReconnect()
                    }}
                    disabled={reconnecting || syncing || resettingUsage}
                  >
                    {reconnecting ? <Loader2 className="mr-2 h-4 w-4 shrink-0 animate-spin" /> : <Wifi className="mr-2 h-4 w-4 shrink-0" />}
                    <span className="min-w-0 truncate">{reconnecting ? t('nodeModal.reconnecting') : t('nodeModal.reconnect')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      handleResetUsage()
                    }}
                    disabled={resettingUsage || syncing || reconnecting}
                  >
                    <RefreshCw className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{t('nodeModal.resetUsage', { defaultValue: 'Reset' })}</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      setShowUpdateCoreDialog(true)
                    }}
                    disabled={syncing || reconnecting || resettingUsage || updatingNode}
                  >
                    <Package className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{t('nodeModal.updateCore', { defaultValue: 'Update Core' })}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      setShowUpdateGeofilesDialog(true)
                    }}
                    disabled={syncing || reconnecting || resettingUsage || updatingNode}
                  >
                    <Map className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{t('nodeModal.updateGeofiles', { defaultValue: 'Update Geofiles' })}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={e => {
                      e.stopPropagation()
                      handleUpdateNode()
                    }}
                    disabled={syncing || reconnecting || resettingUsage || updatingNode}
                  >
                    {updatingNode ? <Loader2 className="mr-2 h-4 w-4 shrink-0 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4 shrink-0" />}
                    <span className="min-w-0 truncate">{updatingNode ? t('nodeModal.updatingNode', { defaultValue: 'Updating Node...' }) : t('nodeModal.updateNode', { defaultValue: 'Update Node' })}</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive focus:text-destructive">
                    <Trash2 className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{t('delete')}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
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
                          'group/version inline-flex items-center cursor-pointer',
                          dir === 'rtl' ? 'flex-row-reverse gap-1' : 'gap-1',
                        )}
                        onClick={e => {
                          e.stopPropagation()
                          setShowUpdateCoreDialog(true)
                        }}
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

          {hasUsageDisplay && (
            <>
              <Separator className="my-2 opacity-50" />
              {/* Usage Display */}
              <NodeUsageDisplay node={node} />
            </>
          )}
        </div>
      </Card>

      <DeleteAlertDialog node={node} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />

      <ResetUsageAlertDialog node={node} isOpen={isResetUsageDialogOpen} onClose={() => setResetUsageDialogOpen(false)} onConfirm={confirmResetUsage} isLoading={resettingUsage} />

      <UserOnlineStatsDialog isOpen={showOnlineStats} onOpenChange={setShowOnlineStats} nodeId={node.id} nodeName={node.name} />

      <UpdateCoreDialog node={node} isOpen={showUpdateCoreDialog} onOpenChange={setShowUpdateCoreDialog} />

      <UpdateGeofilesDialog node={node} isOpen={showUpdateGeofilesDialog} onOpenChange={setShowUpdateGeofilesDialog} />
    </TooltipProvider>
  )
}
