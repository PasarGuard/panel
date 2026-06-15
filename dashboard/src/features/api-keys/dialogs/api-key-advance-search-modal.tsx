import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { LoaderButton } from '@/components/ui/loader-button'
import useDirDetection from '@/hooks/use-dir-detection'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Search, X, Hash } from 'lucide-react'
import { APIKeyStatus } from '@/service/api'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import type { ApiKeyAdvanceSearchFormValue } from '@/features/api-keys/forms/api-key-advance-search-form'

interface ApiKeyAdvanceSearchModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<ApiKeyAdvanceSearchFormValue>
  onSubmit: (values: ApiKeyAdvanceSearchFormValue) => void
}

const statusOptions = [
  { value: APIKeyStatus.active, label: 'admins.active' },
  { value: APIKeyStatus.disabled, label: 'admins.disabled' },
] as const

export default function ApiKeyAdvanceSearchModal({ isDialogOpen, onOpenChange, form, onSubmit }: ApiKeyAdvanceSearchModalProps) {
  const dir = useDirDetection()
  const { t } = useTranslation()

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-auto max-w-[650px] flex-col justify-start " onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            <span>{t('advanceSearch.title')}</span>
          </DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex h-full flex-col justify-between space-y-4">
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="flex w-full flex-1 flex-col items-start gap-4 pb-4">
                <FormField
                  control={form.control}
                  name="key_id"
                  render={({ field }) => (
                    <FormItem className="w-full">
                      <FormLabel className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                        <Hash className="h-3 w-3" />
                        {t('apiKeys.keyId')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder={t('apiKeys.keyId')}
                          {...field}
                          value={field.value || ''}
                          onChange={(e) => field.onChange(e.target.value ? parseInt(e.target.value) : undefined)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => {
                    return (
                      <FormItem className="w-full flex-1">
                        <FormLabel>{t('advanceSearch.byStatus')}</FormLabel>
                        <FormControl>
                          <>
                            {/* Display selected statuses as badges */}
                            {field.value && field.value.length > 0 && (
                              <div className="flex flex-wrap gap-2 mb-2">
                                {field.value.map(status => {
                                  const option = statusOptions.find(opt => opt.value === status)
                                  if (!option) return null
                                  return (
                                    <Badge key={status} variant="secondary" className="flex items-center gap-1">
                                      {t(option.label)}
                                      <X
                                        className="h-3 w-3 cursor-pointer"
                                        onClick={() => {
                                          field.onChange(field.value?.filter(s => s !== status))
                                        }}
                                      />
                                    </Badge>
                                  )
                                })}
                              </div>
                            )}
                            
                            {/* Status selector with checkboxes */}
                            <Select
                              value=""
                              onValueChange={(value: APIKeyStatus) => {
                                if (!value) return
                                const currentValue = field.value || []
                                if (!currentValue.includes(value)) {
                                  field.onChange([...currentValue, value])
                                }
                              }}
                            >
                              <SelectTrigger dir={dir} className="w-full gap-2 py-2">
                                <SelectValue placeholder={t('hostsDialog.selectStatus')} />
                              </SelectTrigger>
                              <SelectContent dir={dir} className="bg-background">
                                {statusOptions.map(option => (
                                  <SelectItem
                                    key={option.value}
                                    value={option.value}
                                    className="flex cursor-pointer items-center gap-2 px-4 py-2 focus:bg-accent"
                                    disabled={field.value?.includes(option.value)}
                                  >
                                    <div className="flex w-full items-center gap-3">
                                      <Checkbox checked={field.value?.includes(option.value)} className="h-4 w-4" />
                                      <span className="text-sm font-normal">{t(option.label)}</span>
                                    </div>
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            
                            {/* Clear all button */}
                            {field.value && field.value.length > 0 && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => field.onChange([])}
                                className="mt-2 w-full"
                              >
                                {t('hostsDialog.clearAllStatuses')}
                              </Button>
                            )}
                          </>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit">
                {t('apply')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
