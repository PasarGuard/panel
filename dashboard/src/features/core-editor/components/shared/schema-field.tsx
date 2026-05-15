import type { XrayGeneratedFormField } from '@pasarguard/xray-config-kit'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface SchemaFieldProps {
  field: XrayGeneratedFormField
  value: string
  onChange: (next: string) => void
  disabled?: boolean
  className?: string
}

/** Minimal parity-field renderer: maps JSON path hints to a single-line input until richer typing exists. */
export function SchemaField({ field, value, onChange, disabled, className }: SchemaFieldProps) {
  return (
    <div className={cn('min-w-0 w-full space-y-1.5', className)}>
      <div className="flex items-center gap-2">
        <Label className="text-xs font-medium">{field.go || field.json}</Label>
        <span className="text-[10px] text-muted-foreground">{field.type}</span>
      </div>
      <Input
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        className="h-10 w-full min-w-0 text-xs"
        dir="ltr"
      />
    </div>
  )
}
