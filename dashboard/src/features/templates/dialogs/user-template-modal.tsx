import GroupsSelector from '@/components/common/groups-selector'
import { DecimalInput } from '@/components/common/decimal-input'
import { TimeUnitSelect, TIME_UNIT_SECONDS, type TimeUnit } from '@/components/common/time-unit-select'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import useDirDetection from '@/hooks/use-dir-detection'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import {
  DataLimitResetStrategy,
  getGetGroupsSimpleQueryKey,
  getGetUserTemplatesQueryKey,
  getGetUserTemplatesSimpleQueryKey,
  ShadowsocksMethods,
  useCreateUserTemplate,
  useModifyUserTemplate,
  UserStatusCreate,
  XTLSFlows,
} from '@/service/api'
import { formatBytes, gbToBytes } from '@/utils/formatByte'
import { queryClient } from '@/utils/query-client.ts'
import React, { useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ChevronDown, FileUser, Pencil } from 'lucide-react'
import { userTemplateFormDefaultValues, type UserTemplatesFromValueInput } from '@/features/templates/forms/user-template-form'

interface UserTemplatesModalprops {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<UserTemplatesFromValueInput>
  editingUserTemplate: boolean
  editingUserTemplateId?: number
}

type StatusSelectItemProps = {
  value: string
  children: React.ReactNode
  onSelect?: (value: string) => void
}

const StatusSelect = ({ value, onValueChange, placeholder, children }: { value?: string; onValueChange?: (value: string) => void; placeholder?: string; children: React.ReactNode }) => {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation()

  const handleSelect = (selectedValue: string) => {
    onValueChange?.(selectedValue)
    setOpen(false)
  }

  const getStatusText = (statusValue?: string) => {
    if (!statusValue) return placeholder || t('status.active', { defaultValue: 'Active' })

    switch (statusValue) {
      case UserStatusCreate.active:
        return t('status.active', { defaultValue: 'Active' })
      case UserStatusCreate.on_hold:
        return t('status.on_hold', { defaultValue: 'On Hold' })
      default:
        return placeholder || t('status.active', { defaultValue: 'Active' })
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} className="h-9 w-full justify-between px-3 py-2 text-sm">
          <span className="truncate">{getStatusText(value)}</span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-1" align="start">
        {React.Children.map(children, child => {
          if (React.isValidElement<StatusSelectItemProps>(child) && typeof child.props.value === 'string') {
            return React.cloneElement(child, {
              onSelect: handleSelect,
            })
          }
          return child
        })}
      </PopoverContent>
    </Popover>
  )
}

const StatusSelectItem = ({ value, children, onSelect }: StatusSelectItemProps) => {
  const getDotColor = () => {
    switch (value) {
      case UserStatusCreate.active:
        return 'bg-green-500'
      case UserStatusCreate.on_hold:
        return 'bg-violet-500'
      default:
        return 'bg-gray-500'
    }
  }

  return (
    <div
      className="hover:bg-accent hover:text-accent-foreground relative flex w-full min-w-0 cursor-pointer items-center rounded-sm px-2 py-2 text-sm transition-colors outline-none select-none"
      onClick={() => onSelect?.(value)}
    >
      <span className="min-w-0 flex-1 truncate pr-2">{children}</span>
      <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
        <div className={`h-2 w-2 rounded-full ${getDotColor()}`} />
      </span>
    </div>
  )
}

export default function UserTemplateModal({ isDialogOpen, onOpenChange, form, editingUserTemplate, editingUserTemplateId }: UserTemplatesModalprops) {
  const dir = useDirDetection()
  const { t } = useTranslation()
  const addUserTemplateMutation = useCreateUserTemplate()
  const handleError = useDynamicErrorHandler()
  const modifyUserTemplateMutation = useModifyUserTemplate()
  const [timeType, setTimeType] = useState<TimeUnit>('seconds')
  const [expireDurationUnit, setExpireDurationUnit] = useState<TimeUnit>('days')
  const [loading, setLoading] = useState(false)
  const prevStatusForSyncRef = React.useRef<string | undefined>(undefined)

  useEffect(() => {
    if (!isDialogOpen) return
    queryClient.invalidateQueries({
      queryKey: getGetGroupsSimpleQueryKey({ all: true }),
    })
  }, [isDialogOpen])

  useEffect(() => {
    if (!isDialogOpen || editingUserTemplate) return
    form.reset(userTemplateFormDefaultValues)
    setExpireDurationUnit('days')
    setTimeType('seconds')
    prevStatusForSyncRef.current = undefined
  }, [isDialogOpen, editingUserTemplate, form])

  useEffect(() => {
    if (!isDialogOpen) {
      setExpireDurationUnit('days')
    }
  }, [isDialogOpen])

  const status = form.watch('status')

  useEffect(() => {
    if (!isDialogOpen) {
      prevStatusForSyncRef.current = undefined
      return
    }
    if (prevStatusForSyncRef.current === undefined) {
      prevStatusForSyncRef.current = status
      return
    }
    if (prevStatusForSyncRef.current === status) return
    prevStatusForSyncRef.current = status
    if (status === UserStatusCreate.on_hold) {
      form.clearErrors('on_hold_timeout')
      void form.trigger('expire_duration')
    } else {
      form.setValue('on_hold_timeout', undefined)
      form.clearErrors('on_hold_timeout')
      form.clearErrors('expire_duration')
      void form.trigger('expire_duration')
    }
  }, [status, form, isDialogOpen])

  const onSubmit = async (values: UserTemplatesFromValueInput) => {
    setLoading(true)
    try {
      const status = values.status ?? UserStatusCreate.active
      const normalizedDataLimitGb = Number(values.data_limit ?? 0)
      const hasDataLimit = Number.isFinite(normalizedDataLimitGb) && normalizedDataLimitGb > 0
      const normalizedHwidLimit = values.hwid_limit == null ? null : Number(values.hwid_limit)
      // Build payload according to UserTemplateCreate interface
      const submitData = {
        name: values.name,
        data_limit: hasDataLimit ? gbToBytes(normalizedDataLimitGb as any) : 0,
        hwid_limit: normalizedHwidLimit == null ? null : Number.isFinite(normalizedHwidLimit) ? Math.floor(normalizedHwidLimit) : null,
        expire_duration: values.expire_duration,
        username_prefix: values.username_prefix || '',
        username_suffix: values.username_suffix || '',
        group_ids: values.groups, // map groups to group_ids
        status,
        on_hold_timeout: status === UserStatusCreate.on_hold ? values.on_hold_timeout : undefined,
        data_limit_reset_strategy: hasDataLimit ? values.data_limit_reset_strategy : undefined,
        reset_usages: values.reset_usages,
        extra_settings:
          values.method || values.flow
            ? {
              method: values.method,
              flow: values.flow,
            }
            : undefined,
      }

      if (editingUserTemplate && editingUserTemplateId) {
        await modifyUserTemplateMutation.mutateAsync({
          templateId: editingUserTemplateId,
          data: submitData,
        })
        toast.success(
          t('templates.editSuccess', {
            name: values.name,
            defaultValue: 'User Templates «{name}» has been updated successfully',
          }),
        )
      } else {
        await addUserTemplateMutation.mutateAsync({
          data: submitData,
        })
        toast.success(
          t('templates.createSuccess', {
            name: values.name,
            defaultValue: 'User Templates «{name}» has been created successfully',
          }),
        )
      }
      // Invalidate both template list variants used across pages/modals.
      queryClient.invalidateQueries({ queryKey: getGetUserTemplatesQueryKey() })
      queryClient.invalidateQueries({ queryKey: getGetUserTemplatesSimpleQueryKey() })
      onOpenChange(false)
      form.reset()
    } catch (error: any) {
      const fields = [
        'name',
        'data_limit',
        'hwid_limit',
        'expire_duration',
        'username_prefix',
        'username_suffix',
        'groups',
        'status',
        'on_hold_timeout',
        'data_limit_reset_strategy',
        'method',
        'flow',
        'reset_usages',
      ]
      handleError({ error, fields, form, contextKey: 'groups' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="h-auto max-w-[1000px]" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingUserTemplate ? <Pencil className="h-5 w-5" /> : <FileUser className="h-5 w-5" />}
            <span>{editingUserTemplate ? t('editUserTemplateModal.title') : t('userTemplateModal.title')}</span>
          </DialogTitle>
          <DialogDescription className="sr-only">{t('userTemplateModal.description', { defaultValue: 'Configure user template settings.' })}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col">
            <div className="-mr-4 flex max-h-[80dvh] flex-col items-start gap-4 overflow-y-auto px-2 pr-4 pb-6 sm:max-h-[75dvh] sm:flex-row">
              <div className="w-full flex-1 space-y-4">
                <div className="flex w-full flex-row gap-2">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('templates.name')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('templates.name')} isError={!!form.formState.errors.name} {...field} className="min-w-40 sm:w-72" />
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
                        <FormLabel>{t('templates.status')}</FormLabel>
                        <FormControl>
                          <StatusSelect value={field.value} onValueChange={field.onChange} placeholder={t('status.active', { defaultValue: 'Active' })}>
                            <StatusSelectItem value={UserStatusCreate.active}>{t('status.active', { defaultValue: 'Active' })}</StatusSelectItem>
                            <StatusSelectItem value={UserStatusCreate.on_hold}>{t('status.on_hold', { defaultValue: 'On Hold' })}</StatusSelectItem>
                          </StatusSelect>
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="data_limit"
                  render={({ field }) => (
                    <FormItem className="relative flex-1">
                      <FormLabel>{t('templates.dataLimit')}</FormLabel>
                      <FormControl>
                        <div className="relative">
                          <DecimalInput placeholder={t('templates.dataLimit')} value={field.value} emptyValue={0} zeroValue={0} onValueChange={value => field.onChange(value ?? 0)} className="pr-10" />
                          <span className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm font-medium">{t('userDialog.gb', { defaultValue: 'GB' })}</span>
                        </div>
                      </FormControl>
                      {field.value !== null && field.value !== undefined && field.value > 0 && field.value < 1 && (
                        <p dir="ltr" className="text-muted-foreground mt-2 w-full text-end text-xs">
                          {formatBytes(Math.round(field.value * 1024 * 1024 * 1024))}
                        </p>
                      )}
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="data_limit_reset_strategy"
                  render={({ field }) => {
                    const datalimit = form.watch('data_limit')
                    const normalizedDataLimitGb = Number(datalimit ?? 0)
                    const hasDataLimit = Number.isFinite(normalizedDataLimitGb) && normalizedDataLimitGb > 0
                    if (!hasDataLimit) {
                      return <></>
                    }
                    return (
                      <FormItem className="flex-1">
                        <FormLabel>{t('templates.userDataLimitStrategy')}</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('userDialog.resetStrategyNo', { defaultValue: 'No' })} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value={DataLimitResetStrategy['no_reset']}>{t('userDialog.resetStrategyNo')}</SelectItem>
                            <SelectItem value={DataLimitResetStrategy['day']}>{t('userDialog.resetStrategyDaily')}</SelectItem>
                            <SelectItem value={DataLimitResetStrategy['week']}>{t('userDialog.resetStrategyWeekly')}</SelectItem>
                            <SelectItem value={DataLimitResetStrategy['month']}>{t('userDialog.resetStrategyMonthly')}</SelectItem>
                            <SelectItem value={DataLimitResetStrategy['year']}>{t('userDialog.resetStrategyAnnually')}</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name="expire_duration"
                  render={({ field }) => {
                    const unitSeconds = TIME_UNIT_SECONDS[expireDurationUnit]

                    return (
                      <FormItem className="flex-1">
                        <FormLabel className="text-left">{t('templates.expire')}</FormLabel>
                        <FormControl>
                          <div className="relative" dir="ltr">
                            <DecimalInput
                              placeholder={t('templates.expire')}
                              value={field.value}
                              emptyValue={0}
                              zeroValue={0}
                              toDisplayValue={value => value / unitSeconds}
                              toValue={displayValue => displayValue * unitSeconds}
                              onValueChange={value => {
                                field.onChange(value ?? 0)
                                void form.trigger('expire_duration')
                              }}
                              className={dir === 'rtl' ? 'pl-20' : 'pr-20'}
                            />
                            <TimeUnitSelect
                              value={expireDurationUnit}
                              onValueChange={setExpireDurationUnit}
                              triggerClassName={`absolute top-0 h-full w-20 rounded-none border-y-0 focus:ring-0 focus:ring-offset-0 ${dir === 'rtl' ? 'left-0 border-l-0' : 'right-0 border-r-0'}`}
                            />
                          </div>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name="reset_usages"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between space-y-0 rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <FormLabel className="text-base">
                          {t('templates.resetUsages', {
                            defaultValue: 'Reset Usages',
                          })}
                        </FormLabel>
                      </div>
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="hwid_limit"
                  render={({ field }) => (
                    <FormItem className="relative flex-1">
                      <FormLabel>{t('templates.hwidLimit', { defaultValue: 'HWID Limit' })}</FormLabel>
                      <FormControl>
                        <DecimalInput
                          placeholder={t('templates.hwidLimitPlaceholder', { defaultValue: 'Empty for default, 0 for unlimited' })}
                          value={field.value}
                          emptyValue={undefined}
                          zeroValue={0}
                          keepZeroOnBlur
                          normalizeDisplayValueOnBlur={Math.floor}
                          onValueChange={field.onChange}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="on_hold_timeout"
                  render={({ field }) => {
                    const convertToDisplayValue = (value: number | undefined) => {
                      if (value == null || value === 0) return ''
                      return value / TIME_UNIT_SECONDS[timeType]
                    }

                    const convertToSeconds = (inputValue: string, type: TimeUnit) => {
                      const numValue = parseFloat(inputValue)
                      if (isNaN(numValue) || numValue < 0) return undefined
                      return numValue * TIME_UNIT_SECONDS[type]
                    }

                    if (status !== UserStatusCreate.on_hold) {
                      return <></>
                    }
                    return (
                      <FormItem className="flex-1">
                        <FormLabel>{t('templates.onHoldTimeout')}</FormLabel>
                        <FormControl>
                          <div className="border-border flex flex-row overflow-hidden rounded-md border">
                            <div className="flex-[3]">
                              <Input
                                type="number"
                                step="any"
                                min="0"
                                placeholder={t('templates.onHoldTimeout')}
                                value={convertToDisplayValue(field.value)}
                                onChange={e => {
                                  const secondsValue = convertToSeconds(e.target.value, timeType)
                                  field.onChange(secondsValue)
                                }}
                                className="flex-[3] rounded-none border-0 focus-visible:ring-0 focus-visible:ring-offset-0"
                              />
                            </div>
                            <div className="w-20 shrink-0">
                              <TimeUnitSelect value={timeType} onValueChange={setTimeType} triggerClassName="w-full rounded-none border-0 px-2 focus:ring-0 focus:ring-offset-0" />
                            </div>
                          </div>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />

                <FormField
                  control={form.control}
                  name="username_prefix"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('templates.prefix')}</FormLabel>
                      <FormControl>
                        <Input type="text" placeholder={t('templates.prefix')} {...field} onChange={e => field.onChange(e.target.value)} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="username_suffix"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('templates.suffix')}</FormLabel>
                      <FormControl>
                        <Input type="text" placeholder={t('templates.suffix')} {...field} onChange={e => field.onChange(e.target.value)} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <div className="w-full flex-1 space-y-4">
                <FormField
                  control={form.control}
                  name="method"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('templates.method')}</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={t('userDialog.proxySettings.method', { defaultValue: 'Select Method' })} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={ShadowsocksMethods['aes-128-gcm']}>aes-128-gcm</SelectItem>
                          <SelectItem value={ShadowsocksMethods['aes-256-gcm']}>aes-256-gcm</SelectItem>
                          <SelectItem value={ShadowsocksMethods['chacha20-ietf-poly1305']}>chacha20-ietf-poly1305</SelectItem>
                          <SelectItem value={ShadowsocksMethods['xchacha20-poly1305']}>xchacha20-poly1305</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="flow"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('templates.flow')}</FormLabel>
                      <Select onValueChange={value => field.onChange(value === 'null' ? undefined : value)} value={field.value ?? 'null'}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={t('userDialog.proxySettings.flow', { defaultValue: 'Flow' })} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="null">{t('userDialog.proxySettings.flow.none', { defaultValue: 'None' })}</SelectItem>
                          <SelectItem value={XTLSFlows['xtls-rprx-vision']}>xtls-rprx-vision</SelectItem>
                          <SelectItem value={XTLSFlows['xtls-rprx-vision-udp443']}>xtls-rprx-vision-udp443</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField control={form.control} name="groups" render={({ field }) => <GroupsSelector control={form.control} name="groups" onGroupsChange={field.onChange} />} />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit" isLoading={loading} loadingText={editingUserTemplate ? t('modifying', { defaultValue: 'Modifying...' }) : t('creating')}>
                {editingUserTemplate ? t('modify', { defaultValue: 'Modify' }) : t('create')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
