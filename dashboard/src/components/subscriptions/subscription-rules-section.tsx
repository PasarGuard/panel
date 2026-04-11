import { SortableSubscriptionRule } from '@/components/subscriptions/sortable-subscription-rule'
import type { SubscriptionFormData } from '@/components/subscriptions/subscription-settings-schema'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { closestCenter, DndContext, DragEndEvent } from '@dnd-kit/core'
import { rectSortingStrategy, SortableContext } from '@dnd-kit/sortable'
import { FileText, Plus, RotateCcw } from 'lucide-react'
import type { ComponentProps } from 'react'
import type { FieldArrayWithId } from 'react-hook-form'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

type DndContextSensors = NonNullable<ComponentProps<typeof DndContext>['sensors']>

export interface SubscriptionRulesSectionProps {
  form: UseFormReturn<SubscriptionFormData>
  ruleFields: FieldArrayWithId<SubscriptionFormData, 'rules'>[]
  sensors: DndContextSensors
  onDragEnd: (event: DragEndEvent) => void
  onResetToDefault: () => void
  onAddRule: () => void
  onRemoveRule: (index: number) => void
  isSaving: boolean
}

export function SubscriptionRulesSection({
  form,
  ruleFields,
  sensors,
  onDragEnd,
  onResetToDefault,
  onAddRule,
  onRemoveRule,
  isSaving,
}: SubscriptionRulesSectionProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="rounded-lg border bg-card p-3 shadow-sm sm:p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1 space-y-1">
            <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold sm:text-lg">
              {t('settings.subscriptions.rules.title')}
              {ruleFields.length > 0 && (
                <Badge variant="secondary" className="ml-2 shrink-0">
                  {ruleFields.length}
                </Badge>
              )}
            </h3>
            <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.rules.description')}</p>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onResetToDefault} className="flex w-full items-center justify-center gap-2 sm:w-auto" disabled={isSaving}>
              <RotateCcw className="h-4 w-4" />
              <span className="hidden sm:inline">{t('settings.subscriptions.resetToDefault', { defaultValue: 'Reset to Default' })}</span>
              <span className="sm:hidden">{t('settings.subscriptions.resetToDefault', { defaultValue: 'Reset' })}</span>
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onAddRule} className="flex w-full shrink-0 items-center justify-center gap-2 sm:w-auto">
              <Plus className="h-4 w-4" />
              {t('settings.subscriptions.rules.addRule')}
            </Button>
          </div>
        </div>
      </div>

      {ruleFields.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">
          <FileText className="mx-auto mb-3 h-8 w-8 opacity-30" />
          <p className="mb-1 text-xs font-medium sm:text-sm">{t('settings.subscriptions.rules.noRules')}</p>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <div dir="ltr">
            <SortableContext items={ruleFields.map(field => field.id)} strategy={rectSortingStrategy}>
              <div className="scrollbar-thin flex max-h-[min(70vh,500px)] touch-pan-y flex-col gap-2 overflow-y-auto py-1 sm:max-h-[500px] sm:gap-2.5 sm:py-1">
                {ruleFields.map((field, index) => (
                  <SortableSubscriptionRule key={field.id} id={field.id} index={index} onRemove={onRemoveRule} form={form} />
                ))}
              </div>
            </SortableContext>
          </div>
        </DndContext>
      )}
    </div>
  )
}
