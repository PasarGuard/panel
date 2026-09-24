import { Download as DownloadIcon, Loader2, Pause, Play } from 'lucide-react'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent } from '@/components/ui/card'
import { useGetNodesSimple } from '@/service/api'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { getAuthToken } from '@/utils/authStorage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import useDirDetection from '@/hooks/use-dir-detection'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { cn } from '@/lib/utils'
import { TerminalLine } from '@/features/nodes/components/terminal-line'
import { LineCountFilter } from '@/features/nodes/components/line-count-filter'
import { SinceLogsFilter, type TimeFilter } from '@/features/nodes/components/since-logs-filter'
import { StatusLogsFilter } from '@/features/nodes/components/status-logs-filter'
import { appendTrim, parseLogs, type LogLine } from '@/utils/logsUtils'
import { EventSource } from 'eventsource'

/** Max raw SSE chunks kept in memory; display "lines" is sliced client-side (no reconnect). */
const RAW_LOG_BUFFER_MAX = 10000
const LOG_FLUSH_MS = 100

const SINCE_DURATION_MS: Record<Exclude<TimeFilter, 'all'>, number> = {
  '1m': 60 * 1000,
  '5m': 5 * 60 * 1000,
  '15m': 15 * 60 * 1000,
  '30m': 30 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '2h': 2 * 60 * 60 * 1000,
  '6h': 6 * 60 * 60 * 1000,
  '12h': 12 * 60 * 60 * 1000,
  '24h': 24 * 60 * 60 * 1000,
}

export const priorities = [
  {
    label: 'nodes.logs.info',
    value: 'info',
  },
  {
    label: 'nodes.logs.warning',
    value: 'warning',
  },
  {
    label: 'nodes.logs.debug',
    value: 'debug',
  },
  {
    label: 'nodes.logs.error',
    value: 'error',
  },
]

export default function NodeLogs() {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [selectedNode, setSelectedNode] = useState<number>(0)
  const [rawLogs, setRawLogs] = useState<LogLine[]>([])
  const [lines, setLines] = useState<number>(1000)
  const { search, debouncedSearch, setSearch } = useDebouncedSearch('', 200)
  const [showTimestamp, setShowTimestamp] = useState(true)
  const [since, setSince] = useState<TimeFilter>('all')
  const [typeFilter, setTypeFilter] = useState<string[]>([])
  const [isPaused, setIsPaused] = useState(false)
  const [messageBuffer, setMessageBuffer] = useState<LogLine[]>([])
  const isPausedRef = useRef(false)
  const autoScrollRef = useRef(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [isLoading, setIsLoading] = useState(false)

  const eventSourceRef = useRef<EventSource | null>(null)

  const { data: nodesResponse } = useGetNodesSimple({ all: true })
  const nodes = nodesResponse?.nodes || []

  // Filter to only show connected nodes
  const connectedNodes = useMemo(() => nodes.filter(node => node.status === 'connected'), [nodes])

  // Auto-select first connected node if available and none is selected
  useEffect(() => {
    if (connectedNodes.length > 0 && selectedNode === 0) {
      setSelectedNode(connectedNodes[0].id)
    }
    // Reset selection if selected node is no longer connected
    if (selectedNode !== 0 && !connectedNodes.find(node => node.id === selectedNode)) {
      setSelectedNode(0)
    }
  }, [connectedNodes, selectedNode])

  const scrollToBottom = () => {
    if (autoScrollRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }

  const handleScroll = () => {
    if (!scrollRef.current) return

    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 10
    if (isAtBottom !== autoScrollRef.current) {
      autoScrollRef.current = isAtBottom
    }
  }

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value || '')
  }

  const handleLines = (nextLines: number) => {
    setLines(nextLines)
  }

  const handleSince = (value: TimeFilter) => {
    setSince(value)
  }

  const handlePauseResume = () => {
    if (isPaused) {
      // Resume: Apply all buffered messages
      if (messageBuffer.length > 0) {
        setRawLogs(prev => appendTrim(prev, messageBuffer, RAW_LOG_BUFFER_MAX))
        setMessageBuffer([])
      }
    }
    const newPausedState = !isPaused
    setIsPaused(newPausedState)
    isPausedRef.current = newPausedState
  }

  // Handle node selection change
  const handleNodeChange = (nodeId: number) => {
    setSelectedNode(nodeId)
    setRawLogs([])
    setMessageBuffer([])
    setIsPaused(false)
    isPausedRef.current = false
    autoScrollRef.current = true
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }

  useEffect(() => {
    if (selectedNode === 0) {
      setIsLoading(false)
      return
    }

    let isCurrentConnection = true
    let noDataTimeout: ReturnType<typeof setTimeout>
    let flushTimer: ReturnType<typeof setTimeout> | null = null
    const pending: LogLine[] = []
    let loadingCleared = false
    setIsLoading(true)
    setRawLogs([])
    setMessageBuffer([])
    // Reset pause state when container changes
    setIsPaused(false)
    isPausedRef.current = false
    autoScrollRef.current = true

    const flushPending = () => {
      flushTimer = null
      if (!isCurrentConnection || pending.length === 0) {
        pending.length = 0
        return
      }
      const batch = pending.splice(0, pending.length)
      if (isPausedRef.current) {
        setMessageBuffer(prev => appendTrim(prev, batch, RAW_LOG_BUFFER_MAX))
      } else {
        setRawLogs(prev => appendTrim(prev, batch, RAW_LOG_BUFFER_MAX))
      }
    }

    const baseUrl =
      import.meta.env.VITE_BASE_API && typeof import.meta.env.VITE_BASE_API === 'string' && import.meta.env.VITE_BASE_API.trim() !== '/' && import.meta.env.VITE_BASE_API.startsWith('http')
        ? import.meta.env.VITE_BASE_API
        : window.location.origin
    const token = getAuthToken()

    const url = `${baseUrl}/api/node/${selectedNode}/logs`
    const eventSource = new EventSource(url, {
      fetch: (input, init) =>
        fetch(input, {
          ...init,
          headers: {
            ...init?.headers,
            Authorization: `Bearer ${token}`,
          },
        }),
    })

    eventSourceRef.current = eventSource

    const resetNoDataTimeout = () => {
      if (noDataTimeout) clearTimeout(noDataTimeout)
      noDataTimeout = setTimeout(() => {
        if (isCurrentConnection) {
          setIsLoading(false)
        }
      }, 2000) // Wait 2 seconds for data before showing "No logs found"
    }

    eventSource.onopen = () => {
      if (!isCurrentConnection) {
        eventSource.close()
        return
      }
      resetNoDataTimeout()
    }

    eventSource.onmessage = e => {
      if (!isCurrentConnection) return

      const parsedLogs = parseLogs(e.data)
      if (parsedLogs.length === 0) return

      pending.push(...parsedLogs)
      if (!loadingCleared) {
        loadingCleared = true
        setIsLoading(false)
      }
      if (noDataTimeout) clearTimeout(noDataTimeout)
      if (flushTimer == null) {
        flushTimer = setTimeout(flushPending, LOG_FLUSH_MS)
      }
    }

    eventSource.onerror = error => {
      if (!isCurrentConnection) return
      console.error('SSE error:', error)
      setIsLoading(false)
      if (noDataTimeout) clearTimeout(noDataTimeout)
    }

    return () => {
      isCurrentConnection = false
      if (noDataTimeout) clearTimeout(noDataTimeout)
      if (flushTimer != null) clearTimeout(flushTimer)
      pending.length = 0
      eventSource.close()
    }
  }, [selectedNode])

  // Sync isPausedRef with isPaused state
  useEffect(() => {
    isPausedRef.current = isPaused
  }, [isPaused])

  const filteredLogs = useMemo(() => {
    const query = (debouncedSearch || '').toLowerCase()
    const cutoffMs = since === 'all' ? null : Date.now() - SINCE_DURATION_MS[since]
    const hasTypeFilter = typeFilter.length > 0

    const noTimestamp: LogLine[] = []
    const timestamped: LogLine[] = []
    for (let i = 0; i < rawLogs.length; i++) {
      const log = rawLogs[i]
      if (hasTypeFilter && !typeFilter.includes(log.type)) continue
      if (query && !log.message.toLowerCase().includes(query)) continue
      if (cutoffMs !== null && log.timestamp && log.timestamp.getTime() < cutoffMs) continue
      if (!log.timestamp) noTimestamp.push(log)
      else timestamped.push(log)
    }
    const visibleTimestamped = timestamped.length > lines ? timestamped.slice(-lines) : timestamped
    return noTimestamp.length === 0 ? visibleTimestamped : noTimestamp.concat(visibleTimestamped)
  }, [rawLogs, debouncedSearch, lines, since, typeFilter])

  useEffect(() => {
    scrollToBottom()
  }, [filteredLogs])

  const handleDownload = () => {
    const logContent = filteredLogs.map(({ timestamp, message }: { timestamp: Date | null; message: string }) => `${timestamp?.toISOString() || 'No timestamp'} ${message}`).join('\n')

    const blob = new Blob([logContent], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const nodeName = nodes.find(n => n.id === selectedNode)?.name || t('nodes.title', { defaultValue: 'Node' })
    const isoDate = new Date().toISOString()
    a.href = url
    a.download = `${nodeName}-${isoDate.slice(0, 10).replace(/-/g, '')}_${isoDate.slice(11, 19).replace(/:/g, '')}.log.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className={cn('flex w-full min-w-0 flex-col gap-3 p-3 sm:gap-4 sm:p-4', dir === 'rtl' && 'rtl')}>
      <div className="flex min-w-0 flex-col gap-2 sm:gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className="min-w-0 flex-1 sm:max-w-[250px]">
            <Label htmlFor="node-select" className="sr-only">
              {t('nodes.title')}
            </Label>
            <Select value={selectedNode.toString()} onValueChange={value => handleNodeChange(Number(value))} disabled={connectedNodes.length === 0}>
              <SelectTrigger id="node-select" className="h-9 w-full min-w-0 overflow-hidden text-sm" disabled={connectedNodes.length === 0}>
                <SelectValue placeholder={connectedNodes.length === 0 ? t('nodes.noNodes') : t('nodes.selectNode')} />
              </SelectTrigger>
              <SelectContent>
                {connectedNodes.map(node => (
                  <SelectItem key={node.id} value={node.id.toString()} className="text-sm">
                    {node.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex shrink-0 gap-2">
            <Button variant="outline" size="sm" className="h-9 px-2.5 sm:px-3" onClick={handlePauseResume} title={isPaused ? t('nodes.logs.resume') : t('nodes.logs.pause')}>
              {isPaused ? <Play className="h-4 w-4 sm:me-2" /> : <Pause className="h-4 w-4 sm:me-2" />}
              <span className="hidden sm:inline">{isPaused ? t('nodes.logs.resume') : t('nodes.logs.pause')}</span>
            </Button>
            <Button variant="outline" size="sm" className="h-9 px-2.5 sm:px-3" onClick={handleDownload} disabled={filteredLogs.length === 0} title={t('nodes.logs.download')}>
              <DownloadIcon className="h-4 w-4 sm:me-2" />
              <span className="hidden sm:inline">{t('nodes.logs.download')}</span>
            </Button>
          </div>
        </div>

        <div className="grid min-w-0 grid-cols-2 gap-2 lg:flex lg:flex-wrap lg:items-center">
          <LineCountFilter value={lines} onValueChange={handleLines} />

          <SinceLogsFilter value={since} onValueChange={handleSince} showTimestamp={showTimestamp} onTimestampChange={setShowTimestamp} />

          <div className="w-full min-w-0 lg:w-auto">
            <StatusLogsFilter value={typeFilter} setValue={setTypeFilter} title={t('nodes.logs.filter')} options={priorities} />
          </div>

          <div className="col-span-2 w-full min-w-0 lg:w-56 xl:w-72">
            <Input type="search" placeholder={t('nodes.logs.search')} value={search} onChange={handleSearch} className="h-9 text-sm" />
          </div>
        </div>

        {isPaused && (
          <Alert className="border-amber-500/50 bg-amber-500/15 text-amber-700 dark:text-amber-400">
            <Pause className="h-4 w-4" />
            <AlertDescription>
              {t('nodes.logs.paused')}
              {messageBuffer.length > 0 && (
                <span className="ms-1 font-medium">
                  ({messageBuffer.length} {t('nodes.logs.messagesBuffered')})
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}
      </div>

      <Card className="bg-background min-w-0">
        <CardContent className="p-1 sm:p-2">
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            dir="ltr"
            className="custom-logs-scrollbar bg-background/75 h-[calc(100vh-280px)] max-h-[720px] min-h-[400px] space-y-0 overflow-x-hidden overflow-y-auto rounded sm:h-[720px] sm:min-h-0"
          >
            {filteredLogs.length > 0 ? (
              filteredLogs.map((filteredLog: LogLine) => <TerminalLine key={filteredLog.id} log={filteredLog} searchTerm={debouncedSearch || ''} noTimestamp={!showTimestamp} />)
            ) : isLoading ? (
              <div className="text-muted-foreground flex h-full items-center justify-center">
                <Loader2 className="h-6 w-6" />
              </div>
            ) : (
              <div className="text-muted-foreground flex h-full items-center justify-center px-4 text-center">{t('nodes.logs.noLogs')}</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
