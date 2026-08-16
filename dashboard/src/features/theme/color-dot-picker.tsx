import { cn } from '@/lib/utils'

type ColorDotPickerProps<T extends string> = {
  value: T
  options: T[]
  onChange: (value: T) => void
  getColor: (value: T) => string
  getLabel: (value: T) => string
}

export function ColorDotPicker<T extends string>({ value, options, onChange, getColor, getLabel }: ColorDotPickerProps<T>) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(option => {
        const selected = value === option
        return (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            title={getLabel(option)}
            aria-label={getLabel(option)}
            className={cn(
              'flex h-9 items-center gap-2 rounded-full border px-2 pr-3 text-xs font-medium transition-colors',
              selected ? 'border-foreground bg-background shadow-sm' : 'border-border/70 bg-background hover:border-foreground/40',
            )}
          >
            <span className={cn('h-5 w-5 rounded-full border shadow-sm', selected ? 'border-foreground/40' : 'border-border')} style={{ background: getColor(option) }} />
            {getLabel(option)}
          </button>
        )
      })}
    </div>
  )
}
