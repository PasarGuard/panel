import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { useResetUserDataUsage, useResetUserNodeUsage } from '@/service/api'
import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface ResetUsageDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  username: string
  onSuccess: () => void
}

interface NodeItem {
  node_id: number
  node_name: string
  used_traffic: number
}

export function ResetUsageDialog({ open, onOpenChange, username, onSuccess }: ResetUsageDialogProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [nodes, setNodes] = useState<NodeItem[]>([])
  const [selectedNodes, setSelectedNodes] = useState<number[]>([])
  const [resetMode, setResetMode] = useState<'all' | 'custom'>('all')
  const [fetchingError, setFetchingError] = useState<string | null>(null)

  const resetAllMutation = useResetUserDataUsage({
    mutation: {
      onSuccess: () => {
        toast.success(t('usersTable.resetUsageSuccess', { name: username }))
        onSuccess()
        onOpenChange(false)
      },
      onError: (error: any) => {
        toast.error(t('usersTable.resetUsageFailed', { name: username, error: error?.message || '' }))
      },
    },
  })

  const resetNodeUsageMutation = useResetUserNodeUsage({
    mutation: {
      onSuccess: () => {
        toast.success(t('usersTable.resetUsageSuccess', { name: username }))
        onSuccess()
        onOpenChange(false)
      },
      onError: (error: any) => {
        toast.error(t('usersTable.resetUsageFailed', { name: username, error: error?.message || '' }))
      },
    },
  })

  const fetchNodes = useCallback(async () => {
    setLoading(true)
    setFetchingError(null)
    try {
      const token = localStorage.getItem('token')
      const response = await fetch(`/api/user/${username}/node-traffic`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to load nodes')
      const data = await response.json()
      setNodes(data.nodes || [])
    } catch (err) {
      console.error(err)
      setFetchingError('Failed to load node data')
    } finally {
      setLoading(false)
    }
  }, [username])

  useEffect(() => {
    if (open) {
      fetchNodes()
      setResetMode('all')
      setSelectedNodes([])
    }
  }, [open, fetchNodes])

  const handleConfirm = () => {
    if (resetMode === 'all') {
      resetAllMutation.mutate({ username })
    } else {
      if (selectedNodes.length === 0) {
        toast.error(t('select_at_least_one_node'))
        return
      }
      resetNodeUsageMutation.mutate({ username, data: { node_ids: selectedNodes } })
    }
  }

  const toggleNode = (nodeId: number) => {
    setSelectedNodes(prev => (prev.includes(nodeId) ? prev.filter(id => id !== nodeId) : [...prev, nodeId]))
  }

  const isPending = resetAllMutation.isPending || resetNodeUsageMutation.isPending

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('usersTable.resetUsageTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('usersTable.resetUsagePrompt', { name: username })}</AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-4 py-4">
          <div className="flex flex-col gap-2">
            <Label className="font-semibold">{t('reset_mode')}</Label>
            <div className="flex gap-4">
              <div className="flex items-center gap-2">
                <Checkbox id="mode-all" checked={resetMode === 'all'} onCheckedChange={() => setResetMode('all')} />
                <Label htmlFor="mode-all" className="cursor-pointer font-normal">
                  {t('reset_all_nodes')}
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="mode-custom" checked={resetMode === 'custom'} onCheckedChange={() => setResetMode('custom')} />
                <Label htmlFor="mode-custom" className="cursor-pointer font-normal">
                  {t('reset_specific_nodes')}
                </Label>
              </div>
            </div>
          </div>

          {resetMode === 'custom' && (
            <div className="max-h-[200px] space-y-2 overflow-y-auto rounded-md border p-3">
              {loading ? (
                <div className="flex justify-center py-4">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : fetchingError ? (
                <div className="text-sm text-destructive">{fetchingError}</div>
              ) : nodes.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground">No traffic data found</div>
              ) : (
                nodes.map(node => (
                  <div key={node.node_id} className="flex items-center gap-2">
                    <Checkbox id={`node-${node.node_id}`} checked={selectedNodes.includes(node.node_id)} onCheckedChange={() => toggleNode(node.node_id)} />
                    <Label htmlFor={`node-${node.node_id}`} className="flex-1 cursor-pointer truncate text-sm font-normal">
                      {node.node_name}
                    </Label>
                    <span className="text-xs text-muted-foreground">{(node.used_traffic / (1024 * 1024 * 1024)).toFixed(2)} GB</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => onOpenChange(false)} disabled={isPending}>
            {t('usersTable.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} disabled={isPending || (resetMode === 'custom' && selectedNodes.length === 0)}>
            {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('usersTable.resetUsageSubmit')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
