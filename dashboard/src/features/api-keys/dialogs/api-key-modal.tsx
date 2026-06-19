import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm, useFieldArray, Controller } from 'react-hook-form'
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
import { Key, Copy, Check, ChevronDown, ChevronRight, ShieldCheck, KeyRound } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'

interface ApiKeyModalProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  editingApiKey: APIKeyResponse | null
}

// All resources and their available actions
const RESOURCE_ACTIONS: Record<string, string[]> = {
  users: ['create', 'read', 'read_simple', 'update', 'delete', 'reset_usage', 'revoke_sub', 'set_owner', 'activate_next_plan'],
  admins: ['create', 'read', 'read_simple', 'update', 'delete', 'reset_usage'],
  nodes: ['create', 'read', 'read_simple', 'update', 'delete', 'reconnect', 'update_core', 'logs', 'stats'],
  groups: ['create', 'read', 'read_simple', 'update', 'delete'],
  hosts: ['create', 'read', 'update'],
  templates: ['create', 'read', 'read_simple', 'update', 'delete'],
  client_templates: ['create', 'read', 'read_simple', 'update', 'delete'],
  cores: ['create', 'read', 'read_simple', 'update', 'delete'],
  settings: ['read', 'read_general', 'update'],
  system: ['read'],
  hwids: ['read', 'delete'],
  admin_roles: ['create', 'read', 'read_simple', 'update', 'delete'],
  api_keys: ['create', 'read', 'read_simple', 'update', 'delete'],
}

type ActionValue = true | { scope: number } | null

function getActionValue(permissions: RolePermissions | undefined, resource: string, action: string): ActionValue {
  const res = (permissions as any)?.[resource]
  if (!res) return null
  const val = res[action]
  if (val === undefined || val === null) return null
  return val
}

function setActionValue(permissions: RolePermissions, resource: string, action: string, value: ActionValue): RolePermissions {
  const updated = { ...permissions } as any
  if (!updated[resource]) updated[resource] = {}
  else updated[resource] = { ...updated[resource] }

  if (value === null) {
    delete updated[resource][action]
    if (Object.keys(updated[resource]).length === 0) delete updated[resource]
  } else {
    updated[resource][action] = value
  }
  return updated
}

function PermissionToggle({
  resource,
  action,
  value,
  onChange,
}: {
  resource: string
  action: string
  value: ActionValue
  onChange: (v: ActionValue) => void
}) {
  const isEnabled = value !== null
  const isScoped = typeof value === 'object' && value !== null
  const scope = isScoped ? (value as { scope: number }).scope : 1

  return (
    <div className="flex items-center gap-2 py-0.5">
      <Switch
        checked={isEnabled}
        onCheckedChange={(checked) => onChange(checked ? true : null)}
        className="scale-75 origin-left"
      />
      <span className={cn('text-xs w-24 truncate', !isEnabled && 'text-muted-foreground')}>
        {action}
      </span>
      {isEnabled && (resource === 'users' || resource === 'admins') && (action === 'read' || action === 'read_simple' || action === 'update' || action === 'delete') && (
        <Select
          value={isScoped ? scope.toString() : 'all'}
          onValueChange={(v) => onChange(v === 'all' ? true : { scope: parseInt(v) })}
        >
          <SelectTrigger className="h-5 text-[10px] w-16 px-1.5">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all" className="text-[10px]">All</SelectItem>
            <SelectItem value="1" className="text-[10px]">Own</SelectItem>
          </SelectContent>
        </Select>
      )}
    </div>
  )
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

  const permissionsValue = form.watch('permissions') as RolePermissions

  const totalPermissionsCount = useMemo(() => {
    let count = 0
    for (const value of Object.values(permissionsValue || {})) {
      if (!value || typeof value !== 'object') continue
      for (const inner of Object.values(value as Record<string, unknown>)) {
        if (inner === true) count += 1
        else if (inner && typeof inner === 'object' && Number((inner as any).scope) > 0) count += 1
      }
    }
    return count
  }, [permissionsValue])

  useEffect(() => {
    if (editingApiKey) {
      form.reset({
        name: editingApiKey.name,
        note: editingApiKey.note || '',
        permissions: (editingApiKey.permissions as RolePermissions) || {},
        status: editingApiKey.status || 'active',
        expire_date: editingApiKey.expire_date,
      })
    } else {
      // Default to the admin's own role permissions as a starting point
      const defaultPermissions = (admin?.role?.permissions as RolePermissions) || {}
      form.reset({
        ...apiKeyFormDefaultValues,
        permissions: defaultPermissions,
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
            permissions: values.permissions as RolePermissions,
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
            permissions: values.permissions as RolePermissions,
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

              {/* Permissions editor */}
              <Accordion type="single" collapsible className="mt-0! mb-2 flex w-full flex-col gap-y-4">
                <AccordionItem className="rounded-sm border px-4 **:data-[state=closed]:no-underline **:data-[state=open]:no-underline" value="permissions">
                  <AccordionTrigger className="hover:no-underline py-4">
                    <div className="flex items-center gap-2">
                      <KeyRound className="h-4 w-4" />
                      <span>{t('adminRoles.permissions', { defaultValue: 'Permissions' })}</span>
                      {totalPermissionsCount > 0 && (
                        <Badge variant="secondary" className="ms-2 shrink-0 text-[10px]">
                          {t('adminRoles.permissionCount', { count: totalPermissionsCount, defaultValue: '{{count}} permissions' })}
                        </Badge>
                      )}
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="pb-3 pt-1">
                    <div className="max-h-[250px] overflow-y-auto pr-1 border rounded-md">
                      <Accordion type="multiple" className="w-full">
                        {Object.entries(RESOURCE_ACTIONS).map(([resource, actions]) => {
                          const resourceData = (permissionsValue as any)?.[resource]
                          const enabledCount = resourceData ? Object.values(resourceData).filter(Boolean).length : 0
                          return (
                            <AccordionItem
                              value={resource}
                              key={resource}
                              className="px-3 border-b last:border-b-0"
                            >
                              <AccordionTrigger className="py-2 hover:no-underline">
                                <div className="flex items-center gap-2">
                                  <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
                                  <span className="capitalize text-sm font-medium">{resource.replace('_', ' ')}</span>
                                  {enabledCount > 0 && (
                                    <Badge variant="secondary" className="h-4 px-1.5 text-[9px]">
                                      {enabledCount}
                                    </Badge>
                                  )}
                                </div>
                              </AccordionTrigger>
                              <AccordionContent className="pb-3 pt-1 grid grid-cols-2 gap-x-4 gap-y-1">
                                {actions.map((action) => (
                                  <PermissionToggle
                                    key={action}
                                    resource={resource}
                                    action={action}
                                    value={getActionValue(permissionsValue || {}, resource, action)}
                                    onChange={(v) => {
                                      const updated = setActionValue(permissionsValue || {}, resource, action, v)
                                      form.setValue('permissions', updated as any)
                                    }}
                                  />
                                ))}
                              </AccordionContent>
                            </AccordionItem>
                          )
                        })}
                      </Accordion>
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
