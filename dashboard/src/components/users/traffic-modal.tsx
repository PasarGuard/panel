import React, { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { formatBytes } from '@/utils/formatByte'
import { Progress } from '@/components/ui/progress'
import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface NodeTrafficData {
  node_id: number
  node_name: string
  used_traffic: number
  data_limit: number | null
  has_limit: boolean
}

interface NodeTrafficResponse {
  nodes: NodeTrafficData[]
}

interface TrafficModalProps {
  username: string
  isOpen: boolean
  onClose: () => void
}

export const TrafficModal: React.FC<TrafficModalProps> = ({ username, isOpen, onClose }) => {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [nodeData, setNodeData] = useState<NodeTrafficData[]>([])
  const [error, setError] = useState<string | null>(null)
  const [dataLoaded, setDataLoaded] = useState(false)

  useEffect(() => {
    if (!isOpen || dataLoaded) return

    const loadNodeTraffic = async () => {
      setLoading(true)
      setError(null)
      try {
        const token = localStorage.getItem('token')
        const response = await fetch(`/api/user/${username}/node-traffic`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })

        if (!response.ok) {
          throw new Error('Failed to load node traffic')
        }

        const data: NodeTrafficResponse = await response.json()
        setNodeData(data.nodes || [])
        setDataLoaded(true)
      } catch (err) {
        console.error('Failed to load node traffic:', err)
        setError(t('failed_to_load_data'))
      } finally {
        setLoading(false)
      }
    }

    loadNodeTraffic()
  }, [isOpen, dataLoaded, username, t])

  return (
    <Dialog open={isOpen} onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[500px]" onClick={e => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>{t('traffic_by_node')}</DialogTitle>
          <DialogDescription>{t('traffic_details_for', { username })}</DialogDescription>
        </DialogHeader>

        <div className="mt-4 max-h-[60vh] space-y-4 overflow-y-auto pr-2">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-2 py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary/60" />
              <span className="text-sm text-muted-foreground">{t('loading')}...</span>
            </div>
          )}

          {error && <div className="py-4 text-center text-sm text-destructive">{error}</div>}

          {!loading && !error && nodeData.length === 0 && <div className="py-8 text-center text-sm italic text-muted-foreground">{t('no_traffic_data')}</div>}

          {!loading && !error && nodeData.length > 0 && (
            <div className="space-y-6">
              {nodeData.map(node => {
                const hasLimit = node.has_limit && node.data_limit !== null && node.data_limit > 0
                const percentage = hasLimit ? Math.min((node.used_traffic / node.data_limit!) * 100, 100) : 0

                return (
                  <div key={node.node_id} className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-semibold text-foreground/90">{node.node_name}</span>
                      <div className="flex items-center gap-1.5 font-mono text-xs">
                        <span className="text-foreground">{formatBytes(node.used_traffic)}</span>
                        {hasLimit && (
                          <>
                            <span className="opacity-30">/</span>
                            <span className="text-muted-foreground">{formatBytes(node.data_limit!)}</span>
                          </>
                        )}
                      </div>
                    </div>
                    {hasLimit ? <Progress value={percentage} className="h-2" /> : <div className="h-1 w-full rounded-full bg-muted/40" />}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
