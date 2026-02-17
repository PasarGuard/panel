import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { HostAdvanceSearchFormValues } from '@/components/forms/host-advance-search-form'
import useDirDetection from '@/hooks/use-dir-detection'
import { ProxyHostSecurity, UserStatus } from '@/service/api'
import { X } from 'lucide-react'
import type { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

interface HostAdvanceSearchModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<HostAdvanceSearchFormValues>
  onSubmit: (values: HostAdvanceSearchFormValues) => void
  inbounds: string[]
  isLoadingInbounds?: boolean
}

const statusOptions = [
  { value: UserStatus.active, label: 'hostsDialog.status.active' },
  { value: UserStatus.disabled, label: 'hostsDialog.status.disabled' },
  { value: UserStatus.limited, label: 'hostsDialog.status.limited' },
  { value: UserStatus.expired, label: 'hostsDialog.status.expired' },
  { value: UserStatus.on_hold, label: 'hostsDialog.status.onHold' },
] as const

const securityOptions = [
  { value: ProxyHostSecurity.inbound_default, label: 'hostsDialog.inboundDefault' },
  { value: ProxyHostSecurity.tls, label: 'tls' },
  { value: ProxyHostSecurity.none, label: 'none' },
] as const

export default function HostAdvanceSearchModal({ isDialogOpen, onOpenChange, form, onSubmit, inbounds, isLoadingInbounds }: HostAdvanceSearchModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-auto max-w-[650px] flex-col justify-start" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className={dir === 'rtl' ? 'text-right' : 'text-left'} dir={dir}>
            {t('advanceSearch.title')}
          </DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex h-full flex-col justify-between space-y-4">
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="flex w-full flex-1 flex-col items-start gap-4 pb-4">
                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => (
                    <FormItem className="w-full">
                      <FormLabel>{t('hosts.filters.userStatus', { defaultValue: 'User Status Rules' })}</FormLabel>
                      <FormDescription>
                        {t('hosts.filters.userStatusDescription', {
                          defaultValue: 'Matches hosts by configured user statuses (active, on-hold, limited, etc).',
                        })}
                      </FormDescription>
                      <FormControl>
                        <>
                          {field.value && field.value.length > 0 && (
                            <div className="mb-2 flex flex-wrap gap-2">
                              {field.value.map(status => {
                                const option = statusOptions.find(item => item.value === status)
                                if (!option) return null
                                return (
                                  <Badge key={status} variant="secondary" className="flex items-center gap-1">
                                    {t(option.label)}
                                    <X
                                      className="h-3 w-3 cursor-pointer"
                                      onClick={() => {
                                        field.onChange(field.value?.filter(item => item !== status))
                                      }}
                                    />
                                  </Badge>
                                )
                              })}
                            </div>
                          )}

                          <Select
                            value=""
                            onValueChange={(value: UserStatus) => {
                              if (!value) return
                              const current = field.value || []
                              if (!current.includes(value)) {
                                field.onChange([...current, value])
                              }
                            }}
                          >
                            <SelectTrigger dir={dir} className="w-full gap-2 py-2">
                              <SelectValue placeholder={t('hostsDialog.selectStatus')} />
                            </SelectTrigger>
                            <SelectContent dir={dir} className="bg-background">
                              {statusOptions.map(option => (
                                <SelectItem key={option.value} value={option.value} className="flex cursor-pointer items-center gap-2 px-4 py-2 focus:bg-accent" disabled={field.value?.includes(option.value)}>
                                  <div className="flex w-full items-center gap-3">
                                    <Checkbox checked={field.value?.includes(option.value)} className="h-4 w-4" />
                                    <span className="text-sm font-normal">{t(option.label)}</span>
                                  </div>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>

                          {field.value && field.value.length > 0 && (
                            <Button type="button" variant="outline" size="sm" onClick={() => field.onChange([])} className="mt-2 w-full">
                              {t('hostsDialog.clearAllStatuses')}
                            </Button>
                          )}
                        </>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="inbound_tags"
                  render={({ field }) => (
                    <FormItem className="w-full">
                      <FormLabel>{t('inbound')}</FormLabel>
                      <FormControl>
                        <>
                          {field.value && field.value.length > 0 && (
                            <div className="mb-2 flex flex-wrap gap-2">
                              {field.value.map(tag => (
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
                          )}

                          <Select
                            value=""
                            onValueChange={(value: string) => {
                              if (!value) return
                              const current = field.value || []
                              if (!current.includes(value)) {
                                field.onChange([...current, value])
                              }
                            }}
                          >
                            <SelectTrigger dir={dir}>
                              <SelectValue placeholder={t('hostsDialog.selectInbound')} />
                            </SelectTrigger>
                            <SelectContent dir={dir} className="bg-background">
                              {isLoadingInbounds ? (
                                <SelectItem value="__loading_inbounds__" disabled>
                                  {t('loading', { defaultValue: 'Loading...' })}
                                </SelectItem>
                              ) : inbounds.length > 0 ? (
                                inbounds.map(tag => (
                                  <SelectItem key={tag} value={tag} disabled={field.value?.includes(tag)}>
                                    <div className="flex w-full items-center gap-3">
                                      <Checkbox checked={field.value?.includes(tag)} className="h-4 w-4" />
                                      <span className="text-sm font-normal">{tag}</span>
                                    </div>
                                  </SelectItem>
                                ))
                              ) : (
                                <SelectItem value="__no_inbounds__" disabled>
                                  {t('noInboundsFound', { defaultValue: 'No inbounds found' })}
                                </SelectItem>
                              )}
                            </SelectContent>
                          </Select>

                          {field.value && field.value.length > 0 && (
                            <Button type="button" variant="outline" size="sm" onClick={() => field.onChange([])} className="mt-2 w-full">
                              {t('hosts.filters.clearAllInbounds', { defaultValue: 'Clear all inbounds' })}
                            </Button>
                          )}
                        </>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="security"
                  render={({ field }) => (
                    <FormItem className="w-full">
                      <FormLabel>{t('hostsDialog.security', { defaultValue: 'Security' })}</FormLabel>
                      <FormControl>
                        <Select
                          value={field.value || '__all__'}
                          onValueChange={value => {
                            field.onChange(value === '__all__' ? undefined : (value as ProxyHostSecurity))
                          }}
                        >
                          <SelectTrigger dir={dir}>
                            <SelectValue placeholder={t('hostsDialog.security', { defaultValue: 'Security' })} />
                          </SelectTrigger>
                          <SelectContent dir={dir} className="bg-background">
                            <SelectItem value="__all__">{t('all', { defaultValue: 'All' })}</SelectItem>
                            {securityOptions.map(option => (
                              <SelectItem key={option.value} value={option.value}>
                                {t(option.label, { defaultValue: option.label.toUpperCase() })}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="is_disabled"
                  render={({ field }) => (
                    <FormItem className="w-full">
                      <FormLabel>{t('hosts.filters.hostState', { defaultValue: 'Host State' })}</FormLabel>
                      <FormDescription>
                        {t('hosts.filters.hostStateDescription', {
                          defaultValue: 'Filters whether the host itself is enabled or disabled.',
                        })}
                      </FormDescription>
                      <FormControl>
                        <Select
                          value={field.value === undefined || field.value === null ? '__all__' : field.value ? 'disabled' : 'enabled'}
                          onValueChange={value => {
                            if (value === '__all__') {
                              field.onChange(undefined)
                            } else {
                              field.onChange(value === 'disabled')
                            }
                          }}
                        >
                          <SelectTrigger dir={dir}>
                            <SelectValue placeholder={t('hosts.filters.hostState', { defaultValue: 'Host State' })} />
                          </SelectTrigger>
                          <SelectContent dir={dir} className="bg-background">
                            <SelectItem value="__all__">{t('all', { defaultValue: 'All' })}</SelectItem>
                            <SelectItem value="enabled">{t('hosts.filters.enabledHosts', { defaultValue: 'Enabled Hosts' })}</SelectItem>
                            <SelectItem value="disabled">{t('hosts.filters.disabledHosts', { defaultValue: 'Disabled Hosts' })}</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit">{t('apply')}</LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
