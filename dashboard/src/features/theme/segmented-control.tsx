import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

type SegmentedOption<T extends string> = {
  value: T
  label: string
  icon?: ReactNode
  description?: string
}

type SegmentedControlProps<T extends string> = {
  value: T
  options: SegmentedOption<T>[]
  onChange: (value: T) => void
  columns?: number
}

export function SegmentedControl<T extends string>({ value, options, onChange, columns }: SegmentedControlProps<T>) {
  const columnClass = columns === 2 ? 'grid-cols-2' : columns === 4 ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-3'

  return (
    <div className={cn('bg-muted/40 grid gap-1 rounded-lg p-1', columnClass)}>
      {options.map(option => {
        const selected = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              'flex min-h-10 min-w-0 flex-col items-center justify-center gap-1 rounded-md px-1.5 py-2 text-xs font-medium transition-colors sm:min-h-9 sm:flex-row sm:gap-2 sm:px-3 sm:text-sm',
              selected ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-background/60',
            )}
          >
            {option.icon}
            <span className="max-w-full truncate">{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}
