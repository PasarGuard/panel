import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import type { ClientTemplateFormValues } from '@/features/templates/forms/client-template-form'
import { DEFAULT_TEMPLATE_CONTENT } from '@/features/templates/forms/client-template-form'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { ClientTemplateType, useCreateClientTemplate, useModifyClientTemplate } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { Pencil, FileCode2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

const TEMPLATE_TYPE_LABELS: Record<string, string> = {
  [ClientTemplateType.clash_subscription]: 'Clash Subscription',
  [ClientTemplateType.xray_subscription]: 'Xray Subscription',
  [ClientTemplateType.singbox_subscription]: 'SingBox Subscription',
  [ClientTemplateType.user_agent]: 'User Agent',
  [ClientTemplateType.grpc_user_agent]: 'gRPC User Agent',
}

const isYamlType = (templateType: string) => templateType === ClientTemplateType.clash_subscription

interface ValidationResult {
  isValid: boolean
  error?: string
}

interface ClientTemplateModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<ClientTemplateFormValues>
  editingTemplate: boolean
  editingTemplateId?: number
}

export default function ClientTemplateModal({ isDialogOpen, onOpenChange, form, editingTemplate, editingTemplateId }: ClientTemplateModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const createClientTemplate = useCreateClientTemplate()
  const modifyClientTemplate = useModifyClientTemplate()
  const [isCodeEditorFullscreen, setIsCodeEditorFullscreen] = useState(false)
  const [validation, setValidation] = useState<ValidationResult>({ isValid: true })

  const templateType = form.watch('template_type')
  const isYaml = isYamlType(templateType)

  const validateContent = useCallback(
    (value: string, showToast = false) => {
      if (!value.trim()) {
        const errorMessage = t('clientTemplates.contentRequired', { defaultValue: 'Content is required' })
        setValidation({ isValid: false, error: errorMessage })
        if (showToast) {
          toast.error(errorMessage)
        }
        return false
      }

      if (isYaml) {
        setValidation({ isValid: true })
        return true
      }

      try {
        JSON.parse(value)
        setValidation({ isValid: true })
        return true
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : t('clientTemplates.invalidJson', { defaultValue: 'Invalid JSON' })
        setValidation({ isValid: false, error: errorMessage })
        if (showToast) {
          toast.error(errorMessage)
        }
        return false
      }
    },
    [isYaml, t],
  )

  const handleEditorValidation = useCallback(
    (markers: any[]) => {
      if (isYaml) {
        validateContent(form.getValues().content)
        return
      }

      if (markers.length > 0) {
        setValidation({
          isValid: false,
          error: markers[0].message,
        })
        return
      }

      validateContent(form.getValues().content)
    },
    [form, isYaml, validateContent],
  )

  useEffect(() => {
    setValidation({ isValid: true })
    if (!editingTemplate) {
      form.setValue('content', DEFAULT_TEMPLATE_CONTENT[templateType as ClientTemplateType] ?? '')
    }
  }, [editingTemplate, form, templateType])

  useEffect(() => {
    if (!isDialogOpen) {
      setIsCodeEditorFullscreen(false)
      setValidation({ isValid: true })
    }
  }, [isDialogOpen])

  const handleSubmit = form.handleSubmit(async values => {
    if (!validateContent(values.content, true)) {
      return
    }

    let finalContent = values.content

    if (!isYamlType(values.template_type)) {
      try {
        finalContent = JSON.stringify(JSON.parse(values.content), null, 2)
      } catch {
        const errorMessage = t('clientTemplates.invalidJson', { defaultValue: 'Invalid JSON' })
        setValidation({ isValid: false, error: errorMessage })
        toast.error(errorMessage)
        return
      }
    }

    try {
      if (editingTemplate && editingTemplateId !== undefined) {
        await modifyClientTemplate.mutateAsync({
          templateId: editingTemplateId,
          data: { name: values.name, content: finalContent, is_default: values.is_default },
        })
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('clientTemplates.updateSuccess', { name: values.name, defaultValue: 'Template "{{name}}" updated successfully' }),
        })
      } else {
        await createClientTemplate.mutateAsync({
          data: { name: values.name, template_type: values.template_type, content: finalContent, is_default: values.is_default },
        })
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('clientTemplates.createSuccess', { name: values.name, defaultValue: 'Template "{{name}}" created successfully' }),
        })
      }

      queryClient.invalidateQueries({ queryKey: ['/api/client_templates'] })
      onOpenChange(false)
    } catch (error: any) {
      const detail = error?.response?._data?.detail || error?.response?.data?.detail || error?.message
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: typeof detail === 'string' ? detail : t('clientTemplates.saveFailed', { defaultValue: 'Failed to save template' }),
      })
    }
  })

  const isPending = createClientTemplate.isPending || modifyClientTemplate.isPending

  const title = editingTemplate ? t('clientTemplates.editTemplate', { defaultValue: 'Edit Client Template' }) : t('clientTemplates.addTemplate', { defaultValue: 'Add Client Template' })

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className={cn('md:h-auto h-full w-full max-w-5xl', dir === 'rtl' && 'rtl')}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingTemplate ? <Pencil className="h-5 w-5" /> : <FileCode2 className="h-5 w-5" />}
            <span>{title}</span>
          </DialogTitle>
          <DialogDescription className="sr-only">
            {t('clientTemplates.modalDescription', { defaultValue: 'Create or edit a client template and adjust its content.' })}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="-mr-4 max-h-[80dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[75dvh] pb-2">
              <div className="grid grid-cols-1 gap-4 md:h-full md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:gap-6">
                <div className="flex flex-col">
                  <div className="flex flex-col space-y-4 md:h-full">
                    <FormField
                      control={form.control}
                      name="content"
                      render={({ field }) => (
                        <FormItem className="md:flex md:h-full md:flex-col">
                          <FormControl className="md:flex md:flex-1">
                            <CodeEditorPanel
                              value={field.value || ''}
                              language={isYaml ? 'yaml' : 'json'}
                              onChange={value => {
                                field.onChange(value)
                                validateContent(value)
                              }}
                              onValidate={handleEditorValidation}
                              enableFullscreen
                              dialogOpen={isDialogOpen}
                              onFullscreenChange={setIsCodeEditorFullscreen}
                              embeddedContainerClassName="h-[calc(50vh-1rem)] sm:h-[calc(55vh-1rem)] md:min-h-[450px]"
                            />
                          </FormControl>
                          {validation.error && !validation.isValid && <FormMessage>{validation.error}</FormMessage>}
                        </FormItem>
                      )}
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('name')}</FormLabel>
                        <FormControl>
                          <Input {...field} placeholder={t('clientTemplates.namePlaceholder', { defaultValue: 'Template name' })} isError={!!form.formState.errors.name} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="template_type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('clientTemplates.templateType', { defaultValue: 'Template Type' })}</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value} disabled={editingTemplate}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('clientTemplates.selectType', { defaultValue: 'Select type' })} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {Object.values(ClientTemplateType).map(type => (
                              <SelectItem key={type} value={type}>
                                {TEMPLATE_TYPE_LABELS[type] || type}
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
                    name="is_default"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                        <div className="space-y-1">
                          <FormLabel className="cursor-pointer">{t('clientTemplates.isDefault', { defaultValue: 'Set as default' })}</FormLabel>
                          <p className="text-xs text-muted-foreground">{t('clientTemplates.isDefaultDescription', { defaultValue: 'Use this template automatically for matching output type.' })}</p>
                        </div>
                        <FormControl>
                          <Switch checked={!!field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              </div>
            </div>

            {!isCodeEditorFullscreen && (
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
                  {t('cancel')}
                </Button>
                <LoaderButton type="submit" isLoading={isPending} disabled={!validation.isValid || isPending} loadingText={t('saving', { defaultValue: 'Saving...' })}>
                  {editingTemplate ? t('modify') : t('create')}
                </LoaderButton>
              </div>
            )}
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
