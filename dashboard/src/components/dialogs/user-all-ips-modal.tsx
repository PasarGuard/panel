import { useState, useEffect, useMemo, useCallback } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTranslation } from 'react-i18next'
import { useUserOnlineIpListAllNodes, useGetNodes } from '@/service/api'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { useClipboard } from '@/hooks/use-clipboard'
import { Network, RefreshCw, Loader2, AlertCircle, Server } from 'lucide-react'
import { toast } from 'sonner'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import React from 'react'

interface UserAllIPsModalProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  username: string
  ipLimit?: number | null
}

interface NodeIPCardProps {
  nodeId: string
  nodeName: string
  ips: { [key: string]: number }
}

const NodeIPCard = React.memo(({ nodeId, nodeName, ips }: NodeIPCardProps) => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { copy } = useClipboard()

  const handleCopyIP = useCallback(
    async (ip: string) => {
      await copy(ip)
      toast.success(t('userAllIPs.ipCopied', { defaultValue: 'IP address copied to clipboard' }))
    },
    [copy, t],
  )

  const ipEntries = useMemo(() => {
    return Object.entries(ips)
      .map(([ip, timestamp]) => {
        let tsNum = Number(timestamp)
        if (tsNum < 1e12) tsNum = tsNum * 1000
        const date = new Date(tsNum)
        const timeString = date.toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        })
        return { ip, timestamp: tsNum, timeString }
      })
      .sort((a, b) => b.timestamp - a.timestamp)
  }, [ips])

  const totalIPs = useMemo(() => {
    return Object.keys(ips).length
  }, [ips])

  return (
    <Card className="transition-colors hover:bg-accent/50">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <Server className="h-4 w-4 text-primary" />
            <span className="break-all" dir="ltr">
              {nodeName || t('userAllIPs.nodeId', { defaultValue: 'Node #{{nodeId}}', nodeId })}
            </span>
          </CardTitle>
          <Badge dir={dir} variant="outline" className="border-0 px-0 text-xs">
            {t('userAllIPs.totalIPs', {
              defaultValue: totalIPs === 1 ? '{{count}} IP address' : '{{count}} IP addresses',
              count: totalIPs,
            })}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {ipEntries.map(({ ip, timeString }) => (
              <div key={ip} className="rounded bg-accent/40 p-2 transition-colors hover:bg-accent/60">
                <div className="flex flex-col gap-1">
                  <span
                    className="cursor-pointer break-all font-mono text-sm font-medium transition-colors hover:text-primary"
                    dir="ltr"
                    onClick={() => handleCopyIP(ip)}
                    title={t('userAllIPs.clickToCopy', { defaultValue: 'Click to copy IP address' })}
                  >
                    {ip}
                  </span>
                  <div dir={dir} className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">{t('userAllIPs.lastSeen', { defaultValue: 'Last seen' })}:</span>
                    <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                      {timeString}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
})

NodeIPCard.displayName = 'NodeIPCard'

const LoadingState = React.memo(() => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <div className="flex h-32 flex-col items-center justify-center gap-2">
      <Loader2 className="h-6 w-6 animate-spin" />
      <span className="text-sm" dir={dir}>
        {t('loading', { defaultValue: 'Loading...' })}
      </span>
    </div>
  )
})

LoadingState.displayName = 'LoadingState'

const ErrorState = React.memo(({ message }: { message: string }) => {
  const dir = useDirDetection()

  return (
    <div className="flex h-32 flex-col items-center justify-center gap-2 px-4 text-center text-muted-foreground">
      <AlertCircle className="h-5 w-5" />
      <span className="text-sm" dir={dir}>
        {message}
      </span>
    </div>
  )
})

ErrorState.displayName = 'ErrorState'

const EmptyState = React.memo(({ message }: { message: string }) => {
  const dir = useDirDetection()

  return (
    <div className="flex h-32 flex-col items-center justify-center gap-2 px-4 text-center text-muted-foreground">
      <Network className="h-5 w-5" />
      <span className="text-sm" dir={dir}>
        {message}
      </span>
    </div>
  )
})

EmptyState.displayName = 'EmptyState'

export default function UserAllIPsModal({ isOpen, onOpenChange, username, ipLimit }: UserAllIPsModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [refreshing, setRefreshing] = useState(false)
  const userCloseRef = React.useRef(false)

  useEffect(() => {
    if (!isOpen) {
      setRefreshing(false)
    }
  }, [isOpen])

  const { data: nodesResponse } = useGetNodes(undefined, {
    query: {
      enabled: isOpen,
      staleTime: 5 * 60 * 1000,
    },
  })
  const nodeNameMap = useMemo(() => {
    const map: { [nodeId: string]: string } = {}
    const nodesData = nodesResponse?.nodes || []
    if (nodesData && Array.isArray(nodesData)) {
      nodesData.forEach(node => {
        map[String(node.id)] = node.name
      })
    }
    return map
  }, [nodesResponse])

  const userIPsQueryOptions = useMemo(
    () => ({
      query: {
        enabled: !!(isOpen && username),
        refetchInterval: (query: any) => {
          if (!isOpen || query.state.error) {
            return false
          }
          return 10000
        },
      },
    }),
    [isOpen, username],
  )
  const { data: userIPsData, isLoading, error, refetch: refetchIPs } = useUserOnlineIpListAllNodes(username, userIPsQueryOptions)

  const handleError = useCallback(
    (error: any) => {
      const errorMessage = error?.message || 'Unknown error occurred'
      if (errorMessage.includes('User not found')) {
        toast.error(
          t('userAllIPs.userNotFound', {
            defaultValue: 'User "{{username}}" not found or currently offline',
            username,
          }),
        )
      } else {
        toast.error(
          t('userAllIPs.errorLoading', {
            defaultValue: 'Unable to load IP addresses: {{message}}',
            message: errorMessage,
          }),
        )
      }
    },
    [t, username],
  )

  useEffect(() => {
    if (error && isOpen) {
      handleError(error)
    }
  }, [error, isOpen, handleError])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await refetchIPs()
      toast.success(t('userAllIPs.refreshed', { defaultValue: 'IP addresses updated' }))
    } catch (error) {
      toast.error(t('userAllIPs.refreshFailed', { defaultValue: 'Failed to refresh IP addresses' }))
    } finally {
      setRefreshing(false)
    }
  }, [refetchIPs, t])

  const transformedData = useMemo(() => {
    if (!userIPsData || typeof userIPsData !== 'object') return null

    const nodes: { nodeId: string; nodeName: string; ips: { [key: string]: number } }[] = []

    if (userIPsData.nodes && typeof userIPsData.nodes === 'object') {
      Object.entries(userIPsData.nodes).forEach(([nodeId, ipList]) => {
        if (ipList && ipList.ips && typeof ipList.ips === 'object') {
          nodes.push({
            nodeId,
            nodeName: nodeNameMap[nodeId] || nodeId,
            ips: ipList.ips,
          })
        }
      })
    }

    return nodes.length > 0 ? nodes : null
  }, [userIPsData, nodeNameMap])

  const totalConnections = useMemo(() => {
    if (!transformedData) return 0
    return transformedData.reduce((sum, node) => {
      return sum + Object.values(node.ips).reduce((s, count) => s + count, 0)
    }, 0)
  }, [transformedData])

  const renderIPList = useCallback(() => {
    if (isLoading) {
      return <LoadingState />
    }

    if (error) {
      return (
        <ErrorState
          message={t('userAllIPs.errorLoading', {
            defaultValue: 'Unable to load IP addresses. Please try again.',
          })}
        />
      )
    }

    if (!transformedData || transformedData.length === 0) {
      return (
        <EmptyState
          message={t('userAllIPs.noIPs', {
            defaultValue: 'No active IP addresses found. This user may not be currently connected to any nodes.',
          })}
        />
      )
    }

    return (
      <div className="space-y-3">
        {transformedData.map(({ nodeId, nodeName, ips }) => (
          <NodeIPCard key={nodeId} nodeId={nodeId} nodeName={nodeName} ips={ips} />
        ))}
      </div>
    )
  }, [isLoading, error, transformedData, t])

  const dialogTitle = useMemo(() => {
    return t('userAllIPs.title', {
      defaultValue: 'IP Addresses - {{username}}',
      username,
    })
  }, [username, t])

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (open) {
        onOpenChange(true)
        return
      }

      // Always allow closing - user should be able to close the dialog
      userCloseRef.current = false
      onOpenChange(false)
    },
    [onOpenChange],
  )

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent
        className="flex h-[90vh] max-w-full flex-col sm:h-[600px] sm:max-w-2xl"
        onInteractOutside={() => {
          userCloseRef.current = true
          onOpenChange(false)
        }}
        onEscapeKeyDown={() => {
          userCloseRef.current = true
          onOpenChange(false)
        }}
      >
        <DialogHeader>
          <DialogTitle className={cn('flex items-center gap-2 text-xl font-semibold', dir === 'rtl' && 'sm:text-right')}>
            <Network className="h-5 w-5" />
            <span>{dialogTitle}</span>
          </DialogTitle>
          <DialogDescription className="sr-only">
            {t('userAllIPs.description', {
              defaultValue: 'View all IP addresses associated with user {{username}} across all nodes',
              username,
            })}
          </DialogDescription>
        </DialogHeader>

        {ipLimit != null && ipLimit > 0 && (
          <Badge variant={totalConnections > ipLimit ? 'destructive' : 'outline'} className="text-sm">
            {t('userAllIPs.connectionCount', {
              defaultValue: '{{current}} / {{limit}} connections',
              current: totalConnections,
              limit: ipLimit,
            })}
          </Badge>
        )}

        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={handleRefresh} disabled={refreshing || isLoading} className="flex-1 sm:flex-none">
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
            <span className={cn(dir === 'rtl' ? 'mr-2' : 'ml-2')}>{t('userAllIPs.refresh', { defaultValue: 'Refresh' })}</span>
          </Button>
        </div>

        <Separator />

        <div className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="p-1">{renderIPList()}</div>
          </ScrollArea>
        </div>

        {isOpen && (
          <div className="flex items-center justify-center gap-2 border-t py-2 text-center text-xs text-muted-foreground">
            <Network className="inline h-3 w-3" />
            <span dir={dir}>
              {t('userAllIPs.autoRefresh', {
                defaultValue: 'Auto-refresh: every {{seconds}} seconds',
                seconds: 10,
              })}
            </span>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
