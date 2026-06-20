import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { LoaderButton } from '@/components/ui/loader-button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DatePicker } from '@/components/common/date-picker'
import {
  serializeDatePickerValue,
  toDatePickerDisplayDate,
} from '@/utils/datePickerUtils'
import {
  apiKeyFormSchema,
  ApiKeyFormValuesInput,
  ApiKeyFormValues,
  apiKeyFormDefaultValues,
} from '../forms/api-key-form'
import {
  useCreateApiKey,
  useModifyApiKey,
  APIKeyResponse,
  getListApiKeysQueryKey,
  RolePermissions,
  useGetAdminsSimple,
} from '@/service/api'
import { useAdmin } from '@/hooks/use-admin'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Key, Copy, Check, KeyRound, Pencil } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Switch } from '@/components/ui/switch'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { PermissionCountBadge, PermissionEditor } from '@/features/admin-roles/components/permission-editor'
import { RolePermissionFormMap, sanitizeRolePermissions } from '@/features/admin-roles/forms/admin-role-form'

interface ApiKeyModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  editingApiKey: APIKeyResponse | null
}

export default function ApiKeyModal({
  isDialogOpen,
  onOpenChange,
  editingApiKey,
}: ApiKeyModalProps) {
  const { t } = useTranslation()
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const queryClient = useQueryClient()
  const { admin } = useAdmin()
  const isOwner = admin?.role?.is_owner === true
  const adminsQuery = useGetAdminsSimple({ all: true }, { query: { enabled: isOwner && isDialogOpen } })
  const admins = adminsQuery.data?.admins || []
  const createMutation = useCreateApiKey({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListApiKeysQueryKey() })
      },
    },
  })
  const updateMutation = useModifyApiKey({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListApiKeysQueryKey() })
      },
    },
  })

  const form = useForm<ApiKeyFormValuesInput, unknown, ApiKeyFormValues>({
    resolver: zodResolver(apiKeyFormSchema),
    defaultValues: apiKeyFormDefaultValues,
  })

  const permissionsValue = form.watch('permissions') as RolePermissionFormMap
  const inheritPermissions = form.watch('inherit_permissions')

  useEffect(() => {
    if (editingApiKey) {
      form.reset({
        name: editingApiKey.name,
        admin_id: editingApiKey.admin_id,
        note: editingApiKey.note || '',
        permissions: sanitizeRolePermissions(editingApiKey.inherit_permissions ? admin?.role?.permissions : editingApiKey.permissions),
        inherit_permissions: editingApiKey.inherit_permissions ?? true,
        status: editingApiKey.status || 'active',
        expire_date: editingApiKey.expire_date,
      })
    } else {
      form.reset({
        ...apiKeyFormDefaultValues,
        admin_id: admin?.id ?? null,
        permissions: {},
        inherit_permissions: true,
      })
    }
    setCreatedKey(null)
  }, [editingApiKey, form, isDialogOpen, admin])

  const onSubmit = async (values: ApiKeyFormValues) => {
    try {
      if (editingApiKey) {
        await updateMutation.mutateAsync({
          keyId: editingApiKey.id,
          data: {
            name: values.name,
            note: values.note,
            admin_id: isOwner ? values.admin_id || undefined : undefined,
            permissions: values.inherit_permissions ? {} : (values.permissions as RolePermissions),
            inherit_permissions: values.inherit_permissions,
            expire_date: values.expire_date as string | null | undefined,
            status: values.status,
          },
        })
        toast.success(t('apiKeys.updateSuccess'))
        onOpenChange(false)
      } else {
        const response = await createMutation.mutateAsync({
          data: {
            name: values.name,
            admin_id: values.admin_id || undefined,
            note: values.note,
            permissions: values.inherit_permissions ? {} : (values.permissions as RolePermissions),
            inherit_permissions: values.inherit_permissions,
            expire_date: values.expire_date as string | null | undefined,
          },
        })
        setCreatedKey(response.api_key)
        toast.success(t('apiKeys.createSuccess'))
      }
    } catch (error: any) {
      toast.error(
        editingApiKey ? t('apiKeys.updateFailed') : t('apiKeys.createFailed'),
        {
          description: error?.data?.detail || error?.message,
        }
      )
    }
  }

  const copyToClipboard = () => {
    if (createdKey) {
      navigator.clipboard.writeText(createdKey)
      setCopied(true)
      toast.success(t('apiKeys.apiKeyCopySuccess'))
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setCreatedKey(null)
      setCopied(false)
    }
    onOpenChange(open)
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="h-auto max-w-[640px]" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingApiKey ? <Pencil className="h-5 w-5" /> : <KeyRound className="h-5 w-5" />}
            <span>{editingApiKey ? t('apiKeys.editKey') : t('apiKeys.createKey')}</span>
          </DialogTitle>
          <DialogDescription className="sr-only">
            {t('apiKeys.description', { defaultValue: 'Manage API keys for programmatic access' })}
          </DialogDescription>
        </DialogHeader>

        {createdKey ? (
          <div className="space-y-4">
            <div className="-mr-4 max-h-[75dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[70dvh]">
              <Alert>
                <Key className="h-4 w-4" />
                <AlertTitle>{t('apiKeys.apiKey')}</AlertTitle>
                <AlertDescription>{t('apiKeys.apiKeyShowWarning')}</AlertDescription>
              </Alert>
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={createdKey}
                  className="font-mono"
                  onClick={(e) => (e.target as HTMLInputElement).select()}
                />
                <Button
                  size="icon"
                  variant="outline"
                  onClick={copyToClipboard}
                  aria-label={t('apiKeys.apiKeyCopy')}
                  title={t('apiKeys.apiKeyCopy')}
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <DialogFooter className="pt-2">
              <Button onClick={() => handleOpenChange(false)}>
                {t('close')}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <div className="-mr-4 max-h-[75dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[70dvh]">
                <div className="grid grid-cols-1 items-stretch gap-4 sm:grid-cols-2">
                  {isOwner && (
                    <FormField
                      control={form.control}
                      name="admin_id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('apiKeys.admin')}</FormLabel>
                          <Select
                            value={field.value ? String(field.value) : ''}
                            onValueChange={value => field.onChange(Number(value))}
                            disabled={adminsQuery.isLoading}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder={t('apiKeys.selectAdmin')} />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {admins.map(item => (
                                <SelectItem key={item.id} value={String(item.id)}>
                                  {item.username}
                                </SelectItem>
                              ))}
                              {adminsQuery.isLoading && (
                                <SelectItem value="__loading_admins__" disabled>
                                  {t('loading', { defaultValue: 'Loading...' })}
                                </SelectItem>
                              )}
                            </SelectContent>
                          </Select>
                          <FormDescription>
                            {t('apiKeys.adminDescription', { defaultValue: 'The key will authenticate as this admin.' })}
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('apiKeys.name')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('apiKeys.name')} autoComplete="off" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="expire_date"
                    render={({ field }) => (
                      <FormItem className="flex flex-col">
                        <FormLabel>{t('apiKeys.expireDate')}</FormLabel>
                        <FormControl>
                          <DatePicker
                            mode="single"
                            showTime
                            useUtcTimestamp
                            date={toDatePickerDisplayDate(field.value)}
                            onDateChange={(date) => {
                              const value = date ? serializeDatePickerValue(date, { useUtcTimestamp: true }) : null
                              field.onChange(value)
                            }}
                            placeholder={t('apiKeys.expireDate')}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {editingApiKey && (
                    <FormField
                      control={form.control}
                      name="status"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('apiKeys.status')}</FormLabel>
                          <Select value={field.value} onValueChange={field.onChange}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder={t('apiKeys.status')} />
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
                  )}
                </div>

                <Accordion type="single" collapsible className="!mt-0 flex w-full flex-col gap-y-3">
                  <AccordionItem className="rounded-md border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="permissions">
                    <AccordionTrigger>
                      <div className="flex items-center gap-2">
                        <KeyRound className="h-4 w-4" />
                        <span>{t('adminRoles.permissions', { defaultValue: 'Permissions' })}</span>
                        {!inheritPermissions && <PermissionCountBadge permissions={permissionsValue} />}
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="px-1 pt-1">
                      <div className="space-y-3">
                        <FormField
                          control={form.control}
                          name="inherit_permissions"
                          render={({ field }) => (
                            <FormItem className="flex cursor-pointer flex-row items-center justify-between space-y-0 rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                              <div className="space-y-0.5">
                                <FormLabel className="text-base">{t('apiKeys.inheritPermissions', { defaultValue: 'Inherit admin permissions' })}</FormLabel>
                                <FormDescription>
                                  {t('apiKeys.inheritPermissionsDescription', { defaultValue: "Use the owning admin's current role permissions. Disable to store custom permissions on this key." })}
                                </FormDescription>
                              </div>
                              <FormControl>
                                <div onClick={e => e.stopPropagation()}>
                                  <Switch checked={!!field.value} onCheckedChange={field.onChange} />
                                </div>
                              </FormControl>
                            </FormItem>
                          )}
                        />
                        {!inheritPermissions && (
                          <PermissionEditor
                            permissions={permissionsValue}
                            onPermissionsChange={next => form.setValue('permissions', next, { shouldDirty: true })}
                          />
                        )}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>

                <div className="pt-0.5">
                  <FormField
                    control={form.control}
                    name="note"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('apiKeys.note')}</FormLabel>
                        <FormControl>
                          <Textarea placeholder={t('apiKeys.note')} rows={4} className="min-h-[96px] resize-y" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleOpenChange(false)}
                >
                  {t('cancel')}
                </Button>
                <LoaderButton
                  type="submit"
                  isLoading={createMutation.isPending || updateMutation.isPending}
                  loadingText={editingApiKey ? t('modifying') : t('creating')}
                >
                  {editingApiKey ? t('modify') : t('create')}
                </LoaderButton>
              </div>
            </form>
          </Form>
        )}
      </DialogContent>
    </Dialog>
  )
}
