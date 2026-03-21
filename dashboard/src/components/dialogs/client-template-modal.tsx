import { useTheme } from '@/components/common/theme-provider'
import type { ClientTemplateFormValues } from '@/components/forms/client-template-form'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import { ClientTemplateType, useCreateClientTemplate, useModifyClientTemplate } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { Maximize2, Minimize2 } from 'lucide-react'
import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

const MonacoEditor = lazy(() => import('@monaco-editor/react'))
const MobileJsonAceEditor = lazy(() => import('@/components/common/mobile-json-ace-editor'))
const MobileYamlAceEditor = lazy(() => import('@/components/common/mobile-yaml-ace-editor'))

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

const monacoEditorOptions = {
  minimap: { enabled: false },
  fontSize: 13,
  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
  lineNumbers: 'on' as const,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  formatOnPaste: true,
  formatOnType: true,
  renderWhitespace: 'none' as const,
  wordWrap: 'on' as const,
  folding: true,
  scrollbar: {
    vertical: 'visible' as const,
    horizontal: 'visible' as const,
    useShadows: false,
    verticalScrollbarSize: 8,
    horizontalScrollbarSize: 8,
  },
}

export default function ClientTemplateModal({ isDialogOpen, onOpenChange, form, editingTemplate, editingTemplateId }: ClientTemplateModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const { resolvedTheme } = useTheme()
  const createClientTemplate = useCreateClientTemplate()
  const modifyClientTemplate = useModifyClientTemplate()
  const [isEditorExpanded, setIsEditorExpanded] = useState(false)
  const [validation, setValidation] = useState<ValidationResult>({ isValid: true })

  const templateType = form.watch('template_type')
  const isYaml = isYamlType(templateType)

  const validateContent = useCallback(
    (value: string) => {
      if (!value.trim()) {
        setValidation({ isValid: false, error: 'Content is required' })
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
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Invalid JSON'
        setValidation({ isValid: false, error: msg })
        return false
      }
    },
    [isYaml],
  )

  useEffect(() => {
    setValidation({ isValid: true })
  }, [templateType])

  useEffect(() => {
    if (!isDialogOpen) {
      setIsEditorExpanded(false)
      setValidation({ isValid: true })
    }
  }, [isDialogOpen])

  const handleSubmit = form.handleSubmit(async values => {
    const isContentYaml = isYamlType(values.template_type)

    let finalContent: string
    if (isContentYaml) {
      finalContent = values.content
    } else {
      try {
        finalContent = JSON.stringify(JSON.parse(values.content), null, 2)
      } catch {
        setValidation({ isValid: false, error: 'Invalid JSON' })
        toast.error('Invalid JSON content')
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

  const renderEditor = (field: { value: string; onChange: (v: string) => void }) => {
    const language = isYaml ? 'yaml' : 'json'
    const handleChange = (v: string) => {
      field.onChange(v)
      validateContent(v)
    }

    if (isMobile) {
      return isYaml ? (
        <Suspense fallback={<div className="h-full w-full" />}>
          <MobileYamlAceEditor value={field.value || ''} theme={resolvedTheme} onChange={handleChange} />
        </Suspense>
      ) : (
        <Suspense fallback={<div className="h-full w-full" />}>
          <MobileJsonAceEditor value={field.value || ''} theme={resolvedTheme} onChange={handleChange} />
        </Suspense>
      )
    }

    return (
      <Suspense fallback={<div className="h-full w-full" />}>
        <MonacoEditor
          height="100%"
          defaultLanguage={language}
          language={language}
          value={field.value}
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          onChange={v => handleChange(v ?? '')}
          options={monacoEditorOptions}
        />
      </Suspense>
    )
  }

  const title = editingTemplate ? t('clientTemplates.editTemplate', { defaultValue: 'Edit Client Template' }) : t('clientTemplates.addTemplate', { defaultValue: 'Add Client Template' })

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className={cn('flex h-[80dvh] max-h-[80dvh] w-[95vw] max-w-5xl flex-col gap-0 overflow-hidden p-0', dir === 'rtl' && 'rtl')}>
        <DialogHeader className="shrink-0 border-b px-5 py-4">
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 overflow-hidden">

            {/* ── Left panel: code editor ── */}
            <div className={cn('relative flex min-h-0 flex-col border-r transition-all duration-200', isMobile ? 'hidden' : isEditorExpanded ? 'w-full' : 'w-1/2')}>
              <div className="flex shrink-0 items-center justify-between border-b bg-muted/40 px-3 py-1.5">
                <span className="text-xs font-medium text-muted-foreground">
                  {t('clientTemplates.content', { defaultValue: 'Content' })}
                  <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">{isYaml ? 'YAML' : 'JSON'}</span>
                </span>
                <Button type="button" size="icon" variant="ghost" className="h-6 w-6" onClick={() => setIsEditorExpanded(v => !v)}>
                  {isEditorExpanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
                </Button>
              </div>
              <div className="min-h-0 flex-1" dir="ltr">
                <FormField
                  control={form.control}
                  name="content"
                  render={({ field }) => (
                    <FormItem className="h-full">
                      <FormControl className="h-full">
                        <div className="h-full" dir="ltr">{renderEditor(field)}</div>
                      </FormControl>
                      {!validation.isValid && validation.error && (
                        <div className="absolute bottom-2 left-2 right-2 rounded border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
                          {validation.error}
                        </div>
                      )}
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* ── Right panel: fields + submit ── */}
            <div className={cn('flex shrink-0 flex-col transition-all duration-200', isMobile ? 'w-full' : isEditorExpanded ? 'w-0 overflow-hidden' : 'w-1/2')}>
              <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-5">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('name')}</FormLabel>
                      <FormControl>
                        <Input {...field} placeholder={t('clientTemplates.namePlaceholder', { defaultValue: 'Template name' })} />
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
                    <FormItem className="flex items-center justify-between rounded-lg border p-3">
                      <FormLabel className="cursor-pointer">{t('clientTemplates.isDefault', { defaultValue: 'Set as default' })}</FormLabel>
                      <FormControl>
                        <Switch checked={!!field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />

                {/* Mobile-only editor */}
                {isMobile && (
                  <FormField
                    control={form.control}
                    name="content"
                    render={({ field }) => (
                      <FormItem className="flex flex-col">
                        <FormLabel>
                          {t('clientTemplates.content', { defaultValue: 'Content' })}
                          <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">{isYaml ? 'YAML' : 'JSON'}</span>
                        </FormLabel>
                        <FormControl>
                          <div className="overflow-hidden rounded-md border" dir="ltr" style={{ height: '250px' }}>
                            {renderEditor(field)}
                          </div>
                        </FormControl>
                        {!validation.isValid && validation.error && <FormMessage>{validation.error}</FormMessage>}
                      </FormItem>
                    )}
                  />
                )}
              </div>

              <div className="shrink-0 border-t p-4">
                <div className="flex gap-2">
                  <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)} disabled={isPending}>
                    {t('cancel')}
                  </Button>
                  <LoaderButton type="submit" className="flex-1" isLoading={isPending} loadingText={t('saving', { defaultValue: 'Saving...' })}>
                    {editingTemplate ? t('modify') : t('create')}
                  </LoaderButton>
                </div>
              </div>
            </div>

          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
