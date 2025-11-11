import { useState, useEffect, useRef, useCallback } from 'react'
import { useWebSocket } from 'react-use-websocket/dist/lib/use-websocket'
import debounce from 'lodash.debounce'
import { getAuthToken } from '@/utils/authStorage'

export const MAX_NUMBER_OF_LOGS = 500

const joinPaths = (paths: string[]) => {
  return paths
    .map(path => path.replace(/(^\/+|\/+$)/g, '')) // Remove leading and trailing slashes
    .join('/')
}

const getWebsocketUrl = (nodeID: string) => {
  try {
    let baseURL = new URL(import.meta.env.VITE_BASE_API.startsWith('/') ? window.location.origin + import.meta.env.VITE_BASE_API : import.meta.env.VITE_BASE_API)

    return (baseURL.protocol === 'https:' ? 'wss://' : 'ws://') + joinPaths([baseURL.host + baseURL.pathname, !nodeID ? 'core/logs' : `/node/${nodeID}/logs`]) + '?interval=1&token=' + getAuthToken()
  } catch (e) {
    console.error('Unable to generate websocket url')
    console.error(e)
    return null
  }
}

const Logs = ({ className }: { className?: string }) => {
  const [logs, setLogs] = useState<string[]>([])
  const [selectedNode] = useState<string>('')
  const logsDiv = useRef<HTMLDivElement | null>(null)

  const updateLogs = useCallback(
    debounce(() => {
      if (logsDiv.current) {
        logsDiv.current.scrollTo({
          top: logsDiv.current.scrollHeight,
          behavior: 'smooth',
        })
      }
    }, 300),
    [],
  )

  useWebSocket(getWebsocketUrl(selectedNode), {
    onMessage: (e: any) => {
      const newLogs = e.data.split('\n').filter((line: string) => line.trim() !== '') // Remove empty lines
      setLogs(prevLogs => {
        const updatedLogs = [...prevLogs, ...newLogs]
        if (updatedLogs.length > MAX_NUMBER_OF_LOGS) updatedLogs.splice(0, updatedLogs.length - MAX_NUMBER_OF_LOGS)
        updateLogs()

        return updatedLogs
      })
    },
    shouldReconnect: () => true,
    reconnectAttempts: 10,
    reconnectInterval: 1000,
  })

  useEffect(() => {
    return () => {
      setLogs([])
    }
  }, [])

  return (
    <div ref={logsDiv} className="h-[400px] space-y-2 overflow-auto rounded-lg border p-4 font-mono text-sm">
      <div className={`w-full rounded-lg p-4 font-mono text-sm ${className}`}>
        <div className="space-y-1">
          {logs.map((log, index) => (
            <div key={index} className="flex items-start space-x-4">
              <div key={index} className="flex items-start space-x-4">
                <span>
                  {log.split(/(Warning|Info|Debug|Error|Critical)/gi).map((part, idx) => {
                    if (part === 'Warning') {
                      return (
                        <span key={idx} className="font-bold text-yellow-600">
                          {part}
                        </span>
                      )
                    } else if (part === 'Info') {
                      return (
                        <span key={idx} className="font-bold text-green-600">
                          {part}
                        </span>
                      )
                    } else if (part === 'Debug') {
                      return (
                        <span key={idx} className="font-bold text-blue-600">
                          {part}
                        </span>
                      )
                    } else if (part === 'Error') {
                      return (
                        <span key={idx} className="font-bold text-red-600">
                          {part}
                        </span>
                      )
                    } else if (part === 'Critical') {
                      return (
                        <span key={idx} className="font-bold text-red-800">
                          {part}
                        </span>
                      )
                    } else {
                      return part
                    }
                  })}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Logs
