import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { LoaderButton } from '@/components/ui/loader-button'
import useDirDetection from '@/hooks/use-dir-detection'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Search, X, Hash } from 'lucide-react'
import { APIKeyStatus } from '@/service/api'
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
      <DialogContent className="h-auto w-full max-w-lg" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            <span>{t('advanceSearch.title')}</span>
          </DialogTitle>
          <DialogDescription className="sr-only">
            {t('advanceSearch.description', { defaultValue: 'Filter API keys by identifier and status.' })}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="grid grid-cols-1 gap-4">
                <FormField
                  control={form.control}
                  name="key_id"
                  render={({ field }) => (
                    <FormItem className="w-full">
                      <FormLabel className="flex items-center gap-2">
                        <Hash className="h-3 w-3" />
                        {t('apiKeys.keyId')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder={t('apiKeys.keyId')}
                          {...field}
                          value={field.value || ''}
                          onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : undefined)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => (
                    <FormItem className="w-full">
                      <FormLabel>{t('advanceSearch.byStatus')}</FormLabel>
                      <div className="flex gap-2">
                        <Select
                          value={field.value?.[0] || ''}
                          onValueChange={(value: APIKeyStatus) => {
                            field.onChange(value ? [value] : [])
                          }}
                        >
                          <FormControl>
                            <SelectTrigger dir={dir} className="min-w-0 flex-1">
                              <SelectValue placeholder={t('hostsDialog.selectStatus', { defaultValue: 'Select status' })} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent dir={dir}>
                            {statusOptions.map(option => (
                              <SelectItem key={option.value} value={option.value}>
                                {t(option.label)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {!!field.value?.length && (
                          <Button
                            type="button"
                            variant="outline"
                            size="icon-md"
                            className="h-10 w-10 shrink-0"
                            onClick={() => field.onChange([])}
                            aria-label={t('clear', { defaultValue: 'Clear' })}
                            title={t('clear', { defaultValue: 'Clear' })}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit">
                {t('apply')}
              </LoaderButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
