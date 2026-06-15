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
} from '@/service/api'
import { useAdmin } from '@/hooks/use-admin'
import { useGetRolesSimple } from '@/service/api'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Key, Copy, Check } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

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
  const rolesQuery = useGetRolesSimple()
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

  const filteredRoles = (rolesQuery.data?.roles || []).filter(role => {
    if (!admin) return false
    if (admin.role?.is_owner) return true
    return role.id === admin.role?.id
  })

  useEffect(() => {
    if (editingApiKey) {
      form.reset({
        name: editingApiKey.name,
        note: editingApiKey.note || '',
        role_id: editingApiKey.role_id,
        status: editingApiKey.status || 'active',
        expire_date: editingApiKey.expire_date,
      })
    } else {
      form.reset({
        ...apiKeyFormDefaultValues,
        role_id: admin?.role?.id || 2
      })
    }
    setCreatedKey(null)
  }, [editingApiKey, form, isOpen, admin])

  const onSubmit = async (values: ApiKeyFormValues) => {
    try {
      if (editingApiKey) {
        await updateMutation.mutateAsync({
          keyId: editingApiKey.id,
          data: values,
        })
        toast.success(t('apiKeys.updateSuccess'))
        onOpenChange(false)
      } else {
        const response = await createMutation.mutateAsync({ data: values })
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
      <DialogContent className="sm:max-w-[500px]">
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

              <FormField
                control={form.control}
                name="role_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('apiKeys.role')}</FormLabel>
                    <Select
                      value={field.value.toString()}
                      onValueChange={(val) => field.onChange(parseInt(val))}
                      disabled={filteredRoles.length <= 1}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder={t('apiKeys.role')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {filteredRoles.map((role) => (
                          <SelectItem key={role.id} value={role.id.toString()}>
                            {role.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
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
