import { configFormatOptions } from '@/components/subscriptions/config-format-options'
import { SubscriptionRuleAdvancedSheet } from '@/components/subscriptions/subscription-rule-advanced-sheet'
import type { SubscriptionFormData } from '@/components/subscriptions/subscription-settings-schema'
import { Button } from '@/components/ui/button'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Bolt, GripVertical, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SortableSubscriptionRuleProps {
  index: number
  onRemove: (index: number) => void
  form: UseFormReturn<SubscriptionFormData>
  id: string
}

function RuleActionButtons({
  index,
  onRemove,
  advancedSheetItemCount,
  responseHeaderCount,
  onAdvancedOpen,
  advancedLabel,
  className,
}: {
  index: number
  onRemove: (index: number) => void
  advancedSheetItemCount: number
  responseHeaderCount: number
  onAdvancedOpen: () => void
  advancedLabel: string
  className?: string
}) {
  const { t } = useTranslation()

  return (
    <div className={className}>
      <div className="relative shrink-0">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 sm:h-8 sm:w-8"
          onClick={() => onAdvancedOpen()}
          aria-label={advancedLabel}
          title={
            advancedSheetItemCount > 0 && responseHeaderCount > 0
              ? t('settings.subscriptions.rules.advancedHeadersHint', { count: responseHeaderCount })
              : undefined
          }
        >
          <Bolt className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
        </Button>
        {advancedSheetItemCount > 0 && (
          <span
            className="pointer-events-none absolute -end-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-primary px-0.5 text-[9px] font-medium leading-none text-primary-foreground tabular-nums sm:h-4 sm:min-w-4 sm:text-[10px]"
            aria-hidden
          >
            {advancedSheetItemCount > 99 ? '99+' : advancedSheetItemCount}
          </span>
        )}
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={e => {
          e.preventDefault()
          e.stopPropagation()
          onRemove(index)
        }}
        className="h-7 w-7 shrink-0 p-0 text-destructive opacity-80 hover:bg-destructive/10 hover:text-destructive hover:opacity-100 sm:h-8 sm:w-8"
      >
        <Trash2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
      </Button>
    </div>
  )
}

export function SortableSubscriptionRule({ index, onRemove, form, id }: SortableSubscriptionRuleProps) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false)
  const responseHeaders = (form.watch(`rules.${index}.response_headers`) || {}) as Record<string, string>
  const responseHeaderCount = Object.keys(responseHeaders).length
  const advancedSheetItemCount = responseHeaderCount

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : 1,
    opacity: isDragging ? 0.8 : 1,
    direction: 'ltr' as const,
  }
  const cursor = isDragging ? 'grabbing' : 'grab'

  const advancedLabel =
    advancedSheetItemCount > 0
      ? `${t('settings.subscriptions.rules.advanced')} (${advancedSheetItemCount})`
      : t('settings.subscriptions.rules.advanced')

  const actionProps = {
    index,
    onRemove,
    advancedSheetItemCount,
    responseHeaderCount,
    onAdvancedOpen: () => setIsAdvancedOpen(true),
    advancedLabel,
  }

  return (
    <>
      <div ref={setNodeRef} style={style} className="cursor-default" dir="ltr">
        <div className="group relative flex flex-col gap-2 rounded-md border bg-card p-2 transition-colors hover:bg-accent/20 sm:flex-row sm:items-center sm:gap-3 sm:p-3">
          <div className="flex min-w-0 flex-1 flex-row gap-1 sm:gap-1.5">
            <button
              type="button"
              style={{ cursor: cursor }}
              className="touch-none flex min-h-[44px] min-w-[40px] shrink-0 items-center justify-center self-start rounded-md opacity-50 transition-opacity active:bg-accent/40 group-hover:opacity-100 sm:min-h-0 sm:min-w-0 sm:items-start sm:justify-start sm:self-start sm:bg-transparent sm:p-0 sm:pt-2"
              {...attributes}
              {...listeners}
            >
              <GripVertical className="h-5 w-5 sm:h-5 sm:w-5" />
              <span className="sr-only">Drag to reorder</span>
            </button>

            <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5 sm:grid-cols-[minmax(0,1fr)_13.5rem] sm:items-start sm:gap-2">
              <FormField
                control={form.control}
                name={`rules.${index}.pattern`}
                render={({ field }) => (
                  <FormItem className="min-w-0 space-y-0 sm:space-y-1">
                    <FormLabel className="sr-only">{t('settings.subscriptions.rules.pattern')}</FormLabel>
                    <FormControl>
                      <Input
                        placeholder={t('settings.subscriptions.rules.patternPlaceholder')}
                        {...field}
                        className="h-8 w-full min-w-0 border-muted bg-background/60 px-2.5 font-mono text-[11px] leading-snug text-foreground/90 focus:bg-background sm:h-8 sm:px-3 sm:text-xs"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex min-w-0 flex-row items-center gap-1.5 sm:contents">
                <FormField
                  control={form.control}
                  name={`rules.${index}.target`}
                  render={({ field }) => (
                    <FormItem className="min-w-0 flex-1 space-y-0 sm:w-[13.5rem] sm:shrink-0 sm:space-y-1">
                      <FormLabel className="sr-only">{t('settings.subscriptions.rules.target')}</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger
                            dir="ltr"
                            className="h-8 w-full min-w-0 border-muted bg-background/60 px-2.5 text-[11px] focus:bg-background sm:h-8 sm:px-3 sm:text-xs"
                          >
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent dir="ltr" className="scrollbar-thin z-[50]">
                          {configFormatOptions.map(option => (
                            <SelectItem key={option.value} value={option.value}>
                              <div className="flex items-center gap-1.5">
                                <option.icon className="h-4 w-4" />
                                <span className="text-xs">{t(option.label)}</span>
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <RuleActionButtons {...actionProps} className="flex shrink-0 items-center gap-1 sm:hidden" />
              </div>
            </div>
          </div>

          <RuleActionButtons {...actionProps} className="hidden shrink-0 items-center justify-end gap-2 sm:flex sm:ms-0" />

          {isDragging && <div className="pointer-events-none absolute inset-0 rounded-md border border-primary/20 bg-primary/5" />}
        </div>
      </div>

      <SubscriptionRuleAdvancedSheet
        form={form}
        ruleIndex={index}
        rowId={id}
        open={isAdvancedOpen}
        onOpenChange={setIsAdvancedOpen}
      />
    </>
  )
}
