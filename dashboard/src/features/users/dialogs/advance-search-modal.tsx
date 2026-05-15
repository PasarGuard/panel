import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DecimalInput } from '@/components/common/decimal-input'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DatePicker } from '@/components/common/date-picker'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import AdminsSelector from '@/components/common/admins-selector'
import GroupsSelector from '@/components/common/groups-selector'
import type { AdvanceSearchFormValue } from '@/features/users/forms/advance-search-form'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useGetGroupsSimple } from '@/service/api'
import { Search, X } from 'lucide-react'
import type { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Separator } from '@/components/ui/separator'

interface AdvanceSearchModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<AdvanceSearchFormValue>
  onSubmit: (values: AdvanceSearchFormValue) => void | Promise<void>
  isSudo?: boolean
  isApplying?: boolean
}

export default function AdvanceSearchModal({ isDialogOpen, onOpenChange, form, onSubmit, isSudo, isApplying = false }: AdvanceSearchModalProps) {
  const dir = useDirDetection()
  const { t } = useTranslation()
  const noDataLimitOnly = form.watch('no_data_limit')
  const noExpireOnly = form.watch('no_expire')
  const onlineOnly = form.watch('online')

  const { data: groupsData } = useGetGroupsSimple({ all: true })

  const groupIdToName = new Map((groupsData?.groups || []).map((group: any) => [group.id, group.name]))

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-full max-w-[650px] flex-col justify-start sm:h-auto" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            <span>{t('advanceSearch.title')}</span>
          </DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex h-full flex-col justify-between space-y-4">
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="flex w-full flex-1 flex-col gap-4 pb-4">
                <section className="w-full space-y-4">
                  <div className="space-y-1">
                    <h3 className="text-sm font-semibold">{t('advanceSearch.searchMode', { defaultValue: 'Search mode' })}</h3>
                    <p className="text-muted-foreground text-xs">{t('advanceSearch.searchModeDescription', { defaultValue: 'Choose how the main search field should be interpreted.' })}</p>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="is_username"
                      render={({ field }) => (
                        <FormItem className="space-y-0">
                          <FormControl>
                            <button
                              type="button"
                              aria-pressed={field.value}
                              disabled={isApplying}
                              onClick={() => {
                                field.onChange(true)
                                form.setValue('is_protocol', false, { shouldDirty: true })
                              }}
                              className={cn(
                                'flex h-full w-full flex-col items-start justify-between rounded-md border px-4 py-3 text-left transition-colors',
                                field.value ? 'border-primary bg-primary/5 shadow-sm' : 'border-border bg-background hover:border-primary/40 hover:bg-accent/30',
                                isApplying && 'cursor-not-allowed opacity-60',
                              )}
                            >
                              <div className="flex w-full items-start justify-between gap-3">
                                <span className="text-sm font-medium">{t('advanceSearch.byUsername')}</span>
                                <span className={cn('mt-1 h-2.5 w-2.5 rounded-full', field.value ? 'bg-primary' : 'bg-muted-foreground/25')} />
                              </div>
                              <p className="text-muted-foreground text-start text-xs">{t('advanceSearch.byUsernameDescription', { defaultValue: 'Search usernames and notes.' })}</p>
                            </button>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="is_protocol"
                      render={({ field }) => (
                        <FormItem className="space-y-0">
                          <FormControl>
                            <button
                              type="button"
                              aria-pressed={field.value}
                              disabled={isApplying}
                              onClick={() => {
                                field.onChange(true)
                                form.setValue('is_username', false, { shouldDirty: true })
                              }}
                              className={cn(
                                'flex h-full w-full flex-col items-start justify-between rounded-md border px-4 py-3 text-left transition-colors',
                                field.value ? 'border-primary bg-primary/5 shadow-sm' : 'border-border bg-background hover:border-primary/40 hover:bg-accent/30',
                                isApplying && 'cursor-not-allowed opacity-60',
                              )}
                            >
                              <div className="flex w-full items-start justify-between gap-3">
                                <span className="text-sm font-medium">{t('advanceSearch.byProtocol')}</span>
                                <span className={cn('mt-1 h-2.5 w-2.5 rounded-full', field.value ? 'bg-primary' : 'bg-muted-foreground/25')} />
                              </div>
                              <p className="text-muted-foreground text-start text-xs">
                                {t('advanceSearch.byProtocolDescription', { defaultValue: 'Search protocol details and configuration data.' })}
                              </p>
                            </button>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </section>

                <section className="w-full space-y-4">
                  <div className="space-y-1">
                    <h3 className="text-sm font-semibold">{t('advanceSearch.filtersSection', { defaultValue: 'Refine results' })}</h3>
                    <p className="text-muted-foreground text-xs">{t('advanceSearch.filtersSectionDescription', { defaultValue: 'Use one or more filters to narrow the list.' })}</p>
                  </div>

                  <Separator />

                  <div className="space-y-4">
                    <FormField
                      control={form.control}
                      name="status"
                      render={({ field }) => {
                        const statusOptions = [
                          { value: '0', label: t('allStatuses') },
                          { value: 'active', label: t('status.active') },
                          { value: 'on_hold', label: t('status.on_hold') },
                          { value: 'disabled', label: t('status.disabled') },
                          { value: 'expired', label: t('status.expired') },
                          { value: 'limited', label: t('status.limited') },
                        ]

                        return (
                          <FormItem className="w-full">
                            <FormLabel>{t('advanceSearch.byStatus')}</FormLabel>
                            <FormDescription>{t('advanceSearch.statusDescription', { defaultValue: 'Leave on All to include every status.' })}</FormDescription>
                            <FormControl>
                              <Select value={field.value || '0'} onValueChange={field.onChange} dir={dir} disabled={isApplying}>
                                <SelectTrigger>
                                  <SelectValue placeholder={t('advanceSearch.selectStatus')} />
                                </SelectTrigger>
                                <SelectContent>
                                  {statusOptions.map(status => (
                                    <SelectItem key={status.value} value={status.value}>
                                      {status.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )
                      }}
                    />

                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="data_limit_min"
                        render={({ field }) => (
                          <FormItem className="w-full">
                            <FormLabel>{t('advanceSearch.dataLimitMin', { defaultValue: 'Minimum data limit (GB)' })}</FormLabel>
                            <FormDescription>{t('advanceSearch.dataLimitDescription', { defaultValue: 'Filter users by data-limit range in gigabytes.' })}</FormDescription>
                            <FormControl>
                              <DecimalInput
                                placeholder={t('advanceSearch.dataLimitMinPlaceholder', { defaultValue: 'e.g. 10' })}
                                value={field.value}
                                onValueChange={field.onChange}
                                disabled={isApplying || noDataLimitOnly}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="data_limit_max"
                        render={({ field }) => (
                          <FormItem className="w-full">
                            <FormLabel>{t('advanceSearch.dataLimitMax', { defaultValue: 'Maximum data limit (GB)' })}</FormLabel>
                            <FormDescription>{t('advanceSearch.dataLimitDescription', { defaultValue: 'Filter users by data-limit range in gigabytes.' })}</FormDescription>
                            <FormControl>
                              <DecimalInput
                                placeholder={t('advanceSearch.dataLimitMaxPlaceholder', { defaultValue: 'e.g. 100' })}
                                value={field.value}
                                onValueChange={field.onChange}
                                disabled={isApplying || noDataLimitOnly}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <FormField
                      control={form.control}
                      name="no_data_limit"
                      render={({ field }) => (
                        <FormItem className="flex w-full items-start justify-between gap-4 rounded-md border p-4 space-y-0">
                          <div className="space-y-1">
                            <FormLabel>{t('advanceSearch.noDataLimit', { defaultValue: 'Only users with no data limit' })}</FormLabel>
                            <FormDescription>{t('advanceSearch.noDataLimitDescription', { defaultValue: 'Shows users whose data limit is unlimited.' })}</FormDescription>
                          </div>
                          <FormControl>
                            <Switch
                              checked={field.value}
                              disabled={isApplying}
                              onCheckedChange={checked => {
                                field.onChange(checked)
                                if (checked) {
                                  form.setValue('data_limit_min', undefined, { shouldDirty: true })
                                  form.setValue('data_limit_max', undefined, { shouldDirty: true })
                                }
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="expire_after"
                        render={({ field }) => (
                          <FormItem className="w-full">
                            <FormControl>
                              <div className={cn((isApplying || noExpireOnly) && 'pointer-events-none opacity-60')}>
                                <DatePicker
                                  mode="single"
                                  date={field.value}
                                  onDateChange={field.onChange}
                                  label={t('advanceSearch.expireAfter', { defaultValue: 'Expire after' })}
                                  placeholder={t('advanceSearch.expireAfterPlaceholder', { defaultValue: 'Select start date' })}
                                  minDate={new Date('1900-01-01')}
                                  className="[&_label]:text-sm"
                                />
                              </div>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="expire_before"
                        render={({ field }) => (
                          <FormItem className="w-full">
                            <FormControl>
                              <div className={cn((isApplying || noExpireOnly) && 'pointer-events-none opacity-60')}>
                                <DatePicker
                                  mode="single"
                                  date={field.value}
                                  onDateChange={field.onChange}
                                  label={t('advanceSearch.expireBefore', { defaultValue: 'Expire before' })}
                                  placeholder={t('advanceSearch.expireBeforePlaceholder', { defaultValue: 'Select end date' })}
                                  minDate={new Date('1900-01-01')}
                                  className="[&_label]:text-sm"
                                />
                              </div>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <FormField
                      control={form.control}
                      name="no_expire"
                      render={({ field }) => (
                        <FormItem className="flex w-full items-start justify-between gap-4 rounded-md border p-4 space-y-0">
                          <div className="space-y-1">
                            <FormLabel>{t('advanceSearch.noExpire', { defaultValue: 'Only users with no expire date' })}</FormLabel>
                            <FormDescription>{t('advanceSearch.noExpireDescription', { defaultValue: 'Shows users whose account has no expire date.' })}</FormDescription>
                          </div>
                          <FormControl>
                            <Switch
                              checked={field.value}
                              disabled={isApplying}
                              onCheckedChange={checked => {
                                field.onChange(checked)
                                if (checked) {
                                  form.setValue('expire_after', undefined, { shouldDirty: true })
                                  form.setValue('expire_before', undefined, { shouldDirty: true })
                                }
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="online_after"
                        render={({ field }) => (
                          <FormItem className="w-full">
                            <FormControl>
                              <div className={cn((isApplying || onlineOnly) && 'pointer-events-none opacity-60')}>
                                <DatePicker
                                  mode="single"
                                  date={field.value}
                                  onDateChange={field.onChange}
                                  label={t('advanceSearch.onlineAfter', { defaultValue: 'Online after' })}
                                  placeholder={t('advanceSearch.onlineAfterPlaceholder', { defaultValue: 'Select start date' })}
                                  minDate={new Date('1900-01-01')}
                                  className="[&_label]:text-sm"
                                />
                              </div>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="online_before"
                        render={({ field }) => (
                          <FormItem className="w-full">
                            <FormControl>
                              <div className={cn((isApplying || onlineOnly) && 'pointer-events-none opacity-60')}>
                                <DatePicker
                                  mode="single"
                                  date={field.value}
                                  onDateChange={field.onChange}
                                  label={t('advanceSearch.onlineBefore', { defaultValue: 'Online before' })}
                                  placeholder={t('advanceSearch.onlineBeforePlaceholder', { defaultValue: 'Select end date' })}
                                  minDate={new Date('1900-01-01')}
                                  className="[&_label]:text-sm"
                                />
                              </div>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <FormField
                      control={form.control}
                      name="online"
                      render={({ field }) => (
                        <FormItem className="flex w-full items-start justify-between gap-4 rounded-md border p-4 space-y-0">
                          <div className="space-y-1">
                            <FormLabel>{t('advanceSearch.online', { defaultValue: 'Only online users' })}</FormLabel>
                            <FormDescription>{t('advanceSearch.onlineDescription', { defaultValue: 'Shows users active in the current online window.' })}</FormDescription>
                          </div>
                          <FormControl>
                            <Switch
                              checked={field.value}
                              disabled={isApplying}
                              onCheckedChange={checked => {
                                field.onChange(checked)
                                if (checked) {
                                  form.setValue('online_after', undefined, { shouldDirty: true })
                                  form.setValue('online_before', undefined, { shouldDirty: true })
                                }
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="group"
                      render={({ field }) => (
                        <FormItem className="w-full">
                          <div className="flex items-center justify-between gap-3">
                            <FormLabel>{t('advanceSearch.byGroup')}</FormLabel>
                            {!!field.value?.length && <Badge variant="secondary">{field.value.length}</Badge>}
                          </div>
                          <FormControl>
                            <>
                              <div className="mb-3 flex flex-wrap gap-2">
                                {field.value?.map(tag => (
                                  <Badge key={tag} variant="secondary" className="flex items-center gap-1">
                                    {groupIdToName.get(tag) || tag}
                                    <X
                                      className="h-3 w-3 cursor-pointer"
                                      onClick={() => {
                                        field.onChange(field.value?.filter(item => item !== tag))
                                      }}
                                    />
                                  </Badge>
                                ))}
                              </div>
                              <Accordion type="single" collapsible className="w-full">
                                <AccordionItem value="group-select" className="border-none [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline">
                                  <AccordionTrigger className="rounded-md border px-3 py-3 text-sm hover:no-underline">{t('advanceSearch.selectGroup')}</AccordionTrigger>
                                  <AccordionContent>
                                    <div className="mt-2">
                                      <GroupsSelector control={form.control} name="group" onGroupsChange={field.onChange} disabled={isApplying} />
                                    </div>
                                  </AccordionContent>
                                </AccordionItem>
                              </Accordion>
                            </>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    {isSudo && (
                      <FormField
                        control={form.control}
                        name="admin"
                        render={({ field }) => (
                          <FormItem className="w-full">
                            <div className="flex items-center justify-between gap-3">
                              <FormLabel>{t('advanceSearch.byAdmin')}</FormLabel>
                              {!!field.value?.length && <Badge variant="secondary">{field.value.length}</Badge>}
                            </div>
                            <FormControl>
                              <>
                                <div className="mb-3 flex flex-wrap gap-2">
                                  {field.value?.map(tag => (
                                    <Badge key={tag} variant="secondary" className="flex items-center gap-1">
                                      {tag}
                                      <X
                                        className="h-3 w-3 cursor-pointer"
                                        onClick={() => {
                                          field.onChange(field.value?.filter(item => item !== tag))
                                        }}
                                      />
                                    </Badge>
                                  ))}
                                </div>
                                <Accordion type="single" collapsible className="w-full">
                                  <AccordionItem value="admin-select" className="border-none [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline">
                                    <AccordionTrigger className="rounded-md border px-3 py-3 text-sm hover:no-underline">{t('advanceSearch.selectAdmin')}</AccordionTrigger>
                                    <AccordionContent>
                                      <div className="mt-2">
                                        <AdminsSelector control={form.control} name="admin" onAdminsChange={field.onChange} disabled={isApplying} />
                                      </div>
                                    </AccordionContent>
                                  </AccordionItem>
                                </Accordion>
                              </>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                  </div>
                </section>

                <Separator />

                <section className="w-full space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <h3 className="text-sm font-semibold">{t('advanceSearch.displaySection', { defaultValue: 'Table display' })}</h3>
                      <p className="text-muted-foreground text-xs">{t('advanceSearch.displaySectionDescription', { defaultValue: 'These options only change how the user list is shown.' })}</p>
                    </div>
                    <Badge variant="outline" className="shrink-0">
                      {t('advanceSearch.uiOnly', { defaultValue: 'UI only' })}
                    </Badge>
                  </div>

                  <div className="overflow-hidden rounded-md">
                    {isSudo && (
                      <FormField
                        control={form.control}
                        name="show_created_by"
                        render={({ field }) => (
                          <FormItem className="flex w-full items-start justify-between gap-4 py-3">
                            <div className="space-y-1">
                              <FormLabel>{t('advanceSearch.showCreatedBy', { defaultValue: 'Show created by' })}</FormLabel>
                              <FormDescription>{t('advanceSearch.showCreatedByDescription', { defaultValue: 'Adds the creator column to the users table.' })}</FormDescription>
                            </div>
                            <FormControl>
                              <Switch checked={field.value} disabled={isApplying} onCheckedChange={field.onChange} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}

                    <FormField
                      control={form.control}
                      name="show_selection_checkbox"
                      render={({ field }) => (
                        <FormItem className={cn('flex w-full items-start justify-between gap-4 py-3', isSudo && 'border-t')}>
                          <div className="space-y-1">
                            <FormLabel>{t('advanceSearch.showSelectionCheckbox', { defaultValue: 'Show selection checkbox' })}</FormLabel>
                            <FormDescription>{t('advanceSearch.showSelectionCheckboxDescription', { defaultValue: 'Shows row checkboxes for bulk selection.' })}</FormDescription>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} disabled={isApplying} onCheckedChange={field.onChange} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </section>
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isApplying}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit" isLoading={isApplying} loadingText={t('applying')}>
                {t('apply')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
