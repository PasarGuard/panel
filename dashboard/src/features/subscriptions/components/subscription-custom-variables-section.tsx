import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { CustomVariablesPopover, normalizeCustomVariableKey } from '@/components/ui/variables-popover'
import type { SubscriptionFormData } from '@/features/subscriptions/components/subscription-settings-schema'
import { builtInVariableKeys } from '@/features/subscriptions/components/subscription-settings-schema'
import { Plus, Trash2 } from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SubscriptionCustomVariablesSectionProps {
  form: UseFormReturn<SubscriptionFormData>
}

const nextCustomVariableKey = (variables: NonNullable<SubscriptionFormData['custom_variables']>) => {
  let index = variables.length + 1
  let key = `CUSTOM_${index}`
  const usedKeys = new Set(variables.map(variable => variable.key))
  while (usedKeys.has(key)) {
    index += 1
    key = `CUSTOM_${index}`
  }
  return key
}

export function SubscriptionCustomVariablesSection({ form }: SubscriptionCustomVariablesSectionProps) {
  const { t } = useTranslation()
  const customVariables = form.watch('custom_variables') || []
  const builtInKeys = new Set<string>(builtInVariableKeys)

  const setCustomVariables = (variables: NonNullable<SubscriptionFormData['custom_variables']>) => {
    form.setValue('custom_variables', variables, {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    })
  }

  const addVariable = () => {
    setCustomVariables([...customVariables, { key: nextCustomVariableKey(customVariables), value: '' }])
  }

  const updateVariable = (index: number, patch: Partial<NonNullable<SubscriptionFormData['custom_variables']>[number]>) => {
    setCustomVariables(customVariables.map((variable, variableIndex) => (variableIndex === index ? { ...variable, ...patch } : variable)))
  }

  const removeVariable = (index: number) => {
    setCustomVariables(customVariables.filter((_, variableIndex) => variableIndex !== index))
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-2 lg:min-h-[5rem]">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-1.5">
            <h3 className="text-base font-semibold sm:text-lg">{t('settings.subscriptions.customVariables.title', { defaultValue: 'Custom Variables' })}</h3>
            <CustomVariablesPopover customVariables={customVariables} />
          </div>
          <p className="text-muted-foreground text-xs sm:text-sm">
            {t('settings.subscriptions.customVariables.description', { defaultValue: 'Create reusable placeholders for subscription and host output.' })}
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={addVariable}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          {t('settings.subscriptions.customVariables.addVariable', { defaultValue: 'Add Variable' })}
        </Button>
      </div>

      <div className="space-y-3">
        {customVariables.length > 0 ? (
          customVariables.map((variable, index) => {
            const duplicate = customVariables.some((candidate, candidateIndex) => candidateIndex !== index && candidate.key === variable.key)
            const conflictsWithBuiltIn = builtInKeys.has(variable.key)
            const hasKeyError = duplicate || conflictsWithBuiltIn
            return (
              <div key={`custom-variable-${index}`} className="bg-card/50 space-y-2 rounded-lg border p-3">
                <div className="flex flex-col gap-2 sm:flex-row">
                  <div className="min-w-0 flex-1 space-y-1">
                    <Input
                      value={variable.key}
                      onChange={event => updateVariable(index, { key: normalizeCustomVariableKey(event.target.value) })}
                      placeholder="CUSTOM_HOST"
                      className="font-mono text-xs"
                      aria-invalid={hasKeyError}
                    />
                    {hasKeyError ? (
                      <p className="text-destructive text-xs">
                        {duplicate
                          ? t('settings.subscriptions.customVariables.duplicateKey', { defaultValue: 'Duplicate custom variable key.' })
                          : t('settings.subscriptions.customVariables.builtinConflict', { defaultValue: 'This key is reserved for a built-in variable.' })}
                      </p>
                    ) : null}
                  </div>
                  <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8 shrink-0" onClick={() => removeVariable(index)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <Textarea
                  value={variable.value}
                  onChange={event => updateVariable(index, { value: event.target.value })}
                  placeholder="{USERNAME}.example.com"
                  className="min-h-[60px] resize-none font-mono text-xs"
                  rows={2}
                />
              </div>
            )
          })
        ) : (
          <div className="border-border/70 rounded-lg border border-dashed px-4 py-8 text-center">
            <p className="text-muted-foreground text-sm">{t('settings.subscriptions.customVariables.empty', { defaultValue: 'No custom variables configured.' })}</p>
          </div>
        )}
      </div>
    </div>
  )
}
