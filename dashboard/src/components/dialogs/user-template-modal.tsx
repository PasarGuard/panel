import GroupsSelector from '@/components/common/groups-selector'
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
import React, { useEffect, useLayoutEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ChevronDown, FileUser, Pencil } from 'lucide-react'
import { userTemplateFormDefaultValues, type UserTemplatesFromValueInput } from '@/components/forms/user-template-form'

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

const StatusSelect = ({
  value,
  onValueChange,
  placeholder,
  children,
}: {
  value?: string
  onValueChange?: (value: string) => void
  placeholder?: string
  children: React.ReactNode
}) => {
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
      <PopoverContent className="w-[--radix-popover-trigger-width] p-1" align="start">
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
      className="relative flex w-full min-w-0 cursor-pointer select-none items-center rounded-sm px-2 py-2 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground"
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
  const [timeType, setTimeType] = useState<'seconds' | 'hours' | 'days'>('seconds')
  const [loading, setLoading] = useState(false)
  const dataLimitInputRef = React.useRef<string>('')
  const expireDurationInputRef = React.useRef<string>('')
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
    dataLimitInputRef.current = ''
    expireDurationInputRef.current = ''
    setTimeType('seconds')
    prevStatusForSyncRef.current = undefined
  }, [isDialogOpen, editingUserTemplate, form])

  useEffect(() => {
    if (!isDialogOpen) {
      dataLimitInputRef.current = ''
      expireDurationInputRef.current = ''
    }
  }, [isDialogOpen])

  /** Keep display refs aligned with form when opening the dialog or switching which template is edited (refs are not part of RHF state). */
  useLayoutEffect(() => {
    if (!isDialogOpen) return
    const daySec = 24 * 60 * 60
    const dl = form.getValues('data_limit')
    if (dl == null || dl === undefined || Number(dl) <= 0) {
      dataLimitInputRef.current = ''
    } else {
      dataLimitInputRef.current = String(dl)
    }
    const ed = form.getValues('expire_duration')
    if (ed == null || ed === undefined || Number(ed) <= 0) {
      expireDurationInputRef.current = ''
    } else {
      expireDurationInputRef.current = String(Number(ed) / daySec)
    }
  }, [isDialogOpen, editingUserTemplateId])

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
      // Build payload according to UserTemplateCreate interface
      const submitData = {
        name: values.name,
        data_limit: hasDataLimit ? gbToBytes(normalizedDataLimitGb as any) : 0,
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
          <DialogDescription className="sr-only">
            {t('userTemplateModal.description', { defaultValue: 'Configure user template settings.' })}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col">
            <div className="-mr-4 flex max-h-[80dvh] flex-col items-start gap-4 overflow-y-auto px-2 pb-6 pr-4 sm:max-h-[75dvh] sm:flex-row">
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
                          <StatusSelect
                            value={field.value}
                            onValueChange={field.onChange}
                            placeholder={t('status.active', { defaultValue: 'Active' })}
                          >
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
                  render={({ field }) => {
                    if (dataLimitInputRef.current === '' && field.value !== null && field.value !== undefined && field.value > 0) {
                      dataLimitInputRef.current = String(field.value)
                    } else if (
                      (field.value === null || field.value === undefined || field.value === 0) &&
                      dataLimitInputRef.current !== '' &&
                      !dataLimitInputRef.current.endsWith('.')
                    ) {
                      dataLimitInputRef.current = ''
                    }

                    const displayValue =
                      dataLimitInputRef.current !== '' ? dataLimitInputRef.current : field.value !== null && field.value !== undefined && field.value > 0 ? String(field.value) : ''

                    return (
                      <FormItem className="relative flex-1">
                        <FormLabel>{t('templates.dataLimit')}</FormLabel>
                        <FormControl>
                          <div className="relative">
                            <Input
                              type="text"
                              inputMode="decimal"
                              placeholder={t('templates.dataLimit')}
                              value={displayValue}
                              onChange={e => {
                                const rawValue = e.target.value.trim()

                                dataLimitInputRef.current = rawValue

                                if (rawValue === '') {
                                  field.onChange(0)
                                  return
                                }

                                const validNumberPattern = /^-?\d*\.?\d*$/
                                if (validNumberPattern.test(rawValue)) {
                                  if (rawValue.endsWith('.') && rawValue.length > 1) {
                                    const prevValue = field.value !== null && field.value !== undefined ? field.value : 0
                                    field.onChange(prevValue)
                                  } else if (rawValue === '.') {
                                    field.onChange(0)
                                  } else {
                                    const numValue = parseFloat(rawValue)
                                    if (!isNaN(numValue) && numValue >= 0) {
                                      field.onChange(numValue)
                                    }
                                  }
                                }
                              }}
                              onBlur={() => {
                                const rawValue = dataLimitInputRef.current.trim()
                                if (rawValue === '' || rawValue === '.' || rawValue === '0') {
                                  dataLimitInputRef.current = ''
                                  field.onChange(0)
                                } else {
                                  const numValue = parseFloat(rawValue)
                                  if (!isNaN(numValue) && numValue >= 0) {
                                    const finalValue = numValue
                                    dataLimitInputRef.current = finalValue > 0 ? String(finalValue) : ''
                                    field.onChange(finalValue)
                                  } else {
                                    dataLimitInputRef.current = ''
                                    field.onChange(0)
                                  }
                                }
                              }}
                              className="pr-10"
                            />
                            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm font-medium text-muted-foreground">{t('userDialog.gb', { defaultValue: 'GB' })}</span>
                          </div>
                        </FormControl>
                        {field.value !== null && field.value !== undefined && field.value > 0 && field.value < 1 && (
                          <p dir='ltr' className="w-full mt-2 text-end text-xs text-muted-foreground">{formatBytes(Math.round(field.value * 1024 * 1024 * 1024))}</p>
                        )}
                        <FormMessage />
                      </FormItem>
                    )
                  }}
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
                    const daySec = 24 * 60 * 60
                    if (
                      expireDurationInputRef.current === '' &&
                      field.value != null &&
                      field.value !== undefined &&
                      field.value > 0
                    ) {
                      expireDurationInputRef.current = String(field.value / daySec)
                    } else if (
                      (field.value === null || field.value === undefined || field.value === 0) &&
                      expireDurationInputRef.current !== '' &&
                      !expireDurationInputRef.current.endsWith('.')
                    ) {
                      expireDurationInputRef.current = ''
                    }

                    const displayValue =
                      expireDurationInputRef.current !== ''
                        ? expireDurationInputRef.current
                        : field.value != null && field.value !== undefined && field.value > 0
                          ? String(field.value / daySec)
                          : ''

                    return (
                      <FormItem className="flex-1">
                        <FormLabel className="text-left">{t('templates.expire')}</FormLabel>
                        <FormControl>
                          <div className="relative" dir="ltr">
                            <Input
                              type="text"
                              inputMode="decimal"
                              placeholder={t('templates.expire')}
                              value={displayValue}
                              onChange={e => {
                                const rawValue = e.target.value.trim()
                                expireDurationInputRef.current = rawValue

                                if (rawValue === '') {
                                  field.onChange(0)
                                  void form.trigger('expire_duration')
                                  return
                                }

                                const validNumberPattern = /^-?\d*\.?\d*$/
                                if (!validNumberPattern.test(rawValue)) return

                                if (rawValue.endsWith('.') && rawValue.length > 1) {
                                  const prevSeconds =
                                    field.value != null && field.value !== undefined ? field.value : 0
                                  field.onChange(prevSeconds)
                                  void form.trigger('expire_duration')
                                } else if (rawValue === '.') {
                                  field.onChange(0)
                                  void form.trigger('expire_duration')
                                } else {
                                  const numValue = parseFloat(rawValue)
                                  if (!isNaN(numValue) && numValue >= 0) {
                                    field.onChange(numValue * daySec)
                                    void form.trigger('expire_duration')
                                  }
                                }
                              }}
                              onBlur={() => {
                                const rawValue = expireDurationInputRef.current.trim()
                                if (rawValue === '' || rawValue === '.' || rawValue === '0') {
                                  expireDurationInputRef.current = ''
                                  field.onChange(0)
                                  void form.trigger('expire_duration')
                                } else {
                                  const numValue = parseFloat(rawValue)
                                  if (!isNaN(numValue) && numValue >= 0) {
                                    const finalDays = numValue
                                    const finalSeconds = finalDays * daySec
                                    expireDurationInputRef.current = finalDays > 0 ? String(finalDays) : ''
                                    field.onChange(finalSeconds)
                                    void form.trigger('expire_duration')
                                  } else {
                                    expireDurationInputRef.current = ''
                                    field.onChange(0)
                                    void form.trigger('expire_duration')
                                  }
                                }
                              }}
                              className={dir === 'rtl' ? 'pl-14' : 'pr-14'}
                            />
                            <span
                              className={`pointer-events-none absolute top-1/2 -translate-y-1/2 text-sm font-medium text-muted-foreground ${dir === 'rtl' ? 'start-3' : 'end-3'}`}
                            >
                              {t('time.days', { defaultValue: 'Days' })}
                            </span>
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
                    <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
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
                  name="on_hold_timeout"
                  render={({ field }) => {
                    const convertToDisplayValue = (value: number | undefined) => {
                      if (value == null || value === 0) return ''
                      switch (timeType) {
                        case 'seconds':
                          return value
                        case 'hours':
                          return value / (60 * 60)
                        case 'days':
                          return value / (24 * 60 * 60)
                        default:
                          return value
                      }
                    }

                    const convertToSeconds = (inputValue: string, type: string) => {
                      const numValue = parseFloat(inputValue)
                      if (isNaN(numValue) || numValue < 0) return undefined
                      switch (type) {
                        case 'seconds':
                          return numValue
                        case 'hours':
                          return numValue * 60 * 60
                        case 'days':
                          return numValue * 24 * 60 * 60
                        default:
                          return numValue
                      }
                    }

                    if (status !== UserStatusCreate.on_hold) {
                      return <></>
                    }
                    return (
                      <FormItem className="flex-1">
                        <FormLabel>{t('templates.onHoldTimeout')}</FormLabel>
                        <FormControl>
                          <div className="flex flex-row overflow-hidden rounded-md border border-border">
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
                            <div className="flex-[2]">
                              <Select value={timeType} onValueChange={v => setTimeType(v as 'seconds' | 'hours' | 'days')}>
                                <SelectTrigger className="w-full rounded-none border-0 focus:ring-0 focus:ring-offset-0">
                                  <SelectValue placeholder={t('time.seconds', { defaultValue: 'Seconds' })} />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="days">{t('time.days', { defaultValue: 'Days' })}</SelectItem>
                                  <SelectItem value="hours">{t('time.hours', { defaultValue: 'Hours' })}</SelectItem>
                                  <SelectItem value="seconds">{t('time.seconds', { defaultValue: 'Seconds' })}</SelectItem>
                                </SelectContent>
                              </Select>
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
            <div className="mt-4 flex justify-end gap-2 ">
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
