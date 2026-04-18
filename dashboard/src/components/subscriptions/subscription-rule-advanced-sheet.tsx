import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import type { SubscriptionFormData } from './subscription-settings-schema'
import { VariablesList } from '@/components/ui/variables-popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import { Info, Plus, Trash2 } from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SubscriptionRuleAdvancedSheetProps {
  form: UseFormReturn<SubscriptionFormData>
  ruleIndex: number
  rowId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SubscriptionRuleAdvancedSheet({
  form,
  ruleIndex,
  rowId,
  open,
  onOpenChange,
}: SubscriptionRuleAdvancedSheetProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const infoPopoverSide = isMobile ? 'bottom' : dir === 'rtl' ? 'left' : 'right'
  const infoPopoverAlign = isMobile ? 'center' : 'start'

  const responseHeaders = (form.watch(`rules.${ruleIndex}.response_headers`) || {}) as Record<string, string>
  const responseHeaderEntries = Object.entries(responseHeaders)
  const responseHeaderCount = responseHeaderEntries.length

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
    const updatedHeaders = Object.fromEntries(
      responseHeaderEntries.map(([headerKey, headerValue]) => [headerKey === currentKey ? nextKey : headerKey, headerValue]),
    )
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
      <SheetContent
        side={dir === 'rtl' ? 'left' : 'right'}
        className={cn('flex h-full max-h-screen w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg')}
        onOpenAutoFocus={e => e.preventDefault()}
      >
        <SheetHeader className="flex flex-col flex-shrink-0 space-y-1 border-b px-6 pb-4 pt-6 pe-14 text-start">
          <SheetTitle>{t('settings.subscriptions.rules.advancedTitle')}</SheetTitle>
          <SheetDescription>{t('settings.subscriptions.rules.advancedDescription')}</SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-6 py-4">
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{t('settings.subscriptions.rules.responseHeaders')}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">{t('settings.subscriptions.rules.responseHeadersDescription')}</p>
              </div>
              <Popover>
                <PopoverTrigger asChild>
                  <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                    <Info className="h-4 w-4 text-muted-foreground" />
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
                {t('settings.subscriptions.rules.addHeader')}
              </Button>
            </div>

            <div className="max-h-[min(50dvh,24rem)] space-y-3 overflow-y-auto pr-0.5">
              {responseHeaderCount > 0 ? (
                responseHeaderEntries.map(([headerKey, headerValue], index) => (
                  <div key={`${rowId}-header-${index}`} className="space-y-2 rounded-lg border bg-card/50 p-3">
                    <div className="flex items-start gap-2">
                      <Input
                        value={headerKey}
                        onChange={e => updateResponseHeaderName(headerKey, e.target.value)}
                        placeholder={t('settings.subscriptions.rules.headerName')}
                        className="font-mono text-xs"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0 text-destructive hover:bg-destructive/10"
                        onClick={() => removeResponseHeader(headerKey)}
                      >
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
                <div className="rounded-lg border border-dashed border-border/70 px-4 py-8 text-center">
                  <p className="text-sm font-medium text-foreground">{t('settings.subscriptions.rules.responseHeaders')}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{t('settings.subscriptions.rules.responseHeadersDescription')}</p>
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
