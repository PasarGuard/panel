import { useTheme } from '@/components/common/theme-provider'
import type { ClientTemplateFormValues } from '@/components/forms/client-template-form'
import { DEFAULT_TEMPLATE_CONTENT } from '@/components/forms/client-template-form'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
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
import { Pencil, FileCode2, Maximize2, Minimize2 } from 'lucide-react'
import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

const MonacoEditor = lazy(() => import('@/components/common/monaco-editor'))
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
  fontSize: 14,
  fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
  lineNumbers: 'on' as const,
  roundedSelection: true,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  formatOnPaste: true,
  formatOnType: true,
  renderWhitespace: 'none' as const,
  wordWrap: 'on' as const,
  folding: true,
  suggestOnTriggerCharacters: true,
  quickSuggestions: true,
  renderLineHighlight: 'all' as const,
  scrollbar: {
    vertical: 'visible' as const,
    horizontal: 'visible' as const,
    useShadows: false,
    verticalScrollbarSize: 10,
    horizontalScrollbarSize: 10,
  },
  contextmenu: true,
  copyWithSyntaxHighlighting: false,
  multiCursorModifier: 'alt' as const,
  accessibilitySupport: 'on' as const,
  mouseWheelZoom: true,
  quickSuggestionsDelay: 0,
  occurrencesHighlight: 'singleFile' as const,
  wordBasedSuggestions: 'currentDocument' as const,
  suggest: {
    showWords: true,
    showSnippets: true,
    showClasses: true,
    showFunctions: true,
    showVariables: true,
    showProperties: true,
    showColors: true,
    showFiles: true,
    showReferences: true,
    showFolders: true,
    showTypeParameters: true,
    showEnums: true,
    showConstructors: true,
    showDeprecated: true,
    showEnumMembers: true,
    showKeywords: true,
  },
} as const

export default function ClientTemplateModal({ isDialogOpen, onOpenChange, form, editingTemplate, editingTemplateId }: ClientTemplateModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const { resolvedTheme } = useTheme()
  const createClientTemplate = useCreateClientTemplate()
  const modifyClientTemplate = useModifyClientTemplate()
  const [isEditorFullscreen, setIsEditorFullscreen] = useState(false)
  const [isEditorReady, setIsEditorReady] = useState(false)
  const [editorInstance, setEditorInstance] = useState<any>(null)
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

  const relayoutEditor = useCallback(
    (editor = editorInstance) => {
      if (!editor) return
      if (typeof editor.layout === 'function') {
        editor.layout()
      }
      if (typeof editor.resize === 'function') {
        editor.resize()
      }
    },
    [editorInstance],
  )

  const handleToggleFullscreen = useCallback(() => {
    setIsEditorFullscreen(prev => {
      setTimeout(() => {
        relayoutEditor()
        window.dispatchEvent(new Event('resize'))
      }, 50)
      return !prev
    })
  }, [relayoutEditor])

  const handleEditorDidMount = useCallback(
    (editor: any) => {
      setIsEditorReady(true)
      setEditorInstance(editor)

      requestAnimationFrame(() => {
        relayoutEditor(editor)
        setTimeout(() => {
          relayoutEditor(editor)
        }, 100)
      })
    },
    [relayoutEditor],
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
      setIsEditorFullscreen(false)
      setValidation({ isValid: true })
    }
  }, [isDialogOpen])

  useEffect(() => {
    const handleResize = () => {
      setTimeout(() => {
        relayoutEditor()
      }, 100)
    }

    const handleOrientationChange = () => {
      setTimeout(() => {
        relayoutEditor()
      }, 300)
    }

    window.addEventListener('resize', handleResize)
    window.addEventListener('orientationchange', handleOrientationChange)

    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('orientationchange', handleOrientationChange)
    }
  }, [relayoutEditor])

  useEffect(() => {
    if (!editorInstance || !isEditorReady) return

    setTimeout(() => {
      relayoutEditor()
    }, 150)
  }, [editorInstance, isEditorFullscreen, isEditorReady, relayoutEditor])

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

  const renderEditor = (field: { value: string; onChange: (value: string) => void }, fullscreen = false) => {
    const language = isYaml ? 'yaml' : 'json'
    const handleChange = (value: string) => {
      field.onChange(value)
      validateContent(value)
    }

    if (isMobile) {
      return isYaml ? (
        <Suspense fallback={<div className="h-full w-full" />}>
          <MobileYamlAceEditor value={field.value || ''} theme={resolvedTheme} onChange={handleChange} onLoad={handleEditorDidMount} />
        </Suspense>
      ) : (
        <Suspense fallback={<div className="h-full w-full" />}>
          <MobileJsonAceEditor value={field.value || ''} theme={resolvedTheme} onChange={handleChange} onLoad={handleEditorDidMount} />
        </Suspense>
      )
    }

    return (
      <Suspense fallback={<div className="h-full w-full" />}>
        <MonacoEditor
          height={fullscreen ? '100%' : undefined}
          defaultLanguage={language}
          language={language}
          value={field.value}
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          onChange={value => handleChange(value ?? '')}
          onValidate={handleEditorValidation}
          onMount={handleEditorDidMount}
          options={monacoEditorOptions}
        />
      </Suspense>
    )
  }

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
                            <div
                              className={cn(
                                'relative flex flex-col rounded-lg border bg-background',
                                isEditorFullscreen ? 'fixed inset-0 z-[60] flex items-center justify-center' : 'h-[calc(50vh-1rem)] sm:h-[calc(55vh-1rem)] md:min-h-[450px]',
                              )}
                              dir="ltr"
                              style={
                                isEditorFullscreen
                                  ? {
                                    display: 'flex',
                                    flexDirection: 'column',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                  }
                                  : {
                                    display: 'flex',
                                    flexDirection: 'column',
                                  }
                              }
                            >
                              {isEditorFullscreen && <div className="absolute inset-0 bg-background/95 backdrop-blur-sm" onClick={handleToggleFullscreen} />}
                              {!isEditorReady && (
                                <div className="absolute inset-0 z-[70] flex items-center justify-center bg-background/80 backdrop-blur-sm">
                                  <span className="h-8 w-8 animate-spin rounded-full border-b-2 border-t-2 border-primary"></span>
                                </div>
                              )}

                              {isEditorFullscreen ? (
                                <div className="relative z-10 flex h-full w-full flex-col bg-background sm:my-8 sm:h-auto sm:w-full sm:max-w-[95vw] sm:rounded-lg sm:border sm:shadow-xl">
                                  <div className="hidden items-center justify-between rounded-t-lg border-b bg-background px-3 py-2.5 sm:flex">
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-medium">{title}</span>
                                    </div>
                                    <Button
                                      type="button"
                                      size="icon"
                                      variant="ghost"
                                      className="h-8 w-8 shrink-0"
                                      onClick={handleToggleFullscreen}
                                      aria-label={t('exitFullscreen', { defaultValue: 'Exit fullscreen' })}
                                    >
                                      <Minimize2 className="h-4 w-4" />
                                    </Button>
                                  </div>
                                  <Button
                                    type="button"
                                    size="icon"
                                    variant="default"
                                    className="absolute right-2 top-2 z-20 h-9 w-9 rounded-full shadow-lg sm:hidden"
                                    onClick={handleToggleFullscreen}
                                    aria-label={t('exitFullscreen', { defaultValue: 'Exit fullscreen' })}
                                  >
                                    <Minimize2 className="h-4 w-4" />
                                  </Button>
                                  <div className="relative h-full sm:h-[calc(100vh-160px)]" style={{ width: '100%' }}>
                                    {renderEditor(field, true)}
                                  </div>
                                </div>
                              ) : (
                                <>
                                  {!isEditorFullscreen && (
                                    <Button
                                      type="button"
                                      size="icon"
                                      variant="ghost"
                                      className="absolute right-2 top-2 z-10 bg-background/90 backdrop-blur-sm hover:bg-background/90"
                                      onClick={handleToggleFullscreen}
                                      aria-label={t('fullscreen', { defaultValue: 'Fullscreen' })}
                                    >
                                      <Maximize2 className="h-4 w-4" />
                                    </Button>
                                  )}
                                  <div className="relative min-h-0 flex-1" style={{ minHeight: 0 }}>
                                    {renderEditor(field)}
                                  </div>
                                </>
                              )}
                            </div>
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
                      <FormItem className="flex items-center justify-between rounded-lg border p-3">
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

            {!isEditorFullscreen && (
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
