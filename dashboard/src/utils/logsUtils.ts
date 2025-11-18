export type LogType = 'error' | 'warning' | 'info' | 'debug'
export type LogVariant = 'red' | 'yellow' | 'blue' | 'orange'

export interface LogLine {
  rawTimestamp: string | null
  timestamp: Date | null
  message: string
}

interface LogStyle {
  type: LogType
  variant: LogVariant
  color: string
}

const LOG_STYLES: Record<LogType, LogStyle> = {
  error: {
    type: 'error',
    variant: 'red',
    color: 'bg-red-500/40',
  },
  warning: {
    type: 'warning',
    variant: 'orange',
    color: 'bg-orange-500/40',
  },
  info: {
    type: 'info',
    variant: 'blue',
    color: 'bg-blue-600/40',
  },
  debug: {
    type: 'debug',
    variant: 'yellow',
    color: 'bg-yellow-500/40',
  },
} as const

export function parseLogs(logString: string): LogLine[] {
  // Regex to match the log line format
  // Example of return :
  // 1 2024-12-10T10:00:00.000Z The server is running on port 8080
  // Should return :
  // { timestamp: new Date("2024-12-10T10:00:00.000Z"),
  // message: "The server is running on port 8080" }
  const logRegex = /^(?:(\d+)\s+)?(\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z|\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} UTC)?\s*(.*)$/

  return logString
    .split('\n')
    .map(line => line.trim())
    .filter(line => line !== '')
    .map(line => {
      const match = line.match(logRegex)
      if (!match) return null

      const [, , timestamp, message] = match

      if (!message?.trim()) return null

      let parsedTimestamp: Date | null = null
      if (timestamp) {
        try {
          // Handle Xray format: 2025/09/27 13:26:58.279079 (assume UTC)
          if (timestamp.includes('/')) {
            parsedTimestamp = new Date(timestamp + 'Z') // Treat as UTC
          } else {
            // Handle other formats
            parsedTimestamp = new Date(timestamp.replace(' UTC', 'Z'))
          }
          // Validate the parsed date is valid
          if (isNaN(parsedTimestamp.getTime())) {
            parsedTimestamp = null
          }
        } catch {
          // If date parsing fails, set to null
          parsedTimestamp = null
        }
      }

      // Remove duplicate status indicators from message text since they're shown in badges
      let cleanedMessage = message.trim()
      cleanedMessage = cleanedMessage.replace(/^\[(Debug|Info|Warning|Error)\]\s*/i, '')

      return {
        rawTimestamp: timestamp ?? null,
        timestamp: parsedTimestamp,
        message: cleanedMessage,
      }
    })
    .filter(log => log !== null) as LogLine[]
}

// Detect log type based on Xray core message content
export const getLogType = (message: string): LogStyle => {
  if (/\[error\]/i.test(message)) {
    return LOG_STYLES.error
  }

  if (/\[warning\]/i.test(message) || /\[warn\]/i.test(message)) {
    return LOG_STYLES.warning
  }

  if (/\[info\]/i.test(message)) {
    return LOG_STYLES.info
  }

  if (/\[debug\]/i.test(message)) {
    return LOG_STYLES.debug
  }

  // Xray access logs: "from IP:port accepted tcp/udp:destination:port [info] email: user@example.com"
  if (/from\s+.+:\d+\s+accepted\s+(tcp|udp):.+:\d+\s+\[.+\]\s+email:\s+.+/i.test(message)) {
    return LOG_STYLES.info
  }

  // Default to info
  return LOG_STYLES.info
}
