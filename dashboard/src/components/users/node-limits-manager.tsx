import { useState, useEffect } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Loader2, Trash2 } from 'lucide-react'
import { gbToBytes } from '@/utils/formatByte'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface NodeLimit {
  node_id: number
  node_name: string
  data_limit: number | null // in bytes, null = no limit
  current_limit_id?: number // ID if limit already exists in DB
}

interface NodeLimitsManagerProps {
  userId?: number
  username?: string
  isEditMode: boolean
}

// Helper to convert bytes to GB
const bytesToGb = (bytes: number): number => {
  return bytes / (1024 * 1024 * 1024)
}

export function NodeLimitsManager({ userId, isEditMode }: NodeLimitsManagerProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [nodeLimits, setNodeLimits] = useState<NodeLimit[]>([])
  const [hasChanges, setHasChanges] = useState(false)

  // Fetch nodes and existing limits
  useEffect(() => {
    if (!isEditMode || !userId) {
      setLoading(false)
      return
    }

    const fetchData = async () => {
      try {
        const token = localStorage.getItem('token')

        // Fetch all nodes
        const nodesResponse = await fetch('/api/nodes', {
          headers: { Authorization: `Bearer ${token}` },
        })
        const nodesData = await nodesResponse.json()

        // Fetch existing limits for this user
        const limitsResponse = await fetch(`/api/node-user-limits/user/${userId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        const limitsData = await limitsResponse.json()

        // Combine data
        interface LimitInfo {
          data_limit: number
          limit_id: number
        }

        const limitsMap = new Map<number, LimitInfo>(
          (limitsData.limits || []).map((limit: { node_id: number; data_limit: number; id: number }) => [limit.node_id, { data_limit: limit.data_limit, limit_id: limit.id }]),
        )

        interface NodeItem {
          id: number
          name: string
        }

        // API returns {nodes: [...]} format
        const nodesList = nodesData?.nodes || nodesData?.items || nodesData || []
        const combined: NodeLimit[] = (nodesList as NodeItem[]).map(node => ({
          node_id: node.id,
          node_name: node.name,
          data_limit: limitsMap.get(node.id)?.data_limit ?? null,
          current_limit_id: limitsMap.get(node.id)?.limit_id,
        }))

        setNodeLimits(combined)
      } catch (error) {
        console.error('Failed to load node limits:', error)
        toast.error(t('failed_to_load_data'))
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [userId, isEditMode, t])

  const handleLimitChange = (nodeId: number, gbValue: string) => {
    const numValue = parseFloat(gbValue)
    const bytesValue: number | null = isNaN(numValue) || gbValue === '' ? null : (gbToBytes(numValue) ?? null)

    setNodeLimits(prev => prev.map(node => (node.node_id === nodeId ? { ...node, data_limit: bytesValue } : node)))
    setHasChanges(true)
  }

  const handleSave = async () => {
    if (!userId) {
      toast.error('User ID is required')
      return
    }

    setSaving(true)
    try {
      const token = localStorage.getItem('token')

      for (const node of nodeLimits) {
        const hasLimit = node.data_limit !== null && node.data_limit > 0
        const hadLimit = node.current_limit_id !== undefined

        if (hasLimit && !hadLimit) {
          // Create new limit
          await fetch('/api/node-user-limits', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              user_id: userId,
              node_id: node.node_id,
              data_limit: node.data_limit,
              data_limit_reset_strategy: 'no_reset',
              reset_time: -1,
            }),
          })
        } else if (hasLimit && hadLimit) {
          // Update existing limit
          await fetch(`/api/node-user-limits/${node.current_limit_id}`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              data_limit: node.data_limit,
              data_limit_reset_strategy: 'no_reset',
              reset_time: -1,
            }),
          })
        } else if (!hasLimit && hadLimit) {
          // Delete limit
          await fetch(`/api/node-user-limits/${node.current_limit_id}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
          })
        }
      }

      toast.success(t('saved_successfully'))
      setHasChanges(false)

      // Refresh data
      const limitsResponse = await fetch(`/api/node-user-limits/user/${userId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const limitsData = await limitsResponse.json()

      interface LimitResult {
        data_limit: number
        limit_id: number
      }

      const limitsMap = new Map<number, LimitResult>(
        (limitsData.limits || []).map((limit: { node_id: number; data_limit: number; id: number }) => [limit.node_id, { data_limit: limit.data_limit, limit_id: limit.id }]),
      )
      setNodeLimits(prev =>
        prev.map(node => ({
          ...node,
          data_limit: limitsMap.get(node.node_id)?.data_limit || null,
          current_limit_id: limitsMap.get(node.node_id)?.limit_id,
        })),
      )
    } catch (error) {
      console.error('Failed to save limits:', error)
      toast.error(t('failed_to_save'))
    } finally {
      setSaving(false)
    }
  }

  if (!isEditMode) {
    return <div className="py-4 text-sm text-muted-foreground">{t('per_node_limits_only_edit', { defaultValue: 'Per-node limits can only be set when editing an existing user.' })}</div>
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="text-sm text-muted-foreground">
        {t('per_node_limits_description', {
          defaultValue: 'Set individual data limits for each node. Leave empty for no limit.',
        })}
      </div>

      <div className="space-y-2">
        {nodeLimits.map(node => {
          const gbValue = node.data_limit !== null ? bytesToGb(node.data_limit) : ''

          return (
            <div key={node.node_id} className="flex items-center gap-3 rounded-lg border p-3">
              <div className="flex-1">
                <Label className="text-sm font-medium">{node.node_name}</Label>
              </div>
              <div className="flex items-center gap-2">
                <Input type="number" min="0" step="0.1" value={gbValue} onChange={e => handleLimitChange(node.node_id, e.target.value)} placeholder="No limit" className="h-8 w-24 text-sm" />
                <span className="text-xs text-muted-foreground">GB</span>
                {node.data_limit !== null && (
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleLimitChange(node.node_id, '')}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {hasChanges && (
        <div className="flex justify-end">
          <Button type="button" onClick={handleSave} disabled={saving} className="gap-2">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('save', { defaultValue: 'Save' })}
          </Button>
        </div>
      )}
    </div>
  )
}
