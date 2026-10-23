import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { getGetPluginSettingsQueryKey, useGetPluginSettings, useModifyPluginSettings } from '@/service/api'
import { getErrorMessage } from '@/utils/error-utils'
import { fromFormValues, schemaFields, toFormValues, type JsonSchema, type PluginField, type PluginFormValues } from '@/features/plugins/settings-schema'

interface PluginSettingsFormProps {
  pluginId: string
  schema: JsonSchema
}

const serverFieldErrors = (error: unknown): Record<string, string> => {
  const detail = (error as { data?: { detail?: unknown } })?.data?.detail
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return {}
  return Object.fromEntries(Object.entries(detail as Record<string, unknown>).map(([key, value]) => [key.split('.')[0].split('[')[0], String(value)]))
}

export function PluginSettingsForm({ pluginId, schema }: PluginSettingsFormProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const fields = useMemo(() => schemaFields(schema), [schema])
  const { data: settings, isLoading } = useGetPluginSettings(pluginId)
  const [values, setValues] = useState<PluginFormValues>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const modify = useModifyPluginSettings()

  useEffect(() => {
    if (settings) setValues(toFormValues(fields, settings))
  }, [fields, settings])

  const setValue = (name: string, value: string | boolean) => {
    setValues(current => ({ ...current, [name]: value }))
    setErrors(current => {
      if (!(name in current)) return current
      const next = { ...current }
      delete next[name]
      return next
    })
  }

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    const { data, errors: localErrors } = fromFormValues(fields, values, settings ?? {})
    if (Object.keys(localErrors).length > 0) {
      setErrors(Object.fromEntries(Object.entries(localErrors).map(([key, kind]) => [key, kind === 'json' ? t('plugins.invalidJson') : t('plugins.invalidNumber')])))
      return
    }
    modify.mutate(
      { pluginId, data },
      {
        onSuccess: saved => {
          setErrors({})
          queryClient.setQueryData(getGetPluginSettingsQueryKey(pluginId), saved)
          toast.success(t('plugins.saved'))
        },
        onError: error => {
          const fieldErrors = serverFieldErrors(error)
          setErrors(fieldErrors)
          toast.error(t('plugins.saveFailed'), { description: Object.keys(fieldErrors).length ? undefined : getErrorMessage(error) })
        },
      },
    )
  }

  if (fields.length === 0) {
    return <p className="text-muted-foreground text-sm">{t('plugins.noSettings')}</p>
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {fields.map(field => (
        <PluginFieldInput key={field.name} field={field} value={values[field.name]} error={errors[field.name]} disabled={isLoading} onChange={value => setValue(field.name, value)} />
      ))}
      {errors.$ && <p className="text-destructive text-sm">{errors.$}</p>}
      <div className="flex justify-end">
        <LoaderButton type="submit" isLoading={modify.isPending} disabled={isLoading} loadingText={t('plugins.saving')}>
          {t('plugins.save')}
        </LoaderButton>
      </div>
    </form>
  )
}

interface PluginFieldInputProps {
  field: PluginField
  value: string | boolean | undefined
  error?: string
  disabled?: boolean
  onChange: (value: string | boolean) => void
}

function PluginFieldInput({ field, value, error, disabled, onChange }: PluginFieldInputProps) {
  const { t } = useTranslation()
  const id = `plugin-field-${field.name}`
  const hint = field.kind === 'string-array' ? t('plugins.oneValuePerLine') : field.kind === 'json' ? t('plugins.jsonValue') : undefined

  if (field.kind === 'boolean') {
    return (
      <div className="flex items-center justify-between gap-4 rounded-md border p-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor={id}>{field.label}</Label>
          {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
        </div>
        <Switch id={id} checked={value === true} disabled={disabled} onCheckedChange={checked => onChange(checked)} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {field.label}
        {field.required && <span className="text-destructive"> *</span>}
      </Label>
      {field.kind === 'enum' ? (
        <Select value={typeof value === 'string' ? value : ''} disabled={disabled} onValueChange={onChange}>
          <SelectTrigger id={id}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map(option => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : field.kind === 'string-array' || field.kind === 'json' ? (
        <Textarea
          id={id}
          dir="ltr"
          rows={field.kind === 'json' ? 6 : 4}
          className={field.kind === 'json' ? 'font-mono text-xs' : undefined}
          value={typeof value === 'string' ? value : ''}
          disabled={disabled}
          onChange={event => onChange(event.target.value)}
        />
      ) : (
        <Input
          id={id}
          type={field.kind === 'number' || field.kind === 'integer' ? 'number' : 'text'}
          step={field.kind === 'integer' ? 1 : 'any'}
          min={field.minimum}
          max={field.maximum}
          value={typeof value === 'string' ? value : ''}
          disabled={disabled}
          onChange={event => onChange(event.target.value)}
        />
      )}
      {field.description && <p className="text-muted-foreground text-xs">{field.description}</p>}
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
      {error && <p className="text-destructive text-xs">{error}</p>}
    </div>
  )
}
