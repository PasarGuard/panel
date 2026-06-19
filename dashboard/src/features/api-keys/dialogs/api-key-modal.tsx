import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Dialog,
  DialogContent,
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
  ApiKeyFormValues,
  apiKeyFormDefaultValues,
} from '../forms/api-key-form'
import {
  useCreateApiKey,
  useModifyApiKey,
  APIKeyResponse,
  getListApiKeysQueryKey,
  RolePermissions,
} from '@/service/api'
import { useAdmin } from '@/hooks/use-admin'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Key, Copy, Check, KeyRound } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Switch } from '@/components/ui/switch'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { PermissionCountBadge, PermissionEditor } from '@/features/admin-roles/components/permission-editor'
import { RolePermissionFormMap } from '@/features/admin-roles/forms/admin-role-form'

interface ApiKeyModalProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  editingApiKey: APIKeyResponse | null
}

export default function ApiKeyModal({
  isOpen,
  onOpenChange,
  editingApiKey,
}: ApiKeyModalProps) {
  const { t } = useTranslation()
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const queryClient = useQueryClient()
  const { admin } = useAdmin()
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

  const form = useForm<ApiKeyFormValues>({
    resolver: zodResolver(apiKeyFormSchema),
    defaultValues: apiKeyFormDefaultValues,
  })

  const permissionsValue = form.watch('permissions') as RolePermissionFormMap
  const inheritPermissions = form.watch('inherit_permissions')

  useEffect(() => {
    if (editingApiKey) {
      form.reset({
        name: editingApiKey.name,
        note: editingApiKey.note || '',
        permissions: ((editingApiKey.inherit_permissions ? admin?.role?.permissions : editingApiKey.permissions) as RolePermissionFormMap) || {},
        inherit_permissions: editingApiKey.inherit_permissions ?? true,
        status: editingApiKey.status || 'active',
        expire_date: editingApiKey.expire_date,
      })
    } else {
      // Default to the admin's own role permissions as a starting point
      const defaultPermissions = (admin?.role?.permissions as RolePermissions) || {}
      form.reset({
        ...apiKeyFormDefaultValues,
        permissions: defaultPermissions,
        inherit_permissions: true,
      })
    }
    setCreatedKey(null)
  }, [editingApiKey, form, isOpen, admin])

  const onSubmit = async (values: ApiKeyFormValues) => {
    try {
      if (editingApiKey) {
        await updateMutation.mutateAsync({
          keyId: editingApiKey.id,
          data: {
            name: values.name,
            note: values.note,
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

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[540px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editingApiKey ? t('apiKeys.editKey') : t('apiKeys.createKey')}
          </DialogTitle>
        </DialogHeader>

        {createdKey ? (
          <div className="space-y-4 py-4">
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
              <Button size="icon" variant="outline" onClick={copyToClipboard}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <Button className="w-full" onClick={() => onOpenChange(false)}>
              {t('close')}
            </Button>
          </div>
        ) : (
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('apiKeys.name')}</FormLabel>
                    <FormControl>
                      <Input placeholder={t('apiKeys.name')} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Accordion type="single" collapsible className="mt-0! mb-2 flex w-full flex-col gap-y-4">
                <AccordionItem className="rounded-sm border px-4 **:data-[state=closed]:no-underline **:data-[state=open]:no-underline" value="permissions">
                  <AccordionTrigger className="hover:no-underline py-4">
                    <div className="flex items-center gap-2">
                      <KeyRound className="h-4 w-4" />
                      <span>{t('adminRoles.permissions', { defaultValue: 'Permissions' })}</span>
                      {!inheritPermissions && <PermissionCountBadge permissions={permissionsValue} />}
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="pb-3 pt-1">
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
                          const value = serializeDatePickerValue(date, { useUtcTimestamp: true })
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
                          <SelectItem value="active">{t('admins.active')}</SelectItem>
                          <SelectItem value="disabled">{t('admins.disabled')}</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={form.control}
                name="note"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('apiKeys.note')}</FormLabel>
                    <FormControl>
                      <Textarea placeholder={t('apiKeys.note')} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                >
                  {t('cancel')}
                </Button>
                <LoaderButton
                  type="submit"
                  isLoading={createMutation.isPending || updateMutation.isPending}
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
