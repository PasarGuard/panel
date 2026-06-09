import type { SubscriptionFormData } from '@/features/subscriptions/components/subscription-settings-schema'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Textarea } from '@/components/ui/textarea'
import { VariablesList } from '@/components/ui/variables-popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { Info, Plus, Trash2 } from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SubscriptionResponseHeadersSectionProps {
  form: UseFormReturn<SubscriptionFormData>
}

export function SubscriptionResponseHeadersSection({ form }: SubscriptionResponseHeadersSectionProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const infoPopoverSide = isMobile ? 'bottom' : dir === 'rtl' ? 'left' : 'right'
  const infoPopoverAlign = isMobile ? 'center' : 'start'

  const responseHeaders = (form.watch('response_headers') || {}) as Record<string, string>
  const responseHeaderEntries = Object.entries(responseHeaders)
  const responseHeaderCount = responseHeaderEntries.length

  const addResponseHeader = () => {
    const nextKey = `x-header-${Object.keys(responseHeaders).length + 1}`
    form.setValue(
      'response_headers',
      {
        ...responseHeaders,
        [nextKey]: '',
      },
      { shouldDirty: true },
    )
  }

  const updateResponseHeaderName = (currentKey: string, nextKey: string) => {
    const updatedHeaders = Object.fromEntries(responseHeaderEntries.map(([headerKey, headerValue]) => [headerKey === currentKey ? nextKey : headerKey, headerValue]))
    form.setValue('response_headers', updatedHeaders, { shouldDirty: true })
  }

  const updateResponseHeaderValue = (headerKey: string, value: string) => {
    form.setValue(
      'response_headers',
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
    form.setValue('response_headers', updatedHeaders, { shouldDirty: true })
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-2">
          <h3 className="text-base font-semibold sm:text-lg">{t('settings.subscriptions.responseHeaders.title')}</h3>
          <p className="text-muted-foreground text-xs sm:text-sm">{t('settings.subscriptions.responseHeaders.description')}</p>
        </div>
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
      </div>

      <div className="flex justify-end">
        <Button type="button" variant="outline" size="sm" onClick={addResponseHeader}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          {t('settings.subscriptions.responseHeaders.addHeader')}
        </Button>
      </div>

      <div className="space-y-3">
        {responseHeaderCount > 0 ? (
          responseHeaderEntries.map(([headerKey, headerValue], index) => (
            <div key={`sub-header-${index}`} className="bg-card/50 space-y-2 rounded-lg border p-3">
              <div className="flex items-start gap-2">
                <Input
                  value={headerKey}
                  onChange={e => updateResponseHeaderName(headerKey, e.target.value)}
                  placeholder={t('settings.subscriptions.responseHeaders.headerName')}
                  className="font-mono text-xs"
                />
                <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8 shrink-0" onClick={() => removeResponseHeader(headerKey)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              <Textarea
                value={headerValue}
                onChange={e => updateResponseHeaderValue(headerKey, e.target.value)}
                placeholder={t('settings.subscriptions.responseHeaders.headerValue')}
                className="min-h-[60px] resize-none font-mono text-xs"
                rows={2}
              />
            </div>
          ))
        ) : (
          <div className="border-border/70 rounded-lg border border-dashed px-4 py-8 text-center">
            <p className="text-muted-foreground text-sm">{t('settings.subscriptions.responseHeaders.noHeaders')}</p>
          </div>
        )}
      </div>
    </div>
  )
}
