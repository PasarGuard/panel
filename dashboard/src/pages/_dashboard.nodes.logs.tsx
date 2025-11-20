import { Download as DownloadIcon, Loader2, Pause, Play } from 'lucide-react'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent } from '@/components/ui/card'
import { useGetNodes } from '@/service/api'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { getAuthToken } from '@/utils/authStorage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription } from '@/components/ui/alert'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { TerminalLine } from '@/components/nodes/terminal-line'
import { LineCountFilter } from '@/components/nodes/line-count-filter'
import { SinceLogsFilter, type TimeFilter } from '@/components/nodes/since-logs-filter'
import { StatusLogsFilter } from '@/components/nodes/status-logs-filter'
import { parseLogs, getLogType, type LogLine } from '@/utils/logsUtils'
import { EventSource } from 'eventsource'

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
  const [rawLogs, setRawLogs] = React.useState<string[]>([])
  const [filteredLogs, setFilteredLogs] = React.useState<LogLine[]>([])
  const [autoScroll, setAutoScroll] = React.useState(true)
  const [lines, setLines] = React.useState<number>(100)
  const [search, setSearch] = React.useState<string>('')
  const [showTimestamp, setShowTimestamp] = React.useState(true)
  const [since, setSince] = React.useState<TimeFilter>('all')
  const [typeFilter, setTypeFilter] = React.useState<string[]>([])
  const [isPaused, setIsPaused] = React.useState(false)
  const [messageBuffer, setMessageBuffer] = React.useState<string[]>([])
  const isPausedRef = useRef(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [isLoading, setIsLoading] = React.useState(false)

  const eventSourceRef = useRef<EventSource | null>(null)

  const { data: nodesResponse } = useGetNodes({})
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
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }

  const handleScroll = () => {
    if (!scrollRef.current) return

    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 10
    setAutoScroll(isAtBottom)
  }

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value || '')
  }

  const handleLines = (lines: number) => {
    setRawLogs([])
    setFilteredLogs([])
    setMessageBuffer([])
    setLines(lines)
  }

  const handleSince = (value: TimeFilter) => {
    setRawLogs([])
    setFilteredLogs([])
    setMessageBuffer([])
    setSince(value)
  }

  const handlePauseResume = () => {
    if (isPaused) {
      // Resume: Apply all buffered messages
      if (messageBuffer.length > 0) {
        setRawLogs(prev => {
          const combined = [...prev, ...messageBuffer]
          return combined.slice(-lines)
        })
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
    setFilteredLogs([])
    setMessageBuffer([])
    setIsPaused(false)
    isPausedRef.current = false
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
    let noDataTimeout: NodeJS.Timeout
    setIsLoading(true)
    setRawLogs([])
    setFilteredLogs([])
    setMessageBuffer([])
    // Reset pause state when container changes
    setIsPaused(false)
    isPausedRef.current = false

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

      if (isPausedRef.current) {
        // When paused, buffer the messages instead of displaying them
        setMessageBuffer(prev => [...prev, e.data])
      } else {
        // When not paused, display messages normally
        setRawLogs(prev => {
          const updated = [...prev, e.data]
          return updated.slice(-lines)
        })
      }

      setIsLoading(false)
      if (noDataTimeout) clearTimeout(noDataTimeout)
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
      if (eventSource.readyState === EventSource.OPEN) {
        eventSource.close()
      }
    }
  }, [selectedNode, lines])

  const handleFilter = (logs: LogLine[]) => {
    return logs.filter(log => {
      const logType = getLogType(log.message).type

      // Filter by type
      if (typeFilter.length > 0 && !typeFilter.includes(logType)) {
        return false
      }

      // Filter by search term
      if (search && !log.message.toLowerCase().includes(search.toLowerCase())) {
        return false
      }

      return true
    })
  }

  // Sync isPausedRef with isPaused state
  useEffect(() => {
    isPausedRef.current = isPaused
  }, [isPaused])

  useEffect(() => {
    setRawLogs([])
    setFilteredLogs([])
    setMessageBuffer([])
  }, [selectedNode])

  useEffect(() => {
    const logs = parseLogs(rawLogs.join('\n'))

    // Sort logs by their extracted timestamps (not SSE arrival time)
    const sortedLogs = logs.sort((a, b) => {
      // Logs without timestamps go to the end
      if (!a.timestamp && !b.timestamp) return 0
      if (!a.timestamp) return 1
      if (!b.timestamp) return -1

      // Sort by actual log timestamp
      return a.timestamp.getTime() - b.timestamp.getTime()
    })

    const filtered = handleFilter(sortedLogs)
    setFilteredLogs(filtered)
  }, [rawLogs, search, lines, since, typeFilter])

  useEffect(() => {
    scrollToBottom()

    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [filteredLogs, autoScroll])

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
    <div className={cn('flex w-full flex-col gap-4 py-4', dir === 'rtl' && 'rtl')}>
      <div className="flex flex-col gap-4">
        <div className="w-full sm:w-auto">
          <Label htmlFor="node-select" className="mb-1 block text-sm">
            {t('nodes.title')}
          </Label>
          <Select value={selectedNode.toString()} onValueChange={value => handleNodeChange(Number(value))} disabled={connectedNodes.length === 0}>
            <SelectTrigger id="node-select" className="h-9 w-full text-sm sm:w-[250px]" disabled={connectedNodes.length === 0}>
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

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-wrap items-center gap-2 sm:gap-4">
              <LineCountFilter value={lines} onValueChange={handleLines} />

              <SinceLogsFilter value={since} onValueChange={handleSince} showTimestamp={showTimestamp} onTimestampChange={setShowTimestamp} />

              <StatusLogsFilter value={typeFilter} setValue={setTypeFilter} title={t('nodes.logs.filter')} options={priorities} />

              <Input
                type="search"
                placeholder={t('nodes.logs.search')}
                value={search}
                onChange={handleSearch}
                className="inline-flex h-9 w-full min-w-[200px] text-sm placeholder-gray-400 sm:w-auto sm:min-w-0"
              />
            </div>

            <div className={cn('flex w-full gap-2 sm:w-auto', dir === 'rtl' && 'flex-row-reverse')}>
              <Button variant="outline" size="sm" className="h-9 flex-1 sm:flex-initial" onClick={handlePauseResume} title={isPaused ? t('nodes.logs.resume') : t('nodes.logs.pause')}>
                {isPaused ? <Play className={cn('h-4 w-4 sm:mr-2', dir === 'rtl' && 'sm:ml-2 sm:mr-0')} /> : <Pause className={cn('h-4 w-4 sm:mr-2', dir === 'rtl' && 'sm:ml-2 sm:mr-0')} />}
                <span className="hidden sm:inline">{isPaused ? t('nodes.logs.resume') : t('nodes.logs.pause')}</span>
              </Button>
              <Button variant="outline" size="sm" className="h-9 flex-1 sm:flex-initial" onClick={handleDownload} disabled={filteredLogs.length === 0}>
                <DownloadIcon className={cn('h-4 w-4 sm:mr-2', dir === 'rtl' && 'sm:ml-2 sm:mr-0')} />
                <span className="hidden sm:inline">{t('nodes.logs.download')}</span>
              </Button>
            </div>
          </div>
          {isPaused && (
            <Alert className="border-amber-500/50 bg-amber-500/15 text-amber-700 dark:text-amber-400">
              <Pause className="h-4 w-4" />
              <AlertDescription>
                {t('nodes.logs.paused')}
                {messageBuffer.length > 0 && (
                  <span className="ml-1 font-medium">
                    ({messageBuffer.length} {t('nodes.logs.messagesBuffered')})
                  </span>
                )}
              </AlertDescription>
            </Alert>
          )}
          <Card className="bg-background">
            <CardContent className="p-1 sm:p-2">
              <div
                ref={scrollRef}
                onScroll={handleScroll}
                dir="ltr"
                className="custom-logs-scrollbar h-[calc(100vh-280px)] max-h-[720px] min-h-[400px] space-y-0 overflow-y-auto overflow-x-hidden rounded bg-background/75 sm:h-[720px] sm:min-h-0"
              >
                {filteredLogs.length > 0 ? (
                  filteredLogs.map((filteredLog: LogLine, index: number) => <TerminalLine key={index} log={filteredLog} searchTerm={search} noTimestamp={!showTimestamp} />)
                ) : isLoading ? (
                  <div className="flex h-full items-center justify-center text-muted-foreground">
                    <Loader2 className="h-6 w-6" />
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center text-muted-foreground">{t('nodes.logs.noLogs')}</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
