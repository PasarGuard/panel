import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { ClientTemplateType, useGetClientTemplatesSimple, type ClientTemplatesSimpleResponse } from '@/service/api'
import { selectSubscriptionRuleProfile, type SubscriptionFormData } from './subscription-settings-schema'
import { CustomVariablesPopover, VariablesList } from '@/components/ui/variables-popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import { Info, Plus, Trash2 } from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

// Radix reserves the empty string to mean "show the placeholder", so "no
// profile" needs a sentinel of its own.
const PROFILE_NONE_VALUE = '__no_profile__'

export interface SubscriptionRuleAdvancedSheetProps {
  form: UseFormReturn<SubscriptionFormData>
  ruleIndex: number
  rowId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SubscriptionRuleAdvancedSheet({ form, ruleIndex, rowId, open, onOpenChange }: SubscriptionRuleAdvancedSheetProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const infoPopoverSide = isMobile ? 'bottom' : dir === 'rtl' ? 'left' : 'right'
  const infoPopoverAlign = isMobile ? 'center' : 'start'

  const responseHeaders = (form.watch(`rules.${ruleIndex}.response_headers`) || {}) as Record<string, string>
  const profileId = form.watch(`rules.${ruleIndex}.profile_id`)
  const target = form.watch(`rules.${ruleIndex}.target`)
  const responseHeaderEntries = Object.entries(responseHeaders)
  const responseHeaderCount = responseHeaderEntries.length

  // A profile written for the other core is accepted here and only fails when a
  // real client fetches its subscription, so offer just the matching ones.
  const profileTemplateType = target === 'sing_box' ? ClientTemplateType.singbox_profile : ClientTemplateType.xray_profile
  const { data: profileTemplateData, isLoading: isLoadingProfiles } = useGetClientTemplatesSimple(
    { template_type: profileTemplateType, all: true },
    {
      query: {
        enabled: open && (target === 'xray' || target === 'sing_box'),
        select: response => response as unknown as ClientTemplatesSimpleResponse,
      },
    },
  )
  const profileTemplates = profileTemplateData?.templates ?? []
  const selectedProfileIsKnown = profileId != null && profileTemplates.some(template => template.id === profileId)

  const addResponseHeader = () => {
    const nextKey = `x-header-${Object.keys(responseHeaders).length + 1}`
    form.setValue(
      `rules.${ruleIndex}.response_headers`,
      {
        ...responseHeaders,
        [nextKey]: '',
      },
      { shouldDirty: true },
    )
  }

  const updateResponseHeaderName = (currentKey: string, nextKey: string) => {
    const updatedHeaders = Object.fromEntries(responseHeaderEntries.map(([headerKey, headerValue]) => [headerKey === currentKey ? nextKey : headerKey, headerValue]))
    form.setValue(`rules.${ruleIndex}.response_headers`, updatedHeaders, { shouldDirty: true })
  }

  const updateResponseHeaderValue = (headerKey: string, value: string) => {
    form.setValue(
      `rules.${ruleIndex}.response_headers`,
      {
        ...responseHeaders,
        [headerKey]: value,
      },
      { shouldDirty: true },
    )
  }

  const removeResponseHeader = (headerKey: string) => {
    const updatedHeaders = { ...responseHeaders }
    delete updatedHeaders[headerKey]
    form.setValue(`rules.${ruleIndex}.response_headers`, updatedHeaders, { shouldDirty: true })
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={dir === 'rtl' ? 'left' : 'right'} className={cn('flex h-full max-h-screen w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg')} onOpenAutoFocus={e => e.preventDefault()}>
        <SheetHeader className="flex flex-shrink-0 flex-col space-y-1 border-b px-6 pe-14 pt-6 pb-4 text-start">
          <SheetTitle>{t('settings.subscriptions.rules.advancedTitle')}</SheetTitle>
          <SheetDescription>{t('settings.subscriptions.rules.advancedDescription')}</SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-6 py-4">
          {(target === 'xray' || target === 'sing_box') && (
            <div className="space-y-2">
              <label htmlFor={`subscription-profile-id-${rowId}`} className="text-foreground text-sm font-medium">
                {t('settings.subscriptions.rules.profileId', { defaultValue: 'Subscription profile' })}
              </label>
              <p className="text-muted-foreground text-sm">
                {t('settings.subscriptions.rules.profileIdDescription', {
                  defaultValue: 'Optional client-template profile selected when this User-Agent rule matches.',
                })}
              </p>
              <Select
                value={profileId != null ? String(profileId) : PROFILE_NONE_VALUE}
                onValueChange={value => {
                  form.setValue(`rules.${ruleIndex}`, selectSubscriptionRuleProfile(form.getValues(`rules.${ruleIndex}`), value === PROFILE_NONE_VALUE ? undefined : Number(value)), {
                    shouldDirty: true,
                  })
                }}
              >
                <SelectTrigger id={`subscription-profile-id-${rowId}`}>
                  <SelectValue placeholder={isLoadingProfiles ? t('loading', { defaultValue: 'Loading...' }) : undefined} />
                </SelectTrigger>
                <SelectContent dir={dir}>
                  <SelectItem value={PROFILE_NONE_VALUE}>{t('settings.subscriptions.rules.profileNone', { defaultValue: 'No profile' })}</SelectItem>
                  {/* A rule can outlive the profile it names, or point at one built
                      for the other core; either way the id must stay selectable so
                      opening this sheet does not silently clear it. */}
                  {profileId != null && !selectedProfileIsKnown && !isLoadingProfiles && (
                    <SelectItem value={String(profileId)}>{t('settings.subscriptions.rules.profileUnknown', { defaultValue: 'Unknown profile (#{{id}})', id: profileId })}</SelectItem>
                  )}
                  {profileTemplates.map(template => (
                    <SelectItem key={template.id} value={String(template.id)}>
                      {template.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-foreground text-sm font-medium">{t('settings.subscriptions.rules.responseHeaders')}</p>
                <p className="text-muted-foreground mt-0.5 text-sm">{t('settings.subscriptions.rules.responseHeadersDescription')}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Popover>
                  <PopoverTrigger asChild>
                    <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                      <Info className="text-muted-foreground h-4 w-4" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[min(90vw,20rem)] p-3 sm:w-80" side={infoPopoverSide} align={infoPopoverAlign} sideOffset={5}>
                    <div className="space-y-1.5">
                      <h4 className="mb-2 text-[11px] font-medium">{t('hostsDialog.variables.title')}</h4>
                      <div className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">
                        <VariablesList includeProfileTitle={true} includeFormat={true} />
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
                <CustomVariablesPopover customVariables={form.watch('custom_variables') || []} side={infoPopoverSide} align={infoPopoverAlign} sideOffset={5} />
              </div>
            </div>

            <div className="flex justify-end">
              <Button type="button" variant="outline" size="sm" onClick={addResponseHeader}>
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                {t('settings.subscriptions.rules.addHeader')}
              </Button>
            </div>

            <div className="max-h-[min(50dvh,24rem)] space-y-3 overflow-y-auto p-px">
              {responseHeaderCount > 0 ? (
                responseHeaderEntries.map(([headerKey, headerValue], index) => (
                  <div key={`${rowId}-header-${index}`} className="bg-card/50 space-y-2 rounded-lg border p-3">
                    <div className="flex items-start gap-2">
                      <Input
                        value={headerKey}
                        onChange={e => updateResponseHeaderName(headerKey, e.target.value)}
                        placeholder={t('settings.subscriptions.rules.headerName')}
                        className="font-mono text-xs"
                      />
                      <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8 shrink-0" onClick={() => removeResponseHeader(headerKey)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <Textarea
                      value={headerValue}
                      onChange={e => updateResponseHeaderValue(headerKey, e.target.value)}
                      placeholder={t('settings.subscriptions.rules.headerValue')}
                      className="min-h-[60px] resize-none font-mono text-xs"
                      rows={2}
                    />
                  </div>
                ))
              ) : (
                <div className="border-border/70 rounded-lg border border-dashed px-4 py-8 text-center">
                  <p className="text-foreground text-sm font-medium">{t('settings.subscriptions.rules.responseHeaders')}</p>
                  <p className="text-muted-foreground mt-1 text-sm">{t('settings.subscriptions.rules.responseHeadersDescription')}</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <SheetFooter className="flex-shrink-0 border-t px-6 py-4">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('close', { defaultValue: 'Close' })}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
