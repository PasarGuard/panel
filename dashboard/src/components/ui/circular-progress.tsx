import { cn } from '@/lib/utils'
import * as React from 'react'

type CircularProgressProps = React.HTMLAttributes<HTMLDivElement> & {
  value: number
  size?: number
  strokeWidth?: number
  showValue?: boolean
  valueFormatter?: (value: number) => string
  trackClassName?: string
  indicatorClassName?: string
}

const clamp = (value: number) => Math.min(100, Math.max(0, value))

const CircularProgress = React.forwardRef<HTMLDivElement, CircularProgressProps>(
  (
    {
      className,
      value,
      size = 120,
      strokeWidth = 8,
      showValue = true,
      valueFormatter,
      trackClassName,
      indicatorClassName,
      ...props
    },
    ref,
  ) => {
    const normalizedValue = clamp(value)
    const radius = (size - strokeWidth) / 2
    const circumference = 2 * Math.PI * radius
    const visibleArc = circumference * 0.75
    const hiddenArc = circumference - visibleArc
    const progressArc = visibleArc * (normalizedValue / 100)
    const valueText = valueFormatter ? valueFormatter(normalizedValue) : `${normalizedValue.toFixed(2)}%`

    return (
      <div
        ref={ref}
        className={cn('relative inline-flex items-center justify-center', className)}
        style={{ width: size, height: size }}
        {...props}
      >
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="-rotate-[135deg]"
          role="img"
          aria-label={`Progress ${valueText}`}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
            strokeDasharray={`${visibleArc} ${hiddenArc}`}
            className={cn('stroke-muted/40', trackClassName)}
            strokeLinecap="round"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
            strokeDasharray={`${progressArc} ${circumference}`}
            className={cn('stroke-primary transition-all duration-500 ease-out', indicatorClassName)}
            strokeLinecap="round"
          />
        </svg>
        {showValue && <span className="pointer-events-none absolute text-sm font-medium text-foreground/90">{valueText}</span>}
      </div>
    )
  },
)

CircularProgress.displayName = 'CircularProgress'

export { CircularProgress }
