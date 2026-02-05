import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useTranslation } from 'react-i18next'
import { UseFormReturn } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { z } from 'zod'
import { useCreateAdmin, useModifyAdmin } from '@/service/api'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client.ts'
import { PasswordInput } from '@/components/ui/password-input'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { LoaderButton } from '@/components/ui/loader-button'
import useDirDetection from '@/hooks/use-dir-detection'
import { VariablesPopover } from '@/components/ui/variables-popover'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { useEffect, useState } from 'react'
import { ChevronDown, UserCog } from 'lucide-react'

interface AdminModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  editingAdmin?: boolean
  editingAdminUserName: string
  form: UseFormReturn<AdminFormValuesInput>
}

const passwordValidation = z.string().refine(
  value => {
    if (!value) return false // Don't allow empty passwords

    // Check in priority order
    if (value.length < 12) {
      return false
    }
    if ((value.match(/\d/g) || []).length < 2) {
      return false
    }
    if ((value.match(/[A-Z]/g) || []).length < 2) {
      return false
    }
    if ((value.match(/[a-z]/g) || []).length < 2) {
      return false
    }
    return /[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`]/.test(value)
  },
  value => {
    // Return specific error message based on the first validation that fails
    if (!value) {
      return { message: 'Password is required' }
    }
    if (value.length < 12) {
      return { message: 'Password must be at least 12 characters long' }
    }
    if ((value.match(/\d/g) || []).length < 2) {
      return { message: 'Password must contain at least 2 digits' }
    }
    if ((value.match(/[A-Z]/g) || []).length < 2) {
      return { message: 'Password must contain at least 2 uppercase letters' }
    }
    if ((value.match(/[a-z]/g) || []).length < 2) {
      return { message: 'Password must contain at least 2 lowercase letters' }
    }
    if (!/[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`]/.test(value)) {
      return { message: 'Password must contain at least one special character' }
    }
    return { message: 'Invalid password' }
  },
)

export const adminFormSchema = z
  .object({
    username: z.string().min(1, 'Username is required'),
    password: z.string().optional(),
    passwordConfirm: z.string().optional(),
    is_sudo: z.boolean().default(false),
    is_disabled: z.boolean().optional(),
    discord_webhook: z.string().optional(),
    sub_domain: z.string().optional(),
    sub_template: z.string().optional(),
    support_url: z.string().optional(),
    telegram_id: z.number().optional(),
    profile_title: z.string().optional(),
    discord_id: z.number().optional(),
    notification_enable: z
      .object({
        create: z.boolean().optional(),
        modify: z.boolean().optional(),
        delete: z.boolean().optional(),
        status_change: z.boolean().optional(),
        reset_data_usage: z.boolean().optional(),
        data_reset_by_next: z.boolean().optional(),
        subscription_revoked: z.boolean().optional(),
      })
      .optional(),
  })
  .superRefine((data, ctx) => {
    // Only validate password if it's provided (for editing) or if it's a new admin
    if (data.password || !data.username) {
      if (!data.password) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Password is required',
          path: ['password'],
        })
        return
      }

      // Validate password strength
      const passwordResult = passwordValidation.safeParse(data.password)
      if (!passwordResult.success) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: passwordResult.error.errors[0].message,
          path: ['password'],
        })
        return
      }

      // Validate password confirmation
      if (data.password !== data.passwordConfirm) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Passwords do not match',
          path: ['passwordConfirm'],
        })
      }
    }
  })

export type AdminFormValuesInput = z.input<typeof adminFormSchema>
export type AdminFormValues = z.infer<typeof adminFormSchema>
export default function AdminModal({ isDialogOpen, onOpenChange, editingAdminUserName, editingAdmin, form }: AdminModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const handleError = useDynamicErrorHandler()
  const addAdminMutation = useCreateAdmin()
  const modifyAdminMutation = useModifyAdmin()

  useEffect(() => {
    if (!isDialogOpen) setNotificationExpanded(false)
  }, [isDialogOpen])

  // State for collapsible notification section
  const [notificationExpanded, setNotificationExpanded] = useState(false)

  // Watch notification enable fields
  const watchedNotificationEnable = form.watch('notification_enable')

  // Ensure form is cleared when modal is closed
  const handleClose = (open: boolean) => {
    if (!open) {
      form.reset()
    }
    onOpenChange(open)
  }

  const onSubmit = async (values: AdminFormValuesInput) => {
    try {
      const editData = {
        is_sudo: values.is_sudo ?? false,
        password: values.password || undefined,
        is_disabled: values.is_disabled,
        discord_webhook: values.discord_webhook,
        sub_domain: values.sub_domain,
        sub_template: values.sub_template,
        support_url: values.support_url,
        telegram_id: values.telegram_id,
        profile_title: values.profile_title,
        discord_id: values.discord_id,
        notification_enable: values.notification_enable || null,
      }
      if (editingAdmin && editingAdminUserName) {
        await modifyAdminMutation.mutateAsync({
          username: editingAdminUserName,
          data: editData,
        })
        toast.success(
          t('admins.editSuccess', {
            name: values.username,
            defaultValue: 'Admin «{{name}}» has been updated successfully',
          }),
        )
      } else {
        if (!values.password) return
        const createData = {
          ...values,
          is_sudo: values.is_sudo ?? false,
          password: values.password, // Ensure password is present
        }
        await addAdminMutation.mutateAsync({
          data: createData,
        })
        toast.success(
          t('admins.createSuccess', {
            name: values.username,
            defaultValue: 'Admin «{{name}}» has been created successfully',
          }),
        )
      }
      queryClient.invalidateQueries({ queryKey: ['/api/admins'] })
      onOpenChange(false)
      form.reset()
    } catch (error: any) {
      const fields = ['username', 'password', 'passwordConfirm', 'is_sudo', 'is_disabled', 'discord_webhook', 'sub_domain', 'sub_template', 'support_url', 'telegram_id', 'profile_title', 'discord_id']
      handleError({ error, fields, form, contextKey: 'admins' })
    }
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleClose}>
      <DialogContent className="h-full max-w-[750px] sm:h-auto" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className={`${dir === 'rtl' ? 'text-right' : 'text-left'}`} dir={dir}>
            {editingAdmin ? t('admins.editAdmin') : t('admins.createAdmin')}
          </DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
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
                          <Input placeholder={t('admins.enterUsername')} disabled={editingAdmin} isError={hasError} {...field} />
                        </FormControl>
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
                          <PasswordInput placeholder={t('admins.enterPassword')} isError={hasError} {...field} />
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
                          <PasswordInput placeholder={t('admins.enterPasswordConfirm')} isError={hasError} {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )
                  }}
                />
                <FormField
                  control={form.control}
                  name={'telegram_id'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.telegramId')}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder={t('Telegram ID (e.g. 36548974)')}
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
                  name={'discord_id'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.discordId')}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder={t('admins.discordId')}
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
                        <Input placeholder={t('admins.discord')} {...field} />
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
                        <Input placeholder={t('admins.supportUrl')} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'profile_title'}
                  render={({ field }) => (
                    <FormItem className="flex h-full flex-col justify-end gap-2">
                      <div className="flex items-center gap-2">
                        <FormLabel>{t('admins.profile')}</FormLabel>
                        <VariablesPopover />
                      </div>
                      <FormControl>
                        <Input placeholder={t('admins.profile')} {...field} />
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
                        <Input placeholder={t('admins.subDomain')} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name={'sub_template'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admins.subTemplate')}</FormLabel>
                      <FormControl>
                        <Input placeholder={t('admins.subTemplate')} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="flex flex-col gap-4">
                <Collapsible open={notificationExpanded} onOpenChange={setNotificationExpanded}>
                  <div
                    className={cn(
                      'group rounded-md border transition-all duration-200 ease-in-out',
                      notificationExpanded && 'border-primary/50 bg-accent/30',
                      'hover:border-primary/30 hover:bg-accent/20',
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

                <FormField
                  control={form.control}
                  name="is_sudo"
                  render={({ field }) => (
                    <FormItem className="flex w-full cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                      <div className="space-y-0.5">
                        <FormLabel className="text-base">{t('admins.sudo')}</FormLabel>
                      </div>
                      <FormControl>
                        <div onClick={e => e.stopPropagation()}>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </div>
                      </FormControl>
                    </FormItem>
                  )}
                />
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
