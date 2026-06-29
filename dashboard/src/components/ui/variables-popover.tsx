import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useClipboard } from '@/hooks/use-clipboard'
import { getGetGeneralSettingsQueryKey, useGetGeneralSettings } from '@/service/api'
import type { General } from '@/service/api'
import { useQueryClient } from '@tanstack/react-query'
import { Braces, Info } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

export interface CustomVariableDefinition {
  key: string
  value?: string
}

export const CUSTOM_VARIABLE_SAMPLE_VALUES: Record<string, string | number> = {
  SERVER_IP: '203.0.113.10',
  SERVER_IPV6: '[2001:db8::10]',
  USERNAME: 'alice',
  DATA_USAGE: '2 GB',
  DATA_LEFT: '8 GB',
  DATA_LIMIT: '10 GB',
  DAYS_LEFT: '14',
  EXPIRE_DATE: '2026-12-31',
  JALALI_EXPIRE_DATE: '1405-10-10',
  TIME_LEFT: '14d',
  STATUS_EMOJI: 'OK',
  USAGE_PERCENTAGE: '20',
  ADMIN_USERNAME: 'admin',
  PROFILE_TITLE: 'Alice Profile',
  PROTOCOL: 'vless',
  TRANSPORT: 'ws',
  url: 'https://example.com/sub/alice',
  format: 'links',
}

export function normalizeCustomVariableKey(value: string) {
  const stripped = value.trim().replace(/^\{|\}$/g, '')
  return stripped.toUpperCase().replace(/[^A-Z0-9_]/g, '_')
}

export function previewVariableValue(value: string, variables: Record<string, string | number> = CUSTOM_VARIABLE_SAMPLE_VALUES) {
  return value.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => {
    const replacement = variables[key]
    return replacement == null ? '<missing>' : String(replacement)
  })
}

interface VariablesPopoverProps {
  /** Whether to show protocol and transport variables (default: false) */
  includeProtocolTransport?: boolean
  /** Whether to show profile title variable (default: false) */
  includeProfileTitle?: boolean
  /** Whether to show format variable (default: false) */
  includeFormat?: boolean
  /** Custom variables to show alongside built-in variables. If omitted, cached global settings are used. */
  customVariables?: CustomVariableDefinition[]
  /** Popover side placement (default: "right") */
  side?: 'top' | 'right' | 'bottom' | 'left'
  /** Popover alignment (default: "start") */
  align?: 'start' | 'center' | 'end'
  /** Side offset in pixels (default: 0) */
  sideOffset?: number
}

export function VariablesPopover({
  includeProtocolTransport = false,
  includeProfileTitle = false,
  includeFormat = false,
  customVariables,
  side = 'bottom',
  align = 'start',
  sideOffset = 0,
}: VariablesPopoverProps) {
  const { t } = useTranslation()
  const { copy } = useClipboard()
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const cachedGeneralSettings = queryClient.getQueryData<General>(getGetGeneralSettingsQueryKey())
  const shouldFetchSettings = customVariables === undefined
  const { data: generalSettings } = useGetGeneralSettings({
    query: {
      enabled: shouldFetchSettings && open,
      retry: false,
      staleTime: 5 * 60 * 1000,
    },
  })
  const visibleCustomVariables = (customVariables ?? (((generalSettings ?? cachedGeneralSettings)?.custom_variables ?? []) as CustomVariableDefinition[])).filter(variable => variable.key?.trim())

  const handleCopy = async (text: string) => {
    await copy(text)
    toast.success(t('usersTable.copied'))
  }

  const VariableItem = ({ variable, translationKey }: { variable: string; translationKey: string }) => (
    <div className="flex min-w-0 items-center gap-1.5">
      <code className="bg-muted/50 hover:bg-muted shrink-0 cursor-pointer rounded-sm px-1.5 py-0.5 text-[11px] transition-colors" onClick={() => handleCopy(variable)} title={t('copy')}>
        {variable}
      </code>
      <span className="text-muted-foreground min-w-0 truncate text-[11px]" title={t(translationKey)}>
        {t(translationKey)}
      </span>
    </div>
  )
  const CustomVariableItem = ({ variable }: { variable: CustomVariableDefinition }) => {
    const token = `{${variable.key}}`
    return (
      <div className="flex min-w-0 items-center gap-1.5">
        <code className="bg-muted/50 hover:bg-muted shrink-0 cursor-pointer rounded-sm px-1.5 py-0.5 text-[11px] transition-colors" onClick={() => handleCopy(token)} title={t('copy')}>
          {token}
        </code>
        <span className="text-muted-foreground min-w-0 truncate text-[11px]" title={variable.value}>
          {variable.value || t('hostsDialog.customVariables.emptyValue', { defaultValue: 'Empty value' })}
        </span>
      </div>
    )
  }

  const variablesList = (
    <div className="space-y-1">
      {includeProfileTitle && (
        <>
          <VariableItem variable="{PROFILE_TITLE}" translationKey="hostsDialog.variables.profile_title" />
          <VariableItem variable="{url}" translationKey="hostsDialog.variables.url" />
        </>
      )}
      {includeFormat && <VariableItem variable="{format}" translationKey="hostsDialog.variables.format" />}
      <VariableItem variable="{USERNAME}" translationKey="hostsDialog.variables.username" />
      <VariableItem variable="{DATA_USAGE}" translationKey="hostsDialog.variables.data_usage" />
      <VariableItem variable="{DATA_LEFT}" translationKey="hostsDialog.variables.data_left" />
      <VariableItem variable="{DATA_LIMIT}" translationKey="hostsDialog.variables.data_limit" />
      <VariableItem variable="{DAYS_LEFT}" translationKey="hostsDialog.variables.days_left" />
      <VariableItem variable="{EXPIRE_DATE}" translationKey="hostsDialog.variables.expire_date" />
      <VariableItem variable="{JALALI_EXPIRE_DATE}" translationKey="hostsDialog.variables.jalali_expire_date" />
      <VariableItem variable="{TIME_LEFT}" translationKey="hostsDialog.variables.time_left" />
      <VariableItem variable="{STATUS_EMOJI}" translationKey="hostsDialog.variables.status_emoji" />
      <VariableItem variable="{USAGE_PERCENTAGE}" translationKey="hostsDialog.variables.usage_percentage" />
      {includeProtocolTransport && (
        <>
          <VariableItem variable="{PROTOCOL}" translationKey="hostsDialog.variables.protocol" />
          <VariableItem variable="{TRANSPORT}" translationKey="hostsDialog.variables.transport" />
        </>
      )}
      <VariableItem variable="{ADMIN_USERNAME}" translationKey="hostsDialog.variables.admin_username" />
      {visibleCustomVariables.length > 0 && (
        <div className="mt-2 space-y-1 border-t pt-2">
          <p className="text-muted-foreground text-[10px] font-medium">{t('hostsDialog.customVariables.title', { defaultValue: 'Custom variables' })}</p>
          {visibleCustomVariables.map(variable => (
            <CustomVariableItem key={variable.key} variable={variable} />
          ))}
        </div>
      )}
    </div>
  )

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className="h-auto w-auto p-0 hover:bg-transparent">
          <Info className="text-muted-foreground h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-3 sm:w-[320px]" side={side} align={align} sideOffset={sideOffset}>
        <div className="space-y-1.5">
          <h4 className="mb-2 text-[11px] font-medium">{t('hostsDialog.variables.title')}</h4>
          <div className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">{variablesList}</div>
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** Component that renders just the variables list (without popover wrapper) - for use in ArrayInput */
export function VariablesList({
  includeProtocolTransport = false,
  includeProfileTitle = false,
  includeFormat = false,
}: {
  includeProtocolTransport?: boolean
  includeProfileTitle?: boolean
  includeFormat?: boolean
}) {
  const { t } = useTranslation()
  const { copy } = useClipboard()

  const handleCopy = async (text: string) => {
    await copy(text)
    toast.success(t('usersTable.copied'))
  }

  const VariableItem = ({ variable, translationKey }: { variable: string; translationKey: string }) => (
    <div className="flex min-w-0 items-center gap-1.5">
      <code className="bg-muted/50 hover:bg-muted shrink-0 cursor-pointer rounded-sm px-1.5 py-0.5 text-[11px] transition-colors" onClick={() => handleCopy(variable)} title={t('copy')}>
        {variable}
      </code>
      <span className="text-muted-foreground min-w-0 truncate text-[11px]" title={t(translationKey)}>
        {t(translationKey)}
      </span>
    </div>
  )

  return (
    <div className="space-y-1">
      {includeProfileTitle && (
        <>
          <VariableItem variable="{PROFILE_TITLE}" translationKey="hostsDialog.variables.profile_title" />
          <VariableItem variable="{url}" translationKey="hostsDialog.variables.url" />
        </>
      )}
      {includeFormat && <VariableItem variable="{format}" translationKey="hostsDialog.variables.format" />}
      <VariableItem variable="{USERNAME}" translationKey="hostsDialog.variables.username" />
      <VariableItem variable="{DATA_USAGE}" translationKey="hostsDialog.variables.data_usage" />
      <VariableItem variable="{USAGE_PERCENTAGE}" translationKey="hostsDialog.variables.usage_percentage" />
      <VariableItem variable="{DATA_LEFT}" translationKey="hostsDialog.variables.data_left" />
      <VariableItem variable="{DATA_LIMIT}" translationKey="hostsDialog.variables.data_limit" />
      <VariableItem variable="{DAYS_LEFT}" translationKey="hostsDialog.variables.days_left" />
      <VariableItem variable="{EXPIRE_DATE}" translationKey="hostsDialog.variables.expire_date" />
      <VariableItem variable="{JALALI_EXPIRE_DATE}" translationKey="hostsDialog.variables.jalali_expire_date" />
      <VariableItem variable="{TIME_LEFT}" translationKey="hostsDialog.variables.time_left" />
      <VariableItem variable="{STATUS_EMOJI}" translationKey="hostsDialog.variables.status_emoji" />
      {includeProtocolTransport && (
        <>
          <VariableItem variable="{PROTOCOL}" translationKey="hostsDialog.variables.protocol" />
          <VariableItem variable="{TRANSPORT}" translationKey="hostsDialog.variables.transport" />
        </>
      )}
      <VariableItem variable="{ADMIN_USERNAME}" translationKey="hostsDialog.variables.admin_username" />
    </div>
  )
}

interface CustomVariablesPopoverProps {
  customVariables?: CustomVariableDefinition[]
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
  sideOffset?: number
}

export function CustomVariablesPopover({ customVariables, side = 'bottom', align = 'start', sideOffset = 0 }: CustomVariablesPopoverProps) {
  const { t } = useTranslation()
  const { copy } = useClipboard()
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const shouldFetchSettings = customVariables === undefined
  const cachedGeneralSettings = queryClient.getQueryData<General>(getGetGeneralSettingsQueryKey())
  const { data: generalSettings } = useGetGeneralSettings({
    query: {
      enabled: shouldFetchSettings && open,
      retry: false,
      staleTime: 5 * 60 * 1000,
    },
  })

  const variables = customVariables ?? (((generalSettings ?? cachedGeneralSettings)?.custom_variables ?? []) as CustomVariableDefinition[])
  const visibleVariables = variables.filter(variable => variable.key?.trim())

  const handleCopy = async (text: string) => {
    await copy(text)
    toast.success(t('usersTable.copied'))
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className="h-auto w-auto p-0 hover:bg-transparent" title={t('hostsDialog.customVariables.trigger', { defaultValue: 'Custom variables' })}>
          <Braces className="text-muted-foreground h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-3 sm:w-[360px]" side={side} align={align} sideOffset={sideOffset}>
        <div className="space-y-2">
          <h4 className="text-[11px] font-medium">{t('hostsDialog.customVariables.title', { defaultValue: 'Custom variables' })}</h4>
          {visibleVariables.length > 0 ? (
            <div className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
              {visibleVariables.map(variable => {
                const token = `{${variable.key}}`
                const preview = previewVariableValue(variable.value || '')
                return (
                  <div key={variable.key} className="space-y-1 rounded-md border p-2">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <code className="bg-muted/50 hover:bg-muted shrink-0 cursor-pointer rounded-sm px-1.5 py-0.5 text-[11px] transition-colors" onClick={() => handleCopy(token)} title={t('copy')}>
                        {token}
                      </code>
                      <span className="text-muted-foreground min-w-0 truncate text-[11px]" title={variable.value}>
                        {variable.value || t('hostsDialog.customVariables.emptyValue', { defaultValue: 'Empty value' })}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-muted-foreground text-[11px]">{t('hostsDialog.customVariables.empty', { defaultValue: 'No custom variables configured.' })}</p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
