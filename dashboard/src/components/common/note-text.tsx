import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { SyntheticEvent } from 'react'

interface NoteTextProps {
  note?: string | null
  className?: string
}

// Clicks inside the popover bubble through the React tree (even from the portal), so keep them off the card or row
const stop = (e: SyntheticEvent) => e.stopPropagation()

// Admin note clamped to two lines; a tap or click opens the full text, so it is readable on touch screens and without edit rights
export function NoteText({ note, className }: NoteTextProps) {
  if (!note) return null

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          dir="auto"
          title={note}
          onClick={stop}
          onKeyDown={stop}
          className={cn('text-muted-foreground line-clamp-2 block w-full cursor-pointer text-start text-xs break-words', className)}
        >
          {note}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" dir="auto" className="text-sm break-words whitespace-pre-wrap" onClick={stop} onKeyDown={stop}>
        {note}
      </PopoverContent>
    </Popover>
  )
}
