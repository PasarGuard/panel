import GroupsSelector from '@/components/common/groups-selector'
import { Button } from '@/components/ui/button.tsx'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog.tsx'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form.tsx'
import { Input } from '@/components/ui/input.tsx'
import { LoaderButton } from '@/components/ui/loader-button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select.tsx'
import { Switch } from '@/components/ui/switch.tsx'
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
import { queryClient } from '@/utils/query-client.ts'
import React, { useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ChevronDown, FileText } from 'lucide-react'
import type { UserTemplatesFromValueInput } from '@/components/forms/user-template-form'

interface UserTemplatesModalprops {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<UserTemplatesFromValueInput>
  editingUserTemplate: boolean
  editingUserTemplateId?: number
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
          if (React.isValidElement(child) && child.props.value) {
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

const StatusSelectItem = ({ value, children, onSelect }: { value: string; children: React.ReactNode; onSelect?: (value: string) => void }) => {
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
  const { t } = useTranslation()
  const addUserTemplateMutation = useCreateUserTemplate()
  const handleError = useDynamicErrorHandler()
  const modifyUserTemplateMutation = useModifyUserTemplate()
  const [timeType, setTimeType] = useState<'seconds' | 'hours' | 'days'>('seconds')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!isDialogOpen) return
    queryClient.invalidateQueries({
      queryKey: getGetGroupsSimpleQueryKey({ all: true }),
    })
  }, [isDialogOpen])

  const onSubmit = async (values: UserTemplatesFromValueInput) => {
    setLoading(true)
    try {
      const status = values.status ?? UserStatusCreate.active
      // Build payload according to UserTemplateCreate interface
      const submitData = {
        name: values.name,
        data_limit: values.data_limit,
        expire_duration: values.expire_duration,
        username_prefix: values.username_prefix || '',
        username_suffix: values.username_suffix || '',
        group_ids: values.groups, // map groups to group_ids
        status,
        on_hold_timeout: status === UserStatusCreate.on_hold ? values.on_hold_timeout : undefined,
        data_limit_reset_strategy: values.data_limit ? values.data_limit_reset_strategy : undefined,
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
      <DialogContent className="h-full max-w-[1000px] sm:h-auto" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            <span>{editingUserTemplate ? t('editUserTemplateModal.title') : t('userTemplateModal.title')}</span>
          </DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col">
            <div className="-mr-4 flex max-h-[76dvh] flex-col items-start gap-4 overflow-y-auto px-2 pb-6 pr-4 sm:max-h-[75dvh] sm:flex-row">
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

                <FormField
                  control={form.control}
                  name="data_limit"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel>{t('templates.dataLimit')}</FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Input
                            type="number"
                            placeholder={t('templates.dataLimit')}
                            {...field}
                            onChange={e => {
                              const value = parseInt(e.target.value)
                              // Convert GB to bytes (1 GB = 1024 * 1024 * 1024 bytes)
                              field.onChange(value ? value * 1024 * 1024 * 1024 : 0)
                            }}
                            value={field.value ? Math.round(field.value / (1024 * 1024 * 1024)) : ''}
                            className="pr-10"
                            min="0"
                          />
                          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm font-medium text-muted-foreground">{t('userDialog.gb', { defaultValue: 'GB' })}</span>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="data_limit_reset_strategy"
                  render={({ field }) => {
                    // Only show if data_limit is set
                    const datalimit = form.watch('data_limit')
                    if (!datalimit) {
                      return <></>
                    }
                    return (
                      <FormItem className="flex-1">
                        <FormLabel>{t('templates.userDataLimitStrategy')}</FormLabel>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
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
                  name="expire_duration"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel>{t('templates.expire')}</FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Input
                            type="number"
                            placeholder={t('templates.expire')}
                            {...field}
                            onChange={e => {
                              const value = parseInt(e.target.value)
                              field.onChange(value ? value * 24 * 60 * 60 : 0)
                            }}
                            value={field.value ? Math.round(field.value / (24 * 60 * 60)) : ''}
                            className="pr-14"
                            min="0"
                          />
                          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm font-medium text-muted-foreground">{t('time.days', { defaultValue: 'Days' })}</span>
                        </div>
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
                      if (!value) return ''
                      switch (timeType) {
                        case 'seconds':
                          return value
                        case 'hours':
                          return Math.round(value / 60 / 60)
                        case 'days':
                          return Math.round(value / 60 / 60 / 24)
                        default:
                          return value
                      }
                    }

                    const convertToSeconds = (inputValue: string, type: string) => {
                      const numValue = parseInt(inputValue)
                      if (isNaN(numValue)) return undefined
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

                    // Only show if status is on_hold
                    const status = form.watch('status')
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
                              <Select value={timeType} onValueChange={v => setTimeType(v as any)}>
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
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField control={form.control} name="groups" render={({ field }) => <GroupsSelector control={form.control} name="groups" onGroupsChange={field.onChange} />} />
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2 pt-4">
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

