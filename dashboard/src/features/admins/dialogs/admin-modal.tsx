import type { AdminFormValuesInput } from '@/features/admins/forms/admin-form'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { DecimalInput } from '@/components/common/decimal-input'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { PasswordInput } from '@/components/ui/password-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { CustomVariablesPopover, normalizeCustomVariableKey, VariablesPopover } from '@/components/ui/variables-popover'
import { useAdmin } from '@/hooks/use-admin'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { useCreateAdmin, useGetRolesSimple, useModifyAdminById } from '@/service/api'
import type { RoleLimits } from '@/service/api'
import { builtInVariableKeys } from '@/features/subscriptions/components/subscription-settings-schema'
import { upsertAdminInAdminsCache } from '@/utils/adminsCache'
import { removeAuthToken } from '@/utils/authStorage'
import { bytesToFormGigabytes, formatBytes, gbToBytes } from '@/utils/formatByte'
import { useQueryClient } from '@tanstack/react-query'
import { Bell, IdCard, Pencil, Plus, Sliders, Trash2, UserCog } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { UseFormReturn, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
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

const SECONDS_PER_DAY = 86_400

const normalizePermissionOverrides = (overrides: AdminFormValuesInput['permission_overrides']): RoleLimits => {
  const minDays = normalizeOverrideValue(overrides?.expire_days_min)
  const maxDays = normalizeOverrideValue(overrides?.expire_days_max)
  const minTimeoutDays = normalizeOverrideValue(overrides?.on_hold_timeout_days_min)
  const maxTimeoutDays = normalizeOverrideValue(overrides?.on_hold_timeout_days_max)
  return {
    max_users: normalizeOverrideValue(overrides?.max_users),
    data_limit_min: normalizeOverrideValue(overrides?.data_limit_min),
    data_limit_max: normalizeOverrideValue(overrides?.data_limit_max),
    expire_min: minDays === null ? null : Math.round(minDays * SECONDS_PER_DAY),
    expire_max: maxDays === null ? null : Math.round(maxDays * SECONDS_PER_DAY),
    min_hwid_per_user: normalizeOverrideValue(overrides?.min_hwid_per_user),
    max_hwid_per_user: normalizeOverrideValue(overrides?.max_hwid_per_user),
    on_hold_timeout_min: minTimeoutDays === null ? null : Math.round(minTimeoutDays * SECONDS_PER_DAY),
    on_hold_timeout_max: maxTimeoutDays === null ? null : Math.round(maxTimeoutDays * SECONDS_PER_DAY),
  }
}

const normalizeDataLimit = (value: AdminFormValuesInput['data_limit']): number => {
  const normalized = normalizeOverrideValue(value)
  return normalized && normalized > 0 ? normalized : 0
}
const ONE_GB_IN_BYTES = 1024 * 1024 * 1024

const nextCustomVariableKey = (variables: NonNullable<AdminFormValuesInput['custom_variables']>) => {
  let index = variables.length + 1
  let key = `CUSTOM_${index}`
  const usedKeys = new Set(variables.map(variable => variable.key))
  while (usedKeys.has(key)) {
    index += 1
    key = `CUSTOM_${index}`
  }
  return key
}

interface AdminModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  editingAdmin?: boolean
  editingAdminId?: number | null
  form: UseFormReturn<AdminFormValuesInput>
}

export default function AdminModal({ isDialogOpen, onOpenChange, editingAdminId, editingAdmin, form }: AdminModalProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const handleError = useDynamicErrorHandler()
  const queryClient = useQueryClient()
  const { admin: currentAdmin } = useAdmin()
  const addAdminMutation = useCreateAdmin()
  const modifyAdminMutation = useModifyAdminById()
  const rolesQuery = useGetRolesSimple()
  const selectedRoleId = form.watch('role_id')
  const customVariables = form.watch('custom_variables') || []
  const builtInKeys = new Set<string>(builtInVariableKeys)
  const roleOptions = useMemo(() => {
    const rolesById = new Map<number, { id: number; name: string; is_owner: boolean }>()
    BUILTIN_ADMIN_ROLES.forEach(role => rolesById.set(role.id, role))
    ;(rolesQuery.data?.roles || []).forEach(role => {
      if (!role.is_owner && role.id !== 1) {
        rolesById.set(role.id, role)
      }
    })

    return Array.from(rolesById.values()).sort((a, b) => a.id - b.id)
  }, [rolesQuery.data?.roles])
  const selectedRoleExists = selectedRoleId == null || roleOptions.some(role => role.id === selectedRoleId)

  useEffect(() => {
    if (!isDialogOpen) {
      setOpenSection(undefined)
    }
  }, [isDialogOpen])

  // Accordion: only one section open at a time
  const [openSection, setOpenSection] = useState<string | undefined>(undefined)

  // Watch notification enable fields
  const watchedNotificationEnable = useWatch({ control: form.control, name: 'notification_enable' })
  const watchedPermissionOverrides = useWatch({ control: form.control, name: 'permission_overrides' })
  const NOTIFICATION_KEYS = ['create', 'modify', 'delete', 'status_change', 'reset_data_usage', 'data_reset_by_next', 'subscription_revoked'] as const
  const notificationEnabledCount = useMemo(() => NOTIFICATION_KEYS.reduce((sum, key) => sum + ((watchedNotificationEnable as any)?.[key] ? 1 : 0), 0), [watchedNotificationEnable])
  const allNotificationsEnabled = notificationEnabledCount === NOTIFICATION_KEYS.length
  const permissionOverridesCount = useMemo(
    () => Object.values(watchedPermissionOverrides || {}).filter(value => value !== null && value !== undefined && value !== '').length,
    [watchedPermissionOverrides],
  )

  const handleAccordionChange = (value: string) => {
    setOpenSection(prev => (prev === value ? undefined : value))
  }

  const setCustomVariables = (variables: NonNullable<AdminFormValuesInput['custom_variables']>) => {
    form.setValue('custom_variables', variables, {
      shouldDirty: true,
      shouldTouch: true,
      shouldValidate: true,
    })
  }

  const addCustomVariable = () => {
    setCustomVariables([...customVariables, { key: nextCustomVariableKey(customVariables), value: '' }])
  }

  const updateCustomVariable = (index: number, patch: Partial<NonNullable<AdminFormValuesInput['custom_variables']>[number]>) => {
    setCustomVariables(customVariables.map((variable, variableIndex) => (variableIndex === index ? { ...variable, ...patch } : variable)))
  }

  const removeCustomVariable = (index: number) => {
    setCustomVariables(customVariables.filter((_, variableIndex) => variableIndex !== index))
  }

  // Ensure form is cleared when modal is closed
  const handleClose = (open: boolean) => {
    if (!open) {
      form.reset()
    }
    onOpenChange(open)
  }

  const onSubmit = async (values: AdminFormValuesInput) => {
    try {
      const passwordChanged = typeof values.password === 'string' && values.password.length > 0
      const isEditingCurrentAdmin = editingAdmin && currentAdmin != null && ((currentAdmin.id != null && editingAdminId === currentAdmin.id) || values.username === currentAdmin.username)
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
        custom_variables: values.custom_variables || [],
        note: values.note,
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
        if (passwordChanged && isEditingCurrentAdmin) {
          toast.success(t('admins.passwordChangedTitle', { defaultValue: 'Password changed' }), {
            description: t('admins.passwordChangedLogout', { defaultValue: 'Please sign in again with your new password.' }),
          })
          onOpenChange(false)
          form.reset()
          await queryClient.cancelQueries()
          removeAuthToken()
          queryClient.clear()
          navigate('/login', { replace: true })
          return
        }
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
          custom_variables: values.custom_variables || [],
          note: values.note,
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
        'custom_variables',
        'note',
        'permission_overrides',
      ]
      handleError({ error, fields, form, contextKey: 'admins' })
    }
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleClose}>
      <DialogContent className="h-auto max-w-[640px]" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingAdmin ? <Pencil className="h-5 w-5" /> : <UserCog className="h-5 w-5" />}
            <span>{editingAdmin ? t('admins.editAdmin') : t('admins.createAdmin')}</span>
          </DialogTitle>
          <DialogDescription className="sr-only">{t('admins.description', { defaultValue: 'Configure admin account settings.' })}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" autoComplete="off">
            <div className="-mr-4 max-h-[75dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[70dvh]">
              {/* Essentials: always visible */}
              <div className="grid grid-cols-1 items-stretch gap-4 sm:grid-cols-2">
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
                  render={({ field }) => {
                    const isOwnerAdmin = editingAdmin && selectedRoleId === 1
                    return (
                      <FormItem>
                        <FormLabel>{t('admins.role')}</FormLabel>
                        <Select value={field.value?.toString() || '3'} onValueChange={value => field.onChange(Number(value))} disabled={isOwnerAdmin}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('admins.role')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {isOwnerAdmin && (
                              <SelectItem value="1" disabled>
                                {t('adminRoles.names.owner', { defaultValue: 'Owner' })}
                              </SelectItem>
                            )}
                            {!selectedRoleExists && !isOwnerAdmin && selectedRoleId != null && (
                              <SelectItem value={String(selectedRoleId)} disabled>
                                {t('adminRoles.currentRoleUnavailable', { defaultValue: 'Current role unavailable' })}
                              </SelectItem>
                            )}
                            {roleOptions.map(role => (
                              <SelectItem key={role.id} value={role.id.toString()}>
                                {t(`adminRoles.names.${role.name}`, { defaultValue: role.name })}
                              </SelectItem>
                            ))}
                            {rolesQuery.isLoading && (
                              <SelectItem value="loading" disabled>
                                {t('loading', { defaultValue: 'Loading...' })}
                              </SelectItem>
                            )}
                            {rolesQuery.isError && (
                              <SelectItem value="roles-error" disabled>
                                {t('adminRoles.loadFallback', { defaultValue: 'Using built-in roles' })}
                              </SelectItem>
                            )}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
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
                          {editingAdmin && <SelectItem value="disabled">{t('status.disabled', { defaultValue: 'Disabled' })}</SelectItem>}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <AdminDataLimitField form={form} />
              </div>

              {/* Advanced settings: collapsed by default */}
              <Accordion type="single" collapsible value={openSection} onValueChange={handleAccordionChange} className="!mt-0 flex w-full flex-col gap-y-3">
                <AccordionItem className="rounded-md border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="profile">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <IdCard className="h-4 w-4" />
                      <span>{t('admins.profileSection', { defaultValue: 'Profile & contact' })}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <div className="grid grid-cols-1 gap-4 pb-2 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="telegram_id"
                        render={({ field }) => (
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
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="discord_webhook"
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
                        name="support_url"
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
                        name="profile_title"
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
                        name="sub_domain"
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
                        name="sub_template"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>{t('admins.subTemplate')}</FormLabel>
                            <FormControl>
                              <Input placeholder={t('admins.subTemplate')} autoComplete="off" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <div className="space-y-3 sm:col-span-2">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 flex-1 space-y-1">
                            <div className="flex items-center gap-1.5">
                              <FormLabel>{t('admins.customVariables.title', { defaultValue: 'Custom Variables' })}</FormLabel>
                              <CustomVariablesPopover customVariables={customVariables} />
                            </div>
                            <p className="text-muted-foreground text-xs">
                              {t('admins.customVariables.description', {
                                defaultValue: 'Override global custom variables for users owned by this admin.',
                              })}
                            </p>
                          </div>
                          <Button type="button" variant="outline" size="sm" onClick={addCustomVariable}>
                            <Plus className="mr-1.5 h-3.5 w-3.5" />
                            {t('admins.customVariables.addVariable', { defaultValue: 'Add Variable' })}
                          </Button>
                        </div>
                        <div className="space-y-2">
                          {customVariables.length > 0 ? (
                            customVariables.map((variable, index) => {
                              const duplicate = customVariables.some((candidate, candidateIndex) => candidateIndex !== index && candidate.key === variable.key)
                              const conflictsWithBuiltIn = builtInKeys.has(variable.key)
                              const hasKeyError = duplicate || conflictsWithBuiltIn
                              return (
                                <div key={`admin-custom-variable-${index}`} className="bg-card/50 space-y-2 rounded-lg border p-3">
                                  <div className="flex flex-col gap-2 sm:flex-row">
                                    <div className="min-w-0 flex-1 space-y-1">
                                      <Input
                                        value={variable.key}
                                        onChange={event => updateCustomVariable(index, { key: normalizeCustomVariableKey(event.target.value) })}
                                        placeholder="CUSTOM_HOST"
                                        className="font-mono text-xs"
                                        aria-invalid={hasKeyError}
                                      />
                                      {hasKeyError ? (
                                        <p className="text-destructive text-xs">
                                          {duplicate
                                            ? t('admins.customVariables.duplicateKey', { defaultValue: 'Duplicate custom variable key.' })
                                            : t('admins.customVariables.builtinConflict', { defaultValue: 'This key is reserved for a built-in variable.' })}
                                        </p>
                                      ) : null}
                                    </div>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="icon"
                                      className="text-destructive hover:bg-destructive/10 h-8 w-8 shrink-0"
                                      onClick={() => removeCustomVariable(index)}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </div>
                                  <Textarea
                                    value={variable.value}
                                    onChange={event => updateCustomVariable(index, { value: event.target.value })}
                                    placeholder="{USERNAME}.example.com"
                                    className="min-h-[60px] resize-none font-mono text-xs"
                                    rows={2}
                                  />
                                </div>
                              )
                            })
                          ) : (
                            <div className="border-border/70 rounded-lg border border-dashed px-4 py-6 text-center">
                              <p className="text-muted-foreground text-sm">{t('admins.customVariables.empty', { defaultValue: 'No custom variables configured.' })}</p>
                            </div>
                          )}
                        </div>
                      </div>
                      <FormField
                        control={form.control}
                        name="note"
                        render={({ field }) => (
                          <FormItem className="sm:col-span-2">
                            <FormLabel>{t('fields.note')}</FormLabel>
                            <FormControl>
                              <Textarea placeholder={t('fields.note')} rows={3} autoComplete="off" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-md border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="notifications">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Bell className="h-4 w-4" />
                      <span>{t('settings.notifications.filterTitle')}</span>
                      <span className="text-muted-foreground text-xs">{notificationEnabledCount}/7</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <div className="bg-muted/30 flex items-center justify-between gap-3 rounded-md px-3 py-2">
                      <span className="text-muted-foreground text-xs">{t('settings.notifications.toggleAll', { defaultValue: 'Toggle all notifications' })}</span>
                      <Switch
                        checked={allNotificationsEnabled}
                        onCheckedChange={checked => {
                          form.setValue(
                            'notification_enable',
                            {
                              create: checked,
                              modify: checked,
                              delete: checked,
                              status_change: checked,
                              reset_data_usage: checked,
                              data_reset_by_next: checked,
                              subscription_revoked: checked,
                            },
                            { shouldDirty: true },
                          )
                        }}
                        className="shrink-0"
                      />
                    </div>
                    <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="notification_enable.create"
                        render={({ field }) => (
                          <FormItem className="hover:bg-muted/40 flex items-center space-y-0 gap-x-2 rounded-sm px-2 py-1.5 transition-colors">
                            <FormControl>
                              <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                            </FormControl>
                            <FormLabel className="cursor-pointer text-xs leading-none font-normal">{t('settings.notifications.subPermissions.create')}</FormLabel>
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="notification_enable.modify"
                        render={({ field }) => (
                          <FormItem className="hover:bg-muted/40 flex items-center space-y-0 gap-x-2 rounded-sm px-2 py-1.5 transition-colors">
                            <FormControl>
                              <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                            </FormControl>
                            <FormLabel className="cursor-pointer text-xs leading-none font-normal">{t('settings.notifications.subPermissions.modify')}</FormLabel>
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="notification_enable.delete"
                        render={({ field }) => (
                          <FormItem className="hover:bg-muted/40 flex items-center space-y-0 gap-x-2 rounded-sm px-2 py-1.5 transition-colors">
                            <FormControl>
                              <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                            </FormControl>
                            <FormLabel className="cursor-pointer text-xs leading-none font-normal">{t('settings.notifications.subPermissions.delete')}</FormLabel>
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="notification_enable.status_change"
                        render={({ field }) => (
                          <FormItem className="hover:bg-muted/40 flex items-center space-y-0 gap-x-2 rounded-sm px-2 py-1.5 transition-colors">
                            <FormControl>
                              <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                            </FormControl>
                            <FormLabel className="cursor-pointer text-xs leading-none font-normal">{t('settings.notifications.subPermissions.statusChange')}</FormLabel>
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="notification_enable.reset_data_usage"
                        render={({ field }) => (
                          <FormItem className="hover:bg-muted/40 flex items-center space-y-0 gap-x-2 rounded-sm px-2 py-1.5 transition-colors">
                            <FormControl>
                              <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                            </FormControl>
                            <FormLabel className="cursor-pointer text-xs leading-none font-normal">{t('settings.notifications.subPermissions.resetDataUsage')}</FormLabel>
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="notification_enable.data_reset_by_next"
                        render={({ field }) => (
                          <FormItem className="hover:bg-muted/40 flex items-center space-y-0 gap-x-2 rounded-sm px-2 py-1.5 transition-colors">
                            <FormControl>
                              <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                            </FormControl>
                            <FormLabel className="cursor-pointer text-xs leading-none font-normal">{t('settings.notifications.subPermissions.dataResetByNext')}</FormLabel>
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name="notification_enable.subscription_revoked"
                        render={({ field }) => (
                          <FormItem className="hover:bg-muted/40 flex items-center space-y-0 gap-x-2 rounded-sm px-2 py-1.5 transition-colors">
                            <FormControl>
                              <Checkbox checked={field.value || false} onCheckedChange={field.onChange} className="h-4 w-4" />
                            </FormControl>
                            <FormLabel className="cursor-pointer text-xs leading-none font-normal">{t('settings.notifications.subPermissions.subscriptionRevoked')}</FormLabel>
                          </FormItem>
                        )}
                      />
                    </div>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-md border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="overrides">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Sliders className="h-4 w-4" />
                      <span>{t('admins.permissionOverrides', { defaultValue: 'Permission overrides' })}</span>
                      <span className="text-muted-foreground text-xs">{permissionOverridesCount}/9</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <p className="text-muted-foreground mb-3 text-xs">
                      {t('admins.permissionOverridesHint', { defaultValue: 'Leave empty to inherit limits from the selected role. Set to 0 to disable.' })}
                    </p>
                    <PermissionOverridesFields form={form} />
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
            <div className="flex justify-end gap-2 pt-2">
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

      <div className="grid gap-3 sm:grid-cols-2">
        <NumberLimitField form={form} name="permission_overrides.on_hold_timeout_days_min" labelKey="adminRoles.limitFields.on_hold_timeout_days_min" />
        <NumberLimitField form={form} name="permission_overrides.on_hold_timeout_days_max" labelKey="adminRoles.limitFields.on_hold_timeout_days_max" />
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
                <span className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs font-medium">{t('userDialog.gb', { defaultValue: 'GB' })}</span>
              </div>
            </FormControl>
            {numericValue != null && numericValue > 0 && numericValue < ONE_GB_IN_BYTES && (
              <p dir="ltr" className="text-muted-foreground mt-1 w-full text-end text-[11px]">
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
                <span className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs font-medium">{t('userDialog.gb', { defaultValue: 'GB' })}</span>
              </div>
            </FormControl>
            {numericValue != null && numericValue > 0 && numericValue < ONE_GB_IN_BYTES && (
              <p dir="ltr" className="text-muted-foreground mt-1 w-full text-end text-[11px]">
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
