import { cn } from '@/lib/utils'
import * as React from 'react'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: string
  isError?: boolean
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, error, isError, ...props }, ref) => {
  return (
    <div className="min-w-0 flex-1">
      <input
        type={type}
        dir="ltr"
        className={cn(
          'border-border bg-input ring-offset-background file:text-foreground placeholder:text-input-placeholder focus-visible:ring-ring flex h-9 w-full rounded-md border px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
          className,
          {
            'border-destructive': !!error || isError,
          },
        )}
        ref={ref}
        {...props}
      />
      {error && <span className="text-destructive mt-2 block text-sm">{error}</span>}
    </div>
  )
})
Input.displayName = 'Input'

export { Input }
