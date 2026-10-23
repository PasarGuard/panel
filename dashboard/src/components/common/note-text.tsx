import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { SyntheticEvent } from 'react'

interface NoteTextProps {
  note?: string | null
  className?: string
}

// Clicks inside the popover bubble through the React tree (even from the portal), so keep them off the card or row
const stop = (e: SyntheticEvent) => e.stopPropagation()

export const noteTriggerClassName = (className?: string) => cn('text-muted-foreground block w-full cursor-pointer text-start text-xs', className)

// The clamp sits on an inner span: WebKit ignores -webkit-line-clamp on <button>. line-clamp-2 needs display:-webkit-box,
// so no display utility (block, flex, ...) may sit next to it: Tailwind emits .block later and it would win
export const noteClampClassName = 'line-clamp-2 break-words'

// Admin note clamped to two lines; a tap or click opens the full text, so it is readable on touch screens and without edit rights
export function NoteText({ note, className }: NoteTextProps) {
  if (!note) return null

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" dir="auto" title={note} onClick={stop} onKeyDown={stop} className={noteTriggerClassName(className)}>
          <span className={noteClampClassName}>{note}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" dir="auto" className="text-sm break-words whitespace-pre-wrap" onClick={stop} onKeyDown={stop}>
        {note}
      </PopoverContent>
    </Popover>
  )
}
