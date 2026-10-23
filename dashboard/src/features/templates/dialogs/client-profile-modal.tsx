import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { CustomVariablesPopover, normalizeCustomVariableKey } from '@/components/ui/variables-popover'
import { getApiErrorDetail, invalidateClientProfileQueries } from '@/features/templates/components/use-client-profile-options'
import { CLIENT_PROFILE_TEMPLATE_TYPES, clientProfileFormToPayload, DEFAULT_TEMPLATE_VALUE, type ClientProfileFormValues } from '@/features/templates/forms/client-profile-form'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors'
import { cn } from '@/lib/utils'
import { useCreateClientProfile, useGetClientTemplatesSimple, useModifyClientProfile } from '@/service/api'
import { hasPermission } from '@/utils/rbac'
import { Pencil, Plus, SlidersHorizontal, Trash2, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useFieldArray, UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

const TEMPLATE_TYPE_LABELS: Record<(typeof CLIENT_PROFILE_TEMPLATE_TYPES)[number], string> = {
  xray_subscription: 'Xray (JSON)',
  singbox_subscription: 'Sing-box',
  clash_subscription: 'Clash / Mihomo',
}

interface ClientProfileModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<ClientProfileFormValues>
  editingProfile: boolean
  editingProfileId?: number
}

const Section = ({ title, description, actions, children }: { title: string; description?: string; actions?: ReactNode; children: ReactNode }) => (
  <div className="space-y-3">
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0 space-y-1">
        <h3 className="text-sm font-semibold sm:text-base">{title}</h3>
        {description ? <p className="text-muted-foreground text-xs">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
    {children}
  </div>
)

export default function ClientProfileModal({ isDialogOpen, onOpenChange, form, editingProfile, editingProfileId }: ClientProfileModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { admin } = useAdmin()
  const handleError = useDynamicErrorHandler()
  const createClientProfile = useCreateClientProfile()
  const modifyClientProfile = useModifyClientProfile()
  const [removeHeaderDraft, setRemoveHeaderDraft] = useState('')
  const canListTemplates = hasPermission(admin, 'client_templates', 'read_simple')
  const { data: templatesData } = useGetClientTemplatesSimple({ all: true }, { query: { enabled: isDialogOpen && canListTemplates, staleTime: 5 * 60 * 1000, gcTime: 10 * 60 * 1000 } })
  const headersArray = useFieldArray({ control: form.control, name: 'response_headers' })
  const variablesArray = useFieldArray({ control: form.control, name: 'custom_variables' })
  const removeHeaders = form.watch('remove_response_headers')
  const customVariables = form.watch('custom_variables')
  const errors = form.formState.errors
  const inheritedPlaceholder = t('clientProfiles.inherited', { defaultValue: 'Inherited from settings' })

  const addRemoveHeader = () => {
    const name = removeHeaderDraft.trim()
    if (!name) return
    if (!removeHeaders.some(existing => existing.toLowerCase() === name.toLowerCase())) {
      form.setValue('remove_response_headers', [...removeHeaders, name], { shouldDirty: true, shouldValidate: true })
    }
    setRemoveHeaderDraft('')
  }

  const handleSubmit = form.handleSubmit(async values => {
    const payload = clientProfileFormToPayload(values)
    try {
      if (editingProfile && editingProfileId !== undefined) {
        await modifyClientProfile.mutateAsync({ profileId: editingProfileId, data: payload })
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('clientProfiles.updateSuccess', { name: payload.name, defaultValue: 'Profile "{{name}}" saved' }),
        })
      } else {
        await createClientProfile.mutateAsync({ data: payload })
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('clientProfiles.createSuccess', { name: payload.name, defaultValue: 'Profile "{{name}}" created' }),
        })
      }
      invalidateClientProfileQueries()
      onOpenChange(false)
    } catch (error: any) {
      if (error?.response?._data || error?.response?.data || error?.data) {
        handleError({ error, fields: ['name', 'note'], form, contextKey: 'clientProfiles' })
      } else {
        toast.error(t('error', { defaultValue: 'Error' }), {
          description: getApiErrorDetail(error) || t('clientProfiles.saveFailed', { defaultValue: 'Failed to save profile' }),
        })
      }
    }
  })

  const isPending = createClientProfile.isPending || modifyClientProfile.isPending
  const title = editingProfile ? t('clientProfiles.editProfile', { defaultValue: 'Edit client profile' }) : t('clientProfiles.addProfile', { defaultValue: 'Create client profile' })

  const textField = (name: 'profile_title' | 'support_url' | 'announce' | 'announce_url', label: string, hint?: string) => (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input {...field} placeholder={inheritedPlaceholder} />
          </FormControl>
          {hint ? <FormDescription className="text-xs">{hint}</FormDescription> : null}
          <FormMessage />
        </FormItem>
      )}
    />
  )

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className={cn('h-full w-full max-w-3xl md:h-auto', dir === 'rtl' && 'rtl')} onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingProfile ? <Pencil className="h-5 w-5" /> : <SlidersHorizontal className="h-5 w-5" />}
            <span>{title}</span>
          </DialogTitle>
          <DialogDescription className="text-xs">
            {t('clientProfiles.modalDescription', {
              defaultValue: 'Users on this profile get these templates and subscription settings. Empty fields use the panel settings.',
            })}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="-mr-4 max-h-[75dvh] space-y-5 overflow-y-auto px-2 pr-4 pb-2">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('name')}</FormLabel>
                      <FormControl>
                        <Input {...field} maxLength={64} placeholder={t('clientProfiles.namePlaceholder', { defaultValue: 'For example: Happ iOS' })} isError={!!errors.name} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="note"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('clientProfiles.note', { defaultValue: 'Note' })}</FormLabel>
                      <FormControl>
                        <Input {...field} maxLength={500} placeholder={t('clientProfiles.notePlaceholder', { defaultValue: 'Only admins see it' })} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <Separator />
              <Section
                title={t('clientProfiles.templatesSection', { defaultValue: 'Templates' })}
                description={t('clientProfiles.templatesDescription', { defaultValue: 'Which client template to use for each app type.' })}
              >
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  {CLIENT_PROFILE_TEMPLATE_TYPES.map(type => (
                    <FormField
                      key={type}
                      control={form.control}
                      name={`templates.${type}`}
                      render={({ field }) => {
                        const options = (templatesData?.templates ?? []).filter(template => template.template_type === type)
                        const hasCurrent = field.value === DEFAULT_TEMPLATE_VALUE || options.some(template => String(template.id) === field.value)
                        return (
                          <FormItem>
                            <FormLabel>{TEMPLATE_TYPE_LABELS[type]}</FormLabel>
                            <Select value={field.value} onValueChange={field.onChange} disabled={!canListTemplates}>
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                <SelectItem value={DEFAULT_TEMPLATE_VALUE}>{t('clientProfiles.defaultTemplate', { defaultValue: 'Default template' })}</SelectItem>
                                {!hasCurrent && <SelectItem value={field.value}>{`#${field.value}`}</SelectItem>}
                                {options.map(template => (
                                  <SelectItem key={template.id} value={String(template.id)}>
                                    {template.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )
                      }}
                    />
                  ))}
                </div>
                {!canListTemplates && (
                  <p className="text-muted-foreground text-xs">
                    {t('clientProfiles.noTemplatesPermission', { defaultValue: 'You do not have access to client templates, so the choice cannot be changed.' })}
                  </p>
                )}
              </Section>

              <Separator />
              <Section
                title={t('clientProfiles.subscriptionSection', { defaultValue: 'Subscription' })}
                description={t('clientProfiles.subscriptionDescription', { defaultValue: 'Leave a field empty to keep the value from the panel settings.' })}
              >
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {textField('profile_title', t('clientProfiles.profileTitle', { defaultValue: 'Profile title' }))}
                  {textField('support_url', t('clientProfiles.supportUrl', { defaultValue: 'Support link' }))}
                  {textField(
                    'announce',
                    t('clientProfiles.announce', { defaultValue: 'Announcement' }),
                    t('clientProfiles.announceHint', { defaultValue: 'Shown in apps that support it (Happ, v2RayTun).' }),
                  )}
                  {textField('announce_url', t('clientProfiles.announceUrl', { defaultValue: 'Announcement link' }))}
                  <FormField
                    control={form.control}
                    name="update_interval"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('clientProfiles.updateInterval', { defaultValue: 'Update interval (hours)' })}</FormLabel>
                        <FormControl>
                          <Input {...field} inputMode="numeric" placeholder={inheritedPlaceholder} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="randomize_order"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('clientProfiles.randomizeOrder', { defaultValue: 'Shuffle servers' })}</FormLabel>
                        <Select value={field.value} onValueChange={field.onChange}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="inherit">{inheritedPlaceholder}</SelectItem>
                            <SelectItem value="on">{t('clientProfiles.on', { defaultValue: 'On' })}</SelectItem>
                            <SelectItem value="off">{t('clientProfiles.off', { defaultValue: 'Off' })}</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </Section>

              <Separator />
              <Section
                title={t('clientProfiles.headersSection', { defaultValue: 'Response headers' })}
                description={t('clientProfiles.headersDescription', { defaultValue: 'Extra headers sent with the subscription. Values can use variables like {USERNAME}.' })}
                actions={
                  <Button type="button" variant="outline" size="sm" onClick={() => headersArray.append({ key: '', value: '' })}>
                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                    {t('clientProfiles.addHeader', { defaultValue: 'Add header' })}
                  </Button>
                }
              >
                {headersArray.fields.length > 0 ? (
                  <div className="space-y-2">
                    {headersArray.fields.map((row, index) => (
                      <div key={row.id} className="flex items-start gap-2">
                        <div className="min-w-0 flex-1 space-y-1">
                          <Input {...form.register(`response_headers.${index}.key`)} placeholder={t('clientProfiles.headerName', { defaultValue: 'Header name' })} className="font-mono text-xs" />
                          {errors.response_headers?.[index]?.key?.message ? <p className="text-destructive text-xs">{errors.response_headers[index]?.key?.message}</p> : null}
                        </div>
                        <div className="min-w-0 flex-[2] space-y-1">
                          <Input {...form.register(`response_headers.${index}.value`)} placeholder={t('clientProfiles.headerValue', { defaultValue: 'Value' })} className="font-mono text-xs" />
                          {errors.response_headers?.[index]?.value?.message ? <p className="text-destructive text-xs">{errors.response_headers[index]?.value?.message}</p> : null}
                        </div>
                        <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-9 w-9 shrink-0" onClick={() => headersArray.remove(index)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-xs">{t('clientProfiles.noHeaders', { defaultValue: 'No extra headers.' })}</p>
                )}

                <div className="space-y-2">
                  <FormLabel>{t('clientProfiles.removeHeaders', { defaultValue: 'Remove headers' })}</FormLabel>
                  <p className="text-muted-foreground text-xs">
                    {t('clientProfiles.removeHeadersDescription', { defaultValue: 'Headers the panel normally sends but this profile should not, for example Announce.' })}
                  </p>
                  <div className="flex gap-2">
                    <Input
                      value={removeHeaderDraft}
                      onChange={e => setRemoveHeaderDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          addRemoveHeader()
                        }
                      }}
                      placeholder={t('clientProfiles.headerName', { defaultValue: 'Header name' })}
                      className="font-mono text-xs"
                    />
                    <Button type="button" variant="outline" size="sm" className="h-9 shrink-0" onClick={addRemoveHeader} disabled={!removeHeaderDraft.trim()}>
                      <Plus className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  {removeHeaders.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {removeHeaders.map((name, index) => (
                        <Badge key={`${name}-${index}`} variant={errors.remove_response_headers?.[index] ? 'destructive' : 'secondary'} className="gap-1 font-mono text-xs">
                          {name}
                          <button
                            type="button"
                            aria-label={t('remove')}
                            onClick={() =>
                              form.setValue(
                                'remove_response_headers',
                                removeHeaders.filter((_, i) => i !== index),
                                { shouldDirty: true, shouldValidate: true },
                              )
                            }
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                  {Array.isArray(errors.remove_response_headers) && errors.remove_response_headers.some(Boolean) ? (
                    <p className="text-destructive text-xs">{errors.remove_response_headers.find(Boolean)?.message}</p>
                  ) : null}
                </div>
              </Section>

              <Separator />
              <Section
                title={t('clientProfiles.variablesSection', { defaultValue: 'Variables' })}
                description={t('clientProfiles.variablesDescription', { defaultValue: 'Your own placeholders for this profile. They override panel variables with the same name.' })}
                actions={
                  <>
                    <CustomVariablesPopover customVariables={customVariables} />
                    <Button type="button" variant="outline" size="sm" onClick={() => variablesArray.append({ key: '', value: '' })}>
                      <Plus className="mr-1.5 h-3.5 w-3.5" />
                      {t('clientProfiles.addVariable', { defaultValue: 'Add variable' })}
                    </Button>
                  </>
                }
              >
                {variablesArray.fields.length > 0 ? (
                  <div className="space-y-2">
                    {variablesArray.fields.map((row, index) => (
                      <div key={row.id} className="flex items-start gap-2">
                        <div className="min-w-0 flex-1 space-y-1">
                          <FormField
                            control={form.control}
                            name={`custom_variables.${index}.key`}
                            render={({ field }) => (
                              <Input {...field} onChange={e => field.onChange(normalizeCustomVariableKey(e.target.value))} placeholder="CUSTOM_HOST" className="font-mono text-xs" />
                            )}
                          />
                          {errors.custom_variables?.[index]?.key?.message ? <p className="text-destructive text-xs">{errors.custom_variables[index]?.key?.message}</p> : null}
                        </div>
                        <div className="min-w-0 flex-[2] space-y-1">
                          <Input {...form.register(`custom_variables.${index}.value`)} maxLength={512} placeholder="{USERNAME}.example.com" className="font-mono text-xs" />
                          {errors.custom_variables?.[index]?.value?.message ? <p className="text-destructive text-xs">{errors.custom_variables[index]?.value?.message}</p> : null}
                        </div>
                        <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-9 w-9 shrink-0" onClick={() => variablesArray.remove(index)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-xs">{t('clientProfiles.noVariables', { defaultValue: 'No variables.' })}</p>
                )}
              </Section>
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit" isLoading={isPending} disabled={isPending} loadingText={t('saving', { defaultValue: 'Saving...' })}>
                {editingProfile ? t('modify') : t('create')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
