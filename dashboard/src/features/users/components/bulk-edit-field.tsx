import { useId, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { Check, type LucideIcon } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import type { BulkEditOperation } from '../forms/bulk-edit-form'

interface Props {
  label: string
  icon?: LucideIcon
  operation: BulkEditOperation
  operations?: BulkEditOperation[]
  clearLabel?: string
  description?: string
  onChange: (operation: BulkEditOperation) => void
  children?: ReactNode
}

export function BulkEditField({ label, icon: Icon, operation, operations = ['set'], clearLabel, description, onChange, children }: Props) {
  const { t } = useTranslation()
  const id = useId()
  const dir = useDirDetection()
  return (
    <div className={cn('space-y-3 border-s-[3px] border-b border-s-transparent px-4 py-4 last:border-b-0', operation !== 'keep' && 'border-s-primary bg-primary/[0.04]')}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Label id={id} className="flex items-center gap-2.5 text-sm font-medium">
          {Icon && <Icon aria-hidden className={cn('h-4 w-4 shrink-0', operation === 'keep' ? 'text-muted-foreground' : 'text-primary')} />}
          <span>{label}</span>
          {operation !== 'keep' && <Check aria-hidden className="text-primary h-3.5 w-3.5 shrink-0" />}
        </Label>
        <Select dir={dir} value={operation} onValueChange={value => onChange(value as BulkEditOperation)}>
          <SelectTrigger aria-labelledby={id} className={cn('bg-background h-9 w-36 sm:w-44', operation !== 'keep' && 'border-primary/30 text-primary')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(['keep', ...operations] as BulkEditOperation[]).map(op => (
              <SelectItem key={op} value={op}>
                {op === 'clear' && clearLabel ? clearLabel : t(`bulkEdit.operations.${op}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {operation !== 'keep' && operation !== 'clear' && <div className="sm:ps-7">{children}</div>}
      {operation !== 'keep' && description && <p className="text-muted-foreground text-xs leading-relaxed sm:ps-7">{description}</p>}
    </div>
  )
}
