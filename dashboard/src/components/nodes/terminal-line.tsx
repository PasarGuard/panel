import { FancyAnsi } from 'fancy-ansi'
import { escapeRegExp } from 'lodash'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipPortal, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import dayjs from '@/lib/dayjs'
import type { Dayjs } from 'dayjs'
import { getLogType, type LogLine } from '@/utils/logsUtils'
import { useTranslation } from 'react-i18next'

interface LogLineProps {
  log: LogLine
  noTimestamp?: boolean
  searchTerm?: string
}

const fancyAnsi = new FancyAnsi()

export function TerminalLine({ log, noTimestamp, searchTerm }: LogLineProps) {
  const { timestamp, message, rawTimestamp } = log
  const { type, variant, color } = getLogType(message)
  const { t, i18n } = useTranslation()
  const locale = i18n.language

  const parseLogDayjs = (value: Date | string | null): Dayjs | null => {
    if (!value) return null
    if (value instanceof Date) {
      return isNaN(value.getTime()) ? null : dayjs(value)
    }

    const cleaned = value.includes(' UTC') ? value.replace(' UTC', 'Z') : value
    const formats = ['YYYY/MM/DD HH:mm:ss.SSSSSS', 'YYYY/MM/DD HH:mm:ss.SSS', 'YYYY/MM/DD HH:mm:ss', 'YYYY-MM-DD HH:mm:ss.SSS', 'YYYY-MM-DD HH:mm:ss']

    for (const format of formats) {
      const parsed = dayjs.utc(cleaned, format, true)
      if (parsed.isValid()) return parsed.local()
    }

    const fallback = dayjs.utc(cleaned)
    return fallback.isValid() ? fallback.local() : null
  }

  const parsedDate = parseLogDayjs(timestamp) ?? parseLogDayjs(rawTimestamp)

  const displayTime = parsedDate ? parsedDate.format('HH:mm:ss') : rawTimestamp || ''
  const tooltipTimestamp = parsedDate ? parsedDate.format('YYYY-MM-DD HH:mm:ss') : rawTimestamp || ''

  const highlightMessage = (text: string, term: string) => {
    if (!term) {
      return (
        <span
          className="transition-colors"
          dangerouslySetInnerHTML={{
            __html: fancyAnsi.toHtml(text),
          }}
        />
      )
    }

    const htmlContent = fancyAnsi.toHtml(text)
    const searchRegex = new RegExp(`(${escapeRegExp(term)})`, 'gi')

    const modifiedContent = htmlContent.replace(searchRegex, match => `<span class="bg-orange-200/80 dark:bg-orange-900/80 font-bold">${match}</span>`)

    return <span className="transition-colors" dangerouslySetInnerHTML={{ __html: modifiedContent }} />
  }

  const tooltip = (color: string, timestamp: string | null) => {
    const square = <div className={cn('h-full w-2 flex-shrink-0 rounded-[3px]', color)} />
    return timestamp ? (
      <TooltipProvider delayDuration={0} disableHoverableContent>
        <Tooltip>
          <TooltipTrigger asChild>{square}</TooltipTrigger>
          <TooltipPortal>
            <TooltipContent sideOffset={5} className="z-[99999] border-border bg-popover">
              <p className="text max-w-md break-all text-xs text-muted-foreground">
                <pre>{timestamp}</pre>
              </p>
            </TooltipContent>
          </TooltipPortal>
        </Tooltip>
      </TooltipProvider>
    ) : (
      square
    )
  }

  return (
    <div
      className={cn(
        'group flex flex-col gap-1.5 px-2 py-2 font-mono text-xs sm:flex-row sm:gap-3 sm:px-3 sm:py-0.5 sm:text-xs',
        type === 'error'
          ? 'bg-red-500/10 hover:bg-red-500/15'
          : type === 'warning'
            ? 'bg-yellow-500/10 hover:bg-yellow-500/15'
            : type === 'debug'
              ? 'bg-orange-500/10 hover:bg-orange-500/15'
              : 'hover:bg-gray-200/50 dark:hover:bg-gray-800/50',
      )}
    >
      <div className={cn('flex flex-shrink-0 items-start gap-2', noTimestamp && 'gap-1')}>
        {/* Icon to expand the log item maybe implement a colapsible later */}
        {/* <Square className="size-4 text-muted-foreground opacity-0 group-hover/logitem:opacity-100 transition-opacity" /> */}
        {tooltip(color, tooltipTimestamp || null)}
        {!noTimestamp && (
          <span className="w-20 flex-shrink-0 select-text text-[11px] text-muted-foreground sm:w-24 sm:text-xs">{displayTime}</span>
        )}

        <Badge variant={variant} className={cn('w-12 flex-shrink-0 justify-center px-1 py-0 text-[11px] sm:w-14 sm:text-[10px]', locale === 'fa' && 'font-body')}>
          {t(`nodes.logs.${type}`)}
        </Badge>
      </div>
      <span className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground dark:text-gray-200 sm:text-xs">{highlightMessage(message, searchTerm || '')}</span>
    </div>
  )
}
