import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Activity, Loader2, Map, MoreVertical, Package, Pencil, Power, RefreshCw, RotateCcw, Trash2, Wifi } from 'lucide-react'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import { NodeResponse, useReconnectNode, useRemoveNode, useResetNodeUsage, useSyncNode, useUpdateNode } from '@/service/api'
import useDirDetection from '@/hooks/use-dir-detection'
import UserOnlineStatsDialog from '@/components/dialogs/user-online-stats-modal'
import UpdateCoreDialog from '@/components/dialogs/update-core-modal'
import UpdateGeofilesDialog from '@/components/dialogs/update-geofiles-modal'

interface NodeActionsMenuProps {
  node: NodeResponse
  onEdit: (node: NodeResponse) => void
  onToggleStatus: (node: NodeResponse) => Promise<void>
  className?: string
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

export default function NodeActionsMenu({ node, onEdit, onToggleStatus, className }: NodeActionsMenuProps) {
  const { t } = useTranslation()
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
      queryClient.invalidateQueries({ queryKey: ['/api/nodes/simple'] })
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
      queryClient.invalidateQueries({ queryKey: ['/api/nodes/simple'] })
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
      queryClient.invalidateQueries({ queryKey: ['/api/nodes/simple'] })
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
      queryClient.invalidateQueries({ queryKey: ['/api/nodes/simple'] })
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
      queryClient.invalidateQueries({ queryKey: ['/api/nodes/simple'] })
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

  return (
    <div className={className} onClick={e => e.stopPropagation()}>
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

      <DeleteAlertDialog node={node} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />
      <ResetUsageAlertDialog node={node} isOpen={isResetUsageDialogOpen} onClose={() => setResetUsageDialogOpen(false)} onConfirm={confirmResetUsage} isLoading={resettingUsage} />
      <UserOnlineStatsDialog isOpen={showOnlineStats} onOpenChange={setShowOnlineStats} nodeId={node.id} nodeName={node.name} />
      <UpdateCoreDialog node={node} isOpen={showUpdateCoreDialog} onOpenChange={setShowUpdateCoreDialog} />
      <UpdateGeofilesDialog node={node} isOpen={showUpdateGeofilesDialog} onOpenChange={setShowUpdateGeofilesDialog} />
    </div>
  )
}
