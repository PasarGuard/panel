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
    <div className="space-y-2">
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
                'flex size-10 shrink-0 items-center justify-center rounded-full border p-0 transition-colors sm:h-9 sm:w-auto sm:gap-2 sm:px-2 sm:pr-3',
                selected ? 'border-foreground bg-background shadow-sm' : 'border-border/70 bg-background hover:border-foreground/40',
              )}
            >
              <span className={cn('size-6 rounded-full border shadow-sm sm:size-5', selected ? 'border-foreground/40' : 'border-border')} style={{ background: getColor(option) }} />
              <span className="hidden text-xs font-medium whitespace-nowrap sm:inline">{getLabel(option)}</span>
            </button>
          )
        })}
      </div>
      <p className="text-muted-foreground text-xs sm:hidden">{getLabel(value)}</p>
    </div>
  )
}
