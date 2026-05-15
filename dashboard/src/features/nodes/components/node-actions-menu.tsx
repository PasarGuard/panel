import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Activity, CircleFadingArrowUp, Loader2, Map as MapIcon, MoreVertical, Package, Pencil, Power, PowerOff, RefreshCcw, RotateCcw, Trash2, WifiSync } from 'lucide-react'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import { CoresSimpleResponse, NodeResponse, useReconnectNode, useRemoveNode, useResetNodeUsage, useSyncNode, useUpdateNode } from '@/service/api'
import useDirDetection from '@/hooks/use-dir-detection'
import UserOnlineStatsDialog from '@/features/users/dialogs/user-online-stats-modal'
import UpdateCoreDialog from '@/features/nodes/dialogs/update-core-modal'
import UpdateGeofilesDialog from '@/features/nodes/dialogs/update-geofiles-modal'

interface NodeActionsMenuProps {
  node: NodeResponse
  onEdit: (node: NodeResponse) => void
  onToggleStatus: (node: NodeResponse) => Promise<void>
  coresData?: CoresSimpleResponse
  className?: string
  isModalHost?: boolean
  renderActions?: boolean
}

type NodeActionsMenuState = {
  isDeleteDialogOpen: boolean
  isResetUsageDialogOpen: boolean
  showOnlineStats: boolean
  showUpdateCoreDialog: boolean
  showUpdateGeofilesDialog: boolean
}

const nodeActionsMenuStateStore = new Map<number, NodeActionsMenuState>()
const nodeActionsNodeStore = new Map<number, NodeResponse>()
const nodeActionsMenuStateListeners = new Map<number, Set<() => void>>()
const nodeActionsGlobalListeners = new Set<() => void>()
const nodeActionsClosingNodeIds = new Set<number>()
const nodeActionsClosingTimers = new Map<number, ReturnType<typeof setTimeout>>()
let nodeActionsGlobalStateVersion = 0
const DIALOG_EXIT_ANIMATION_MS = 220

const createDefaultNodeActionsMenuState = (): NodeActionsMenuState => ({
  isDeleteDialogOpen: false,
  isResetUsageDialogOpen: false,
  showOnlineStats: false,
  showUpdateCoreDialog: false,
  showUpdateGeofilesDialog: false,
})

const ensureNodeActionsMenuState = (node: NodeResponse): NodeActionsMenuState => {
  if (!nodeActionsNodeStore.has(node.id)) {
    nodeActionsNodeStore.set(node.id, node)
  }

  const existing = nodeActionsMenuStateStore.get(node.id)
  if (existing) return existing
  const initial = createDefaultNodeActionsMenuState()
  nodeActionsMenuStateStore.set(node.id, initial)
  return initial
}

const hasOpenNodeDialog = (state: NodeActionsMenuState) =>
  state.isDeleteDialogOpen || state.isResetUsageDialogOpen || state.showOnlineStats || state.showUpdateCoreDialog || state.showUpdateGeofilesDialog

const notifyNodeActionsGlobalListeners = () => {
  nodeActionsGlobalStateVersion += 1
  nodeActionsGlobalListeners.forEach(listener => listener())
}

const syncNodeSnapshot = (node: NodeResponse) => {
  const currentNode = nodeActionsNodeStore.get(node.id)
  if (currentNode === node) return

  nodeActionsNodeStore.set(node.id, node)

  const menuState = nodeActionsMenuStateStore.get(node.id)
  if (menuState && hasOpenNodeDialog(menuState)) {
    nodeActionsMenuStateListeners.get(node.id)?.forEach(listener => listener())
    notifyNodeActionsGlobalListeners()
  }
}

const subscribeNodeActionsMenuState = (nodeId: number, listener: () => void) => {
  let listeners = nodeActionsMenuStateListeners.get(nodeId)
  if (!listeners) {
    listeners = new Set()
    nodeActionsMenuStateListeners.set(nodeId, listeners)
  }

  listeners.add(listener)

  return () => {
    const current = nodeActionsMenuStateListeners.get(nodeId)
    if (!current) return
    current.delete(listener)
    if (current.size === 0) {
      nodeActionsMenuStateListeners.delete(nodeId)
    }
  }
}

const subscribeGlobalNodeActionsMenuState = (listener: () => void) => {
  nodeActionsGlobalListeners.add(listener)

  return () => {
    nodeActionsGlobalListeners.delete(listener)
  }
}

const getOpenDialogNodes = (): NodeResponse[] =>
  Array.from(nodeActionsMenuStateStore.entries())
    .filter(([nodeId, state]) => hasOpenNodeDialog(state) || nodeActionsClosingNodeIds.has(nodeId))
    .map(([nodeId]) => nodeActionsNodeStore.get(nodeId))
    .filter((node): node is NodeResponse => Boolean(node))

const getGlobalNodeActionsMenuStateSnapshot = () => nodeActionsGlobalStateVersion

const updateNodeActionsMenuState = (nodeId: number, updater: (prev: NodeActionsMenuState) => NodeActionsMenuState) => {
  const current = nodeActionsMenuStateStore.get(nodeId)
  if (!current) return

  const hadOpenDialog = hasOpenNodeDialog(current)
  const next = updater(current)
  if (next === current) return
  const hasOpenDialog = hasOpenNodeDialog(next)

  nodeActionsMenuStateStore.set(nodeId, next)

  if (hasOpenDialog) {
    const closingTimer = nodeActionsClosingTimers.get(nodeId)
    if (closingTimer) {
      clearTimeout(closingTimer)
      nodeActionsClosingTimers.delete(nodeId)
    }
    nodeActionsClosingNodeIds.delete(nodeId)
  } else if (hadOpenDialog) {
    nodeActionsClosingNodeIds.add(nodeId)
    const closingTimer = nodeActionsClosingTimers.get(nodeId)
    if (closingTimer) {
      clearTimeout(closingTimer)
    }
    nodeActionsClosingTimers.set(
      nodeId,
      setTimeout(() => {
        nodeActionsClosingNodeIds.delete(nodeId)
        nodeActionsClosingTimers.delete(nodeId)
        notifyNodeActionsGlobalListeners()
      }, DIALOG_EXIT_ANIMATION_MS),
    )
  }

  nodeActionsMenuStateListeners.get(nodeId)?.forEach(listener => listener())
  notifyNodeActionsGlobalListeners()
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

export default function NodeActionsMenu({ node, onEdit, onToggleStatus, coresData, className, isModalHost = true, renderActions = true }: NodeActionsMenuProps) {
  const { t } = useTranslation()
  const [syncing, setSyncing] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [resettingUsage, setResettingUsage] = useState(false)
  const [updatingNode, setUpdatingNode] = useState(false)
  const removeNodeMutation = useRemoveNode()
  const syncNodeMutation = useSyncNode()
  const reconnectNodeMutation = useReconnectNode()
  const resetNodeUsageMutation = useResetNodeUsage()
  const updateNodeMutation = useUpdateNode()
  const getMenuStateSnapshot = useCallback(() => ensureNodeActionsMenuState(node), [node])
  const menuState = useSyncExternalStore(
    useCallback(listener => subscribeNodeActionsMenuState(node.id, listener), [node.id]),
    getMenuStateSnapshot,
    getMenuStateSnapshot,
  )

  const setMenuState = useCallback(
    (updater: Partial<NodeActionsMenuState> | ((prev: NodeActionsMenuState) => NodeActionsMenuState)) => {
      ensureNodeActionsMenuState(node)
      updateNodeActionsMenuState(node.id, prev => (typeof updater === 'function' ? updater(prev) : { ...prev, ...updater }))
    },
    [node, node.id],
  )

  const { isDeleteDialogOpen, isResetUsageDialogOpen, showOnlineStats, showUpdateCoreDialog, showUpdateGeofilesDialog } = menuState

  const setDeleteDialogOpen = useCallback((value: boolean) => setMenuState({ isDeleteDialogOpen: value }), [setMenuState])
  const setResetUsageDialogOpen = useCallback((value: boolean) => setMenuState({ isResetUsageDialogOpen: value }), [setMenuState])
  const setShowOnlineStats = useCallback((value: boolean) => setMenuState({ showOnlineStats: value }), [setMenuState])
  const setShowUpdateCoreDialog = useCallback((value: boolean) => setMenuState({ showUpdateCoreDialog: value }), [setMenuState])
  const setShowUpdateGeofilesDialog = useCallback((value: boolean) => setMenuState({ showUpdateGeofilesDialog: value }), [setMenuState])

  useEffect(() => {
    ensureNodeActionsMenuState(node)
    syncNodeSnapshot(node)
  }, [node])

  const isWireGuard = coresData?.cores?.find(core => core.id === node.core_config_id)?.type === 'wg'

  const handleDeleteClick = (event: Event) => {
    event.preventDefault()
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
    <>
      {renderActions && (
        <div className={className} onClick={e => e.stopPropagation()}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8">
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
                {node.status === 'disabled' ? <Power className="mr-2 h-4 w-4 shrink-0" /> : <PowerOff className="mr-2 h-4 w-4 shrink-0" />}
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
                {reconnecting ? <Loader2 className="mr-2 h-4 w-4 shrink-0 animate-spin" /> : <WifiSync className="mr-2 h-4 w-4 shrink-0" />}
                <span className="min-w-0 truncate">{reconnecting ? t('nodeModal.reconnecting') : t('nodeModal.reconnect')}</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={e => {
                  e.stopPropagation()
                  handleResetUsage()
                }}
                disabled={resettingUsage || syncing || reconnecting}
              >
                <RefreshCcw className="mr-2 h-4 w-4 shrink-0" />
                <span className="min-w-0 truncate">{t('nodeModal.resetUsage', { defaultValue: 'Reset' })}</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {!isWireGuard && (
                <>
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
                    <MapIcon className="mr-2 h-4 w-4 shrink-0" />
                    <span className="min-w-0 truncate">{t('nodeModal.updateGeofiles', { defaultValue: 'Update Geofiles' })}</span>
                  </DropdownMenuItem>
                </>
              )}
              <DropdownMenuItem
                onSelect={e => {
                  e.stopPropagation()
                  handleUpdateNode()
                }}
                disabled={syncing || reconnecting || resettingUsage || updatingNode}
              >
                {updatingNode ? <Loader2 className="mr-2 h-4 w-4 shrink-0 animate-spin" /> : <CircleFadingArrowUp className="mr-2 h-4 w-4 shrink-0" />}
                <span className="min-w-0 truncate">
                  {updatingNode ? t('nodeModal.updatingNode', { defaultValue: 'Updating Node...' }) : t('nodeModal.updateNode', { defaultValue: 'Update Node' })}
                </span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive focus:text-destructive">
                <Trash2 className="mr-2 h-4 w-4 shrink-0" />
                <span className="min-w-0 truncate">{t('delete')}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {isModalHost && (
        <div className="contents" onClick={e => e.stopPropagation()}>
          <DeleteAlertDialog node={node} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />
          <ResetUsageAlertDialog node={node} isOpen={isResetUsageDialogOpen} onClose={() => setResetUsageDialogOpen(false)} onConfirm={confirmResetUsage} isLoading={resettingUsage} />
          <UserOnlineStatsDialog isOpen={showOnlineStats} onOpenChange={setShowOnlineStats} nodeId={node.id} nodeName={node.name} />
          <UpdateCoreDialog node={node} isOpen={showUpdateCoreDialog} onOpenChange={setShowUpdateCoreDialog} />
          <UpdateGeofilesDialog node={node} isOpen={showUpdateGeofilesDialog} onOpenChange={setShowUpdateGeofilesDialog} />
        </div>
      )}
    </>
  )
}

export const NodeActionsMenuModalHost = () => {
  const modalStateVersion = useSyncExternalStore(subscribeGlobalNodeActionsMenuState, getGlobalNodeActionsMenuStateSnapshot, getGlobalNodeActionsMenuStateSnapshot)
  const nodesWithOpenDialogs = useMemo(() => getOpenDialogNodes(), [modalStateVersion])

  if (nodesWithOpenDialogs.length === 0) return null

  return (
    <div className="hidden" aria-hidden="true">
      {nodesWithOpenDialogs.map(node => (
        <NodeActionsMenu key={`node-action-dialog-host-${node.id}`} node={node} onEdit={() => undefined} onToggleStatus={async () => undefined} renderActions={false} />
      ))}
    </div>
  )
}
