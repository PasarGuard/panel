import type { AdminFormValuesInput } from '@/features/admins/forms/admin-form'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { DecimalInput } from '@/components/common/decimal-input'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { PasswordInput } from '@/components/ui/password-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { VariablesPopover } from '@/components/ui/variables-popover'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { cn } from '@/lib/utils'
import { useCreateAdmin, useGetRolesSimple, useModifyAdminById } from '@/service/api'
import type { RoleLimits } from '@/service/api'
import { upsertAdminInAdminsCache } from '@/utils/adminsCache'
import { bytesToFormGigabytes, formatBytes, gbToBytes } from '@/utils/formatByte'
import { useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Pencil, Sliders, UserCog } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

const BUILTIN_ADMIN_ROLES = [
  { id: 2, name: 'administrator', is_owner: false },
  { id: 3, name: 'operator', is_owner: false },
]
const normalizeOverrideValue = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

const normalizePermissionOverrides = (overrides: AdminFormValuesInput['permission_overrides']): RoleLimits => ({
  max_users: normalizeOverrideValue(overrides?.max_users),
  data_limit_min: normalizeOverrideValue(overrides?.data_limit_min),
  data_limit_max: normalizeOverrideValue(overrides?.data_limit_max),
  expire_days_min: normalizeOverrideValue(overrides?.expire_days_min),
  expire_days_max: normalizeOverrideValue(overrides?.expire_days_max),
  min_hwid_per_user: normalizeOverrideValue(overrides?.min_hwid_per_user),
  max_hwid_per_user: normalizeOverrideValue(overrides?.max_hwid_per_user),
})

const normalizeDataLimit = (value: AdminFormValuesInput['data_limit']): number => {
  const normalized = normalizeOverrideValue(value)
  return normalized && normalized > 0 ? normalized : 0
}
const ONE_GB_IN_BYTES = 1024 * 1024 * 1024

interface AdminModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  editingAdmin?: boolean
  editingAdminId?: number | null
  form: UseFormReturn<AdminFormValuesInput>
}

export default function AdminModal({ isDialogOpen, onOpenChange, editingAdminId, editingAdmin, form }: AdminModalProps) {
  const { t } = useTranslation()
  const handleError = useDynamicErrorHandler()
  const queryClient = useQueryClient()
  const addAdminMutation = useCreateAdmin()
  const modifyAdminMutation = useModifyAdminById()
  const rolesQuery = useGetRolesSimple()
  const selectedRoleId = form.watch('role_id')
  const roleOptions = useMemo(() => {
    const rolesById = new Map<number, { id: number; name: string; is_owner: boolean }>()
    BUILTIN_ADMIN_ROLES.forEach(role => rolesById.set(role.id, role))
      ; (rolesQuery.data?.roles || []).forEach(role => {
        if (!role.is_owner && role.id !== 1) {
          rolesById.set(role.id, role)
        }
      })

    return Array.from(rolesById.values()).sort((a, b) => a.id - b.id)
  }, [rolesQuery.data?.roles])
  const selectedRoleExists = selectedRoleId == null || roleOptions.some(role => role.id === selectedRoleId)

  useEffect(() => {
    if (!isDialogOpen) {
      setNotificationExpanded(false)
      setPermissionOverridesExpanded(false)
    }
  }, [isDialogOpen])

  // State for collapsible notification section
  const [notificationExpanded, setNotificationExpanded] = useState(false)
  const [permissionOverridesExpanded, setPermissionOverridesExpanded] = useState(false)

  // Watch notification enable fields
  const watchedNotificationEnable = form.watch('notification_enable')
  const watchedPermissionOverrides = form.watch('permission_overrides')
  const permissionOverridesCount = useMemo(
    () => Object.values(watchedPermissionOverrides || {}).filter(value => value !== null && value !== undefined && value !== '').length,
    [watchedPermissionOverrides],
  )

  // Ensure form is cleared when modal is closed
  const handleClose = (open: boolean) => {
    if (!open) {
      form.reset()
    }
    onOpenChange(open)
  }

  const onSubmit = async (values: AdminFormValuesInput) => {
    try {
      const dataLimitChanged = !!form.formState.dirtyFields.data_limit
      const dataLimitHasValue = values.data_limit !== null && values.data_limit !== undefined && values.data_limit !== ''
      const dataLimitPayload = editingAdmin
        ? dataLimitChanged
          ? { data_limit: normalizeDataLimit(values.data_limit) }
          : {}
        : dataLimitHasValue
          ? { data_limit: normalizeDataLimit(values.data_limit) }
          : {}
      const editData = {
        password: values.password || undefined,
        ...(form.formState.dirtyFields.status ? { status: values.status || 'active' } : {}),
        ...dataLimitPayload,
        discord_webhook: values.discord_webhook,
        sub_domain: values.sub_domain,
        sub_template: values.sub_template,
        support_url: values.support_url,
        telegram_id: values.telegram_id,
        profile_title: values.profile_title,
        note: values.note,
        discord_id: values.discord_id,
        notification_enable: values.notification_enable || null,
        role_id: values.role_id,
        permission_overrides: normalizePermissionOverrides(values.permission_overrides),
      }
      if (editingAdmin && editingAdminId != null) {
        const updatedAdmin = await modifyAdminMutation.mutateAsync({
          adminId: editingAdminId,
          data: editData,
        })
        upsertAdminInAdminsCache(queryClient, updatedAdmin, { allowInsert: true })
        toast.success(
          t('admins.editSuccess', {
            name: values.username,
            defaultValue: 'Admin «{{name}}» has been updated successfully',
          }),
        )
      } else {
        if (!values.password) return
        const createData = {
          username: values.username,
          password: values.password, // Ensure password is present
          status: values.status || 'active',
          ...dataLimitPayload,
          discord_webhook: values.discord_webhook,
          sub_domain: values.sub_domain,
          sub_template: values.sub_template,
          support_url: values.support_url,
          telegram_id: values.telegram_id,
          profile_title: values.profile_title,
          note: values.note,
          discord_id: values.discord_id,
          notification_enable: values.notification_enable || null,
          role_id: values.role_id,
          permission_overrides: normalizePermissionOverrides(values.permission_overrides),
        }
        const createdAdmin = await addAdminMutation.mutateAsync({
          data: createData,
        })
        upsertAdminInAdminsCache(queryClient, createdAdmin, { allowInsert: true })
        toast.success(
          t('admins.createSuccess', {
            name: values.username,
            defaultValue: 'Admin «{{name}}» has been created successfully',
          }),
        )
      }
      onOpenChange(false)
      form.reset()
    } catch (error: any) {
      const fields = [
        'username',
        'password',
        'passwordConfirm',
        'role_id',
        'status',
        'data_limit',
        'discord_webhook',
        'sub_domain',
        'sub_template',
        'support_url',
        'telegram_id',
        'profile_title',
        'note',
        'discord_id',
        'permission_overrides',
      ]
      handleError({ error, fields, form, contextKey: 'admins' })
    }
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleClose}>
      <DialogContent className="h-auto max-w-[750px]" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingAdmin ? <Pencil className="h-5 w-5" /> : <UserCog className="h-5 w-5" />}
            <span>{editingAdmin ? t('admins.editAdmin') : t('admins.createAdmin')}</span>
          </DialogTitle>
          <DialogDescription className="sr-only">{t('admins.description', { defaultValue: 'Configure admin account settings.' })}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" autoComplete="off">
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="grid grid-cols-1 items-stretch gap-4 pb-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="username"
                  render={({ field }) => {
                    const hasError = !!form.formState.errors.username
                    return (
                      <FormItem>
                        <FormLabel>{t('admins.username')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('admins.enterUsername')} disabled={editingAdmin} isError={hasError} autoComplete="off" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name="role_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.role')}</FormLabel>
                      <Select value={field.value?.toString() || '3'} onValueChange={value => field.onChange(Number(value))}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={t('admins.role')} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {!selectedRoleExists && selectedRoleId != null && (
                            <SelectItem value={String(selectedRoleId)} disabled>
                              {t('adminRoles.currentRoleUnavailable', { defaultValue: 'Current role unavailable' })}
                            </SelectItem>
                          )}
                          {roleOptions.map(role => (
                            <SelectItem key={role.id} value={role.id.toString()}>
                              {t(`adminRoles.names.${role.name}`, { defaultValue: role.name })}
                            </SelectItem>
                          ))}
                          {rolesQuery.isLoading && <SelectItem value="loading" disabled>{t('loading', { defaultValue: 'Loading...' })}</SelectItem>}
                          {rolesQuery.isError && <SelectItem value="roles-error" disabled>{t('adminRoles.loadFallback', { defaultValue: 'Using built-in roles' })}</SelectItem>}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('status', { defaultValue: 'Status' })}</FormLabel>
                      <Select value={field.value || 'active'} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={t('status', { defaultValue: 'Status' })} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="active">{t('status.active', { defaultValue: 'Active' })}</SelectItem>
                          <SelectItem value="disabled">{t('status.disabled', { defaultValue: 'Disabled' })}</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <AdminDataLimitField form={form} />
                <FormField
                  control={form.control}
                  name="password"
                  render={({ field }) => {
                    const hasError = !!form.formState.errors.password
                    return (
                      <FormItem>
                        <FormLabel>{t('admins.password')}</FormLabel>
                        <FormControl>
                          <PasswordInput placeholder={t('admins.enterPassword')} isError={hasError} autoComplete="new-password" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name="passwordConfirm"
                  render={({ field }) => {
                    const hasError = !!form.formState.errors.passwordConfirm
                    return (
                      <FormItem>
                        <FormLabel>{t('admins.passwordConfirm')}</FormLabel>
                        <FormControl>
                          <PasswordInput placeholder={t('admins.enterPasswordConfirm')} isError={hasError} autoComplete="new-password" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name={'telegram_id'}
                  render={({ field }) => {
                    return (
                      <FormItem>
                        <FormLabel>{t('admins.telegramId')}</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder={t('Telegram ID (e.g. 36548974)')}
                            autoComplete="off"
                            onChange={e => {
                              const value = e.target.value
                              field.onChange(value ? parseInt(value) : 0)
                            }}
                            value={field.value ? field.value : ''}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name={'discord_id'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.discordId')}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder={t('admins.discordId')}
                          autoComplete="off"
                          onChange={e => {
                            const value = e.target.value
                            field.onChange(value ? parseInt(value) : 0)
                          }}
                          value={field.value ? field.value : ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'discord_webhook'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.discord')}</FormLabel>
                      <FormControl>
                        <Input placeholder={t('admins.discord')} autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'support_url'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.supportUrl')}</FormLabel>
                      <FormControl>
                        <Input placeholder={t('admins.supportUrl')} autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'profile_title'}
                  render={({ field }) => (
                    <FormItem>
                      <div className="flex items-center gap-2">
                        <FormLabel>{t('admins.profile')}</FormLabel>
                        <VariablesPopover />
                      </div>
                      <FormControl>
                        <Input placeholder={t('admins.profile')} autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'sub_domain'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.subDomain')}</FormLabel>
                      <FormControl>
                        <Input placeholder={t('admins.subDomain')} autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'sub_template'}
                  render={({ field }) => (
                    <FormItem className="sm:col-span-2">
                      <FormLabel>{t('admins.subTemplate')}</FormLabel>
                      <FormControl>
                        <Input placeholder={t('admins.subTemplate')} autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'note'}
                  render={({ field }) => (
                    <FormItem className="sm:col-span-2">
                      <FormLabel>{t('fields.note')}</FormLabel>
                      <FormControl>
                        <Textarea placeholder={t('fields.note')} rows={4} autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="flex flex-col gap-4 mb-2">
                <Collapsible open={notificationExpanded} onOpenChange={setNotificationExpanded}>
                  <div
                    className={cn(
                      'group rounded-md border transition-all duration-200 ease-in-out',
                      notificationExpanded && 'border-primary/50 bg-accent/30',
                    )}
                  >
                    <div className="flex w-full items-center justify-between p-4 transition-colors">
                      <CollapsibleTrigger asChild>
                        <div
                          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation()
                          }}
                        >
                          <UserCog className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <button
                            type="button"
                            className={cn('shrink-0 rounded-sm p-1 text-muted-foreground transition-all duration-200 hover:text-foreground', notificationExpanded && 'rotate-180')}
                            onClick={e => {
                              e.stopPropagation()
                              setNotificationExpanded(!notificationExpanded)
                            }}
                          >
                            <ChevronDown className="h-3.5 w-3.5" />
                          </button>
                          <FormLabel
                            className="flex-1 cursor-pointer truncate text-sm font-medium sm:text-base"
                            onClick={(e: React.MouseEvent) => {
                              e.preventDefault()
                              e.stopPropagation()
                              setNotificationExpanded(!notificationExpanded)
                            }}
                          >
                            {t('settings.notifications.filterTitle')}
                            {(() => {
                              const enabledCount = watchedNotificationEnable ? Object.values(watchedNotificationEnable).filter(Boolean).length : 0
                              const totalCount = 7
                              return (
                                <span className="mx-1.5 text-xs text-muted-foreground">
                                  {enabledCount}/{totalCount}
                                </span>
                              )
                            })()}
                          </FormLabel>
                        </div>
                      </CollapsibleTrigger>
                      <FormControl>
                        <Switch
                          checked={watchedNotificationEnable ? Object.values(watchedNotificationEnable).some(Boolean) : false}
                          onCheckedChange={checked => {
                            // Toggle all notification permissions
                            form.setValue('notification_enable', {
                              create: checked,
                              modify: checked,
                              delete: checked,
                              status_change: checked,
                              reset_data_usage: checked,
                              data_reset_by_next: checked,
                              subscription_revoked: checked,
                            })
                          }}
                          onClick={e => e.stopPropagation()}
                          className="shrink-0"
                        />
                      </FormControl>
                    </div>

                    <CollapsibleContent className="data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down overflow-hidden transition-all duration-200 ease-in-out">
                      <div className="space-y-1 border-t bg-muted/30 px-3 py-2">
                        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                          <FormField
                            control={form.control}
                            name="notification_enable.create"
                            render={({ field }) => (
                              <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                <FormControl>
                                  <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                                </FormControl>
                                <FormLabel className="cursor-pointer text-xs font-normal leading-none">{t('settings.notifications.subPermissions.create')}</FormLabel>
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="notification_enable.modify"
                            render={({ field }) => (
                              <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                <FormControl>
                                  <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                                </FormControl>
                                <FormLabel className="cursor-pointer text-xs font-normal leading-none">{t('settings.notifications.subPermissions.modify')}</FormLabel>
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="notification_enable.delete"
                            render={({ field }) => (
                              <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                <FormControl>
                                  <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                                </FormControl>
                                <FormLabel className="cursor-pointer text-xs font-normal leading-none">{t('settings.notifications.subPermissions.delete')}</FormLabel>
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="notification_enable.status_change"
                            render={({ field }) => (
                              <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                <FormControl>
                                  <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                                </FormControl>
                                <FormLabel className="cursor-pointer text-xs font-normal leading-none">{t('settings.notifications.subPermissions.statusChange')}</FormLabel>
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="notification_enable.reset_data_usage"
                            render={({ field }) => (
                              <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                <FormControl>
                                  <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                                </FormControl>
                                <FormLabel className="cursor-pointer text-xs font-normal leading-none">{t('settings.notifications.subPermissions.resetDataUsage')}</FormLabel>
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="notification_enable.data_reset_by_next"
                            render={({ field }) => (
                              <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                <FormControl>
                                  <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                                </FormControl>
                                <FormLabel className="cursor-pointer text-xs font-normal leading-none">{t('settings.notifications.subPermissions.dataResetByNext')}</FormLabel>
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="notification_enable.subscription_revoked"
                            render={({ field }) => (
                              <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                <FormControl>
                                  <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                                </FormControl>
                                <FormLabel className="cursor-pointer text-xs font-normal leading-none">{t('settings.notifications.subPermissions.subscriptionRevoked')}</FormLabel>
                              </FormItem>
                            )}
                          />
                        </div>
                      </div>
                    </CollapsibleContent>
                  </div>
                </Collapsible>

                <Collapsible open={permissionOverridesExpanded} onOpenChange={setPermissionOverridesExpanded}>
                  <div className="group rounded-md border transition-all duration-200 ease-in-out">
                    <CollapsibleTrigger asChild>
                      <button type="button" className="flex w-full items-center justify-between gap-3 p-4 text-left transition-colors hover:bg-muted/40">
                        <div className="flex min-w-0 items-center gap-2">
                          <Sliders className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span className="truncate text-sm font-medium sm:text-base">
                            {t('admins.permissionOverrides', { defaultValue: 'Permission overrides' })}
                            <span className="mx-1.5 text-xs text-muted-foreground">
                              {permissionOverridesCount}/7
                            </span>
                          </span>
                        </div>
                        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200', permissionOverridesExpanded && 'rotate-180')} />
                      </button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down overflow-hidden transition-all duration-200 ease-in-out">
                      <div className="space-y-3 border-t p-3">
                        <p className="text-xs text-muted-foreground">
                          {t('admins.permissionOverridesHint', { defaultValue: 'Leave empty to inherit limits from the selected role. Set to 0 to disable.' })}
                        </p>
                        <PermissionOverridesFields form={form} />
                      </div>
                    </CollapsibleContent>
                  </div>
                </Collapsible>

              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit" isLoading={addAdminMutation.isPending || modifyAdminMutation.isPending} loadingText={editingAdmin ? t('modifying') : t('creating')}>
                {editingAdmin ? t('modify') : t('create')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

type AdminForm = UseFormReturn<AdminFormValuesInput>

function PermissionOverridesFields({ form }: { form: AdminForm }) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <FormField
        control={form.control}
        name="permission_overrides.max_users"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('adminRoles.limitFields.max_users', { defaultValue: 'Max users' })}</FormLabel>
            <FormControl>
              <DecimalInput
                placeholder={t('adminRoles.unlimited', { defaultValue: 'Unlimited' })}
                value={typeof field.value === 'number' ? field.value : null}
                emptyValue={null as any}
                zeroValue={0}
                onValueChange={value => field.onChange(value ?? null)}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <BytesLimitField form={form} name="permission_overrides.data_limit_min" labelKey="adminRoles.limitFields.data_limit_min" />
        <BytesLimitField form={form} name="permission_overrides.data_limit_max" labelKey="adminRoles.limitFields.data_limit_max" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <NumberLimitField form={form} name="permission_overrides.expire_days_min" labelKey="adminRoles.limitFields.expire_days_min" />
        <NumberLimitField form={form} name="permission_overrides.expire_days_max" labelKey="adminRoles.limitFields.expire_days_max" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <NumberLimitField form={form} name="permission_overrides.min_hwid_per_user" labelKey="adminRoles.limitFields.min_hwid_per_user" />
        <NumberLimitField form={form} name="permission_overrides.max_hwid_per_user" labelKey="adminRoles.limitFields.max_hwid_per_user" />
      </div>
    </div>
  )
}

function AdminDataLimitField({ form }: { form: AdminForm }) {
  const { t } = useTranslation()

  return (
    <FormField
      control={form.control}
      name="data_limit"
      render={({ field }) => {
        const numericValue = typeof field.value === 'number' ? field.value : null
        return (
          <FormItem className="relative">
            <FormLabel>{t('admins.dataLimit', { defaultValue: 'Admin data limit' })}</FormLabel>
            <FormControl>
              <div className="relative">
                <DecimalInput
                  placeholder={t('adminRoles.unlimited', { defaultValue: 'Unlimited' })}
                  value={numericValue == null ? null : bytesToFormGigabytes(numericValue)}
                  onValueChange={value => {
                    if (value == null) {
                      field.onChange(null)
                      return
                    }
                    field.onChange(gbToBytes(value))
                  }}
                  emptyValue={undefined}
                  className="pr-10"
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-muted-foreground">
                  {t('userDialog.gb', { defaultValue: 'GB' })}
                </span>
              </div>
            </FormControl>
            {numericValue != null && numericValue > 0 && numericValue < ONE_GB_IN_BYTES && (
              <p dir="ltr" className="mt-1 w-full text-end text-[11px] text-muted-foreground">
                {formatBytes(numericValue)}
              </p>
            )}
            <FormMessage />
          </FormItem>
        )
      }}
    />
  )
}

function NumberLimitField({ form, name, labelKey }: { form: AdminForm; name: any; labelKey: string }) {
  const { t } = useTranslation()
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel className="text-xs">{t(labelKey)}</FormLabel>
          <FormControl>
            <DecimalInput
              placeholder={t('adminRoles.unlimited', { defaultValue: 'Unlimited' })}
              value={typeof field.value === 'number' ? field.value : null}
              emptyValue={null as any}
              zeroValue={0}
              onValueChange={value => field.onChange(value ?? null)}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  )
}

function BytesLimitField({ form, name, labelKey }: { form: AdminForm; name: any; labelKey: string }) {
  const { t } = useTranslation()
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => {
        const numericValue = typeof field.value === 'number' ? field.value : null
        return (
          <FormItem className="relative">
            <FormLabel className="text-xs">{t(labelKey)}</FormLabel>
            <FormControl>
              <div className="relative">
                <DecimalInput
                  placeholder={t('adminRoles.unlimited', { defaultValue: 'Unlimited' })}
                  value={numericValue == null ? null : bytesToFormGigabytes(numericValue)}
                  onValueChange={value => {
                    if (value == null) {
                      field.onChange(null)
                      return
                    }
                    field.onChange(gbToBytes(value))
                  }}
                  emptyValue={undefined}
                  className="pr-10"
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-muted-foreground">
                  {t('userDialog.gb', { defaultValue: 'GB' })}
                </span>
              </div>
            </FormControl>
            {numericValue != null && numericValue > 0 && numericValue < ONE_GB_IN_BYTES && (
              <p dir="ltr" className="mt-1 w-full text-end text-[11px] text-muted-foreground">
                {formatBytes(numericValue)}
              </p>
            )}
            <FormMessage />
          </FormItem>
        )
      }}
    />
  )
}
