import { FancyAnsi } from 'fancy-ansi'
import { escapeRegExp } from 'lodash'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipPortal, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
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

  const formattedTime = timestamp
    ? timestamp.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
    : ''

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
        'group flex flex-row gap-2 py-1 font-mono text-[10px] sm:gap-3 sm:py-0.5 sm:text-xs',
        type === 'error'
          ? 'bg-red-500/10 hover:bg-red-500/15'
          : type === 'warning'
            ? 'bg-yellow-500/10 hover:bg-yellow-500/15'
            : type === 'debug'
              ? 'bg-orange-500/10 hover:bg-orange-500/15'
              : 'hover:bg-gray-200/50 dark:hover:bg-gray-800/50',
      )}
    >
      <div className="flex items-start gap-x-2">
        {/* Icon to expand the log item maybe implement a colapsible later */}
        {/* <Square className="size-4 text-muted-foreground opacity-0 group-hover/logitem:opacity-100 transition-opacity" /> */}
        {tooltip(color, rawTimestamp)}
        {!noTimestamp && <span className="w-16 flex-shrink-0 select-none pl-1 text-[9px] text-muted-foreground sm:w-20 sm:pl-2 sm:text-xs">{formattedTime}</span>}

        <Badge variant={variant} className={cn('w-14 justify-center px-1 py-0 text-[10px]', locale === 'fa' && 'font-body')}>
          {t(`nodes.logs.${type}`)}
        </Badge>
      </div>
      <span className="whitespace-pre-wrap break-all font-mono text-foreground dark:text-gray-200">{highlightMessage(message, searchTerm || '')}</span>
    </div>
  )
}
