import { memo, useMemo } from 'react'
import { FancyAnsi } from 'fancy-ansi'
import { escapeRegExp } from 'es-toolkit'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { getLogStyle, type LogLine } from '@/utils/logsUtils'
import { useTranslation } from 'react-i18next'

interface LogLineProps {
  log: LogLine
  noTimestamp?: boolean
  searchTerm?: string
}

const fancyAnsi = new FancyAnsi()

function pad2(n: number) {
  return n < 10 ? `0${n}` : String(n)
}

function formatLogTimes(timestamp: Date | null, rawTimestamp: string | null): { display: string; tooltip: string } {
  if (timestamp && !Number.isNaN(timestamp.getTime())) {
    const display = `${pad2(timestamp.getHours())}:${pad2(timestamp.getMinutes())}:${pad2(timestamp.getSeconds())}`
    const tooltip = `${timestamp.getFullYear()}-${pad2(timestamp.getMonth() + 1)}-${pad2(timestamp.getDate())} ${display}`
    return { display, tooltip }
  }
  const raw = rawTimestamp || ''
  return { display: raw, tooltip: raw }
}

export const TerminalLine = memo(function TerminalLine({ log, noTimestamp, searchTerm }: LogLineProps) {
  const { timestamp, message, rawTimestamp } = log
  const { type, variant, color } = getLogStyle(log.type)
  const { t, i18n } = useTranslation()
  const locale = i18n.language
  const { display: displayTime, tooltip: tooltipTimestamp } = formatLogTimes(timestamp, rawTimestamp)

  const highlightedHtml = useMemo(() => {
    const htmlContent = fancyAnsi.toHtml(message)
    if (!searchTerm) return htmlContent
    const searchRegex = new RegExp(`(${escapeRegExp(searchTerm)})`, 'gi')
    return htmlContent.replace(searchRegex, match => `<span class="bg-orange-200/80 dark:bg-orange-900/80 font-bold">${match}</span>`)
  }, [message, searchTerm])

  return (
    <div
      className={cn(
        'group flex min-w-0 flex-col gap-1.5 px-2 py-2 font-mono text-xs sm:flex-row sm:items-start sm:gap-3 sm:px-3 sm:py-0.5',
        type === 'error'
          ? 'bg-red-500/10 hover:bg-red-500/15'
          : type === 'warning'
            ? 'bg-yellow-500/10 hover:bg-yellow-500/15'
            : type === 'debug'
              ? 'bg-orange-500/10 hover:bg-orange-500/15'
              : 'hover:bg-gray-200/50 dark:hover:bg-gray-800/50',
      )}
    >
      <div className={cn('flex shrink-0 items-center gap-2', noTimestamp && 'gap-1')}>
        <div className={cn('h-full w-2 shrink-0 rounded-[3px]', color)} title={tooltipTimestamp || undefined} />
        {!noTimestamp && <span className="text-muted-foreground w-18 shrink-0 text-[11px] tabular-nums select-text sm:w-24 sm:text-xs">{displayTime}</span>}

        <Badge variant={variant} className={cn('min-w-12 shrink-0 justify-center px-1.5 py-0 text-[11px] sm:min-w-14 sm:text-[10px]', locale === 'fa' && 'font-body')}>
          {t(`nodes.logs.${type}`)}
        </Badge>
      </div>
      <span className="text-foreground min-w-0 flex-1 font-mono text-xs leading-relaxed wrap-anywhere whitespace-pre-wrap dark:text-gray-200" dangerouslySetInnerHTML={{ __html: highlightedHtml }} />
    </div>
  )
})
