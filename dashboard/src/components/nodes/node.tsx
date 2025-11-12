import { useState } from 'react'
import { Card, CardTitle } from '../ui/card'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '../ui/dropdown-menu'
import { Button } from '../ui/button'
import { MoreVertical, Pencil, Trash2, Power, Activity, RotateCcw, Wifi, Loader2, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import { NodeResponse, useRemoveNode, useSyncNode, useReconnectNode, useResetNodeUsage } from '@/service/api'
import UserOnlineStatsDialog from '../dialogs/user-online-stats-modal'
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

export default function Node({ node, onEdit, onToggleStatus }: NodeProps) {
  const { t } = useTranslation()
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [showOnlineStats, setShowOnlineStats] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [resettingUsage, setResettingUsage] = useState(false)
  const removeNodeMutation = useRemoveNode()
  const syncNodeMutation = useSyncNode()
  const reconnectNodeMutation = useReconnectNode()
  const resetNodeUsageMutation = useResetNodeUsage()

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
      // Invalidate nodes queries
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
      // Invalidate queries to refresh data
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
      // Invalidate queries to refresh data
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

  const handleResetUsage = async () => {
    setResettingUsage(true)
    try {
      await resetNodeUsageMutation.mutateAsync({
        nodeId: node.id,
      })
      toast.success(t('nodeModal.resetUsageSuccess', { defaultValue: 'Node usage reset successfully' }))
      // Invalidate queries to refresh data
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

  return (
    <>
      <Card className="group relative h-full cursor-pointer p-4 transition-colors hover:bg-accent" onClick={() => onEdit(node)}>
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  'min-h-2 min-w-2 rounded-full',
                  node.status === 'connected' ? 'bg-green-500' : node.status === 'connecting' ? 'bg-yellow-500' : node.status === 'error' ? 'bg-red-500' : 'bg-gray-500',
                )}
              />
              <div className="truncate font-medium">{node.name}</div>
            </div>
            <CardTitle className="flex items-center gap-1 truncate text-sm text-muted-foreground">
              <span>
                {node.address}:{node.port}
              </span>
            </CardTitle>
            {(node.xray_version || node.node_version) && (
              <div className="mt-1 flex gap-2 text-xs text-muted-foreground">
                {node.xray_version && (
                  <span>
                    {t('node.xrayVersion', { defaultValue: 'Xray Core Version' })}: {node.xray_version}
                  </span>
                )}
                {node.node_version && (
                  <span>
                    {t('node.coreVersion', { defaultValue: 'Node Core Version' })}: {node.node_version}
                  </span>
                )}
              </div>
            )}
            <NodeUsageDisplay node={node} />
          </div>
          <div onClick={e => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    onToggleStatus(node)
                  }}
                >
                  <Power className="mr-2 h-4 w-4" />
                  {node.status === 'disabled' ? t('enable') : t('disable')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    setShowOnlineStats(true)
                  }}
                  disabled={syncing || reconnecting || resettingUsage}
                >
                  <Activity className="mr-2 h-4 w-4" />
                  {t('nodeModal.onlineStats.button')}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    handleSync()
                  }}
                  disabled={syncing || reconnecting || resettingUsage}
                >
                  {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}
                  {syncing ? t('nodeModal.syncing') : t('nodeModal.sync')}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    handleReconnect()
                  }}
                  disabled={reconnecting || syncing || resettingUsage}
                >
                  {reconnecting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Wifi className="mr-2 h-4 w-4" />}
                  {reconnecting ? t('nodeModal.reconnecting') : t('nodeModal.reconnect')}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    handleResetUsage()
                  }}
                  disabled={resettingUsage || syncing || reconnecting}
                >
                  {resettingUsage ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  {resettingUsage ? t('nodeModal.resettingUsage') : t('nodeModal.resetUsage')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={e => {
                    e.stopPropagation()
                    onEdit(node)
                  }}
                >
                  <Pencil className="mr-2 h-4 w-4" />
                  {t('edit')}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive">
                  <Trash2 className="mr-2 h-4 w-4" />
                  {t('delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </Card>

      <DeleteAlertDialog node={node} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />

      {/* User Online Stats Dialog */}
      <UserOnlineStatsDialog isOpen={showOnlineStats} onOpenChange={setShowOnlineStats} nodeId={node.id} nodeName={node.name} />
    </>
  )
}