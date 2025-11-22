import { Button } from '@/components/ui/button'
import { Plus, Minus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface OperationSelectorProps {
  operation: 'add' | 'remove' | 'add' | 'subtract'
  onOperationChange: (operation: 'add' | 'remove' | 'add' | 'subtract') => void
  addLabel?: string
  removeLabel?: string
  description?: string
  title?: string
}

export function OperationSelector({ operation, onOperationChange, addLabel, removeLabel, description, title }: OperationSelectorProps) {
  const { t } = useTranslation()
  const isAddRemove = operation === 'add' || operation === 'remove'

  return (
    <div className="space-y-3">
      <div className="text-center">
        <h3 className="text-sm font-medium text-muted-foreground">{title || t('bulk.operationType', { defaultValue: 'Operation Type' })}</h3>
        {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
      </div>
      <div className="flex flex-wrap justify-center gap-2 sm:gap-3">
        <Button
          variant={operation === 'add' ? 'default' : 'outline'}
          size="sm"
          onClick={() => onOperationChange('add')}
          className={cn(
            'flex items-center justify-center gap-2 transition-all',
            operation === 'add' && 'shadow-sm',
          )}
        >
          <Plus className="h-4 w-4 shrink-0" />
          <span className="whitespace-nowrap">{addLabel || (isAddRemove ? t('bulk.addGroups') : t('bulk.addDataLimit', { defaultValue: 'Add Data Limit' }))}</span>
        </Button>
        <Button
          variant={operation === 'remove' || operation === 'subtract' ? (isAddRemove ? 'destructive' : 'default') : 'outline'}
          size="sm"
          onClick={() => onOperationChange(isAddRemove ? 'remove' : 'subtract')}
          className={cn(
            'flex items-center justify-center gap-2 transition-all',
            (operation === 'remove' || operation === 'subtract') && 'shadow-sm',
          )}
        >
          <Minus className="h-4 w-4 shrink-0" />
          <span className="whitespace-nowrap">
            {removeLabel || (isAddRemove ? t('bulk.removeGroups') : t('bulk.subtractDataLimit', { defaultValue: 'Subtract Data Limit' }))}
          </span>
        </Button>
      </div>
    </div>
  )
}

