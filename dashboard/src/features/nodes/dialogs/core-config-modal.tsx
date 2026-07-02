import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import { CopyButton } from '@/components/common/copy-button'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { DEFAULT_XRAY_CORE_CONFIG_JSON } from '@/lib/default-xray-core-config'
import {
  canGenerateShadowsocksPassword,
  createWireGuardCoreConfigJson,
  generateShadowsocksPassword as kitGenerateShadowsocksPassword,
  SHADOWSOCKS_PASSWORD_GENERATION_METHODS,
  type VlessBuilderOptions,
} from '@/lib/xray-generation'
import { cn } from '@/lib/utils'
import { findUnknownApiServices, getSelectedOptional, OPTIONAL_API_SERVICES, REQUIRED_API_SERVICES, setOptionalService } from '@/lib/xray-api-services'
import { useCreateCoreConfig, useModifyCoreConfig } from '@/service/api'
import { isEmptyObject } from '@/utils/isEmptyObject.ts'
import { generateMldsa65 } from '@/utils/mldsa65'
import { queryClient } from '@/utils/query-client'
import { generateWireGuardKeyPair } from '@/utils/wireguard'
import { encodeURLSafe } from '@stablelib/base64'
import { generateKeyPair } from '@stablelib/x25519'
import { debounce } from 'es-toolkit'
import { Sparkles, Pencil, Cpu } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FieldErrors, UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { CoreBackendType, CoreConfigFormValues } from '@/features/nodes/forms/core-config-form'
import { VlessAdvancedGenerationModal, type VlessKeyVariant } from '@/features/core-editor/components/shared/vless-advanced-generation-modal'
import { XrayInboundTagPicker } from '@/features/core-editor/components/shared/xray-inbound-tag-selectors'

interface CoreConfigModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<CoreConfigFormValues>
  editingCore: boolean
  editingCoreId?: number
}

interface ValidationResult {
  isValid: boolean
  error?: string
}

type DataFieldProps = {
  label: string
  value: string
  statusColor: string
  copiedMessage: string
  defaultMessage: string
}

export default function CoreConfigModal({ isDialogOpen, onOpenChange, form, editingCore, editingCoreId }: CoreConfigModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const backendType = (form.watch('type') ?? 'xray') as CoreBackendType
  const isXrayBackend = backendType !== 'wg'
  const [validation, setValidation] = useState<ValidationResult>({ isValid: true })
  const createCoreMutation = useCreateCoreConfig()
  const modifyCoreMutation = useModifyCoreConfig()
  const [isCodeEditorFullscreen, setIsCodeEditorFullscreen] = useState(false)
  const [inboundTags, setInboundTags] = useState<string[]>([])
  const [isGeneratingKeyPair, setIsGeneratingKeyPair] = useState(false)
  const [isGeneratingShortId, setIsGeneratingShortId] = useState(false)
  const [selectedEncryptionMethod, setSelectedEncryptionMethod] = useState<string>(SHADOWSOCKS_PASSWORD_GENERATION_METHODS[0])
  const [isGeneratingShadowsocksPassword, setIsGeneratingShadowsocksPassword] = useState(false)
  const [isGeneratingMldsa65, setIsGeneratingMldsa65] = useState(false)
  const [selectedVlessVariant, setSelectedVlessVariant] = useState<VlessKeyVariant>('x25519')
  const [vlessAdvancedSeed, setVlessAdvancedSeed] = useState<VlessBuilderOptions | undefined>(undefined)
  const [isVlessAdvancedModalOpen, setIsVlessAdvancedModalOpen] = useState(false)
  const [discardChangesOpen, setDiscardChangesOpen] = useState(false)

  // Results dialog state
  const [isResultsDialogOpen, setIsResultsDialogOpen] = useState(false)
  const [resultType, setResultType] = useState<string | null>(null)
  const [resultData, setResultData] = useState<any>(null)

  // Store generated values
  const [generatedKeyPair, setGeneratedKeyPair] = useState<{ publicKey: string; privateKey: string } | null>(null)
  const [generatedWireGuardKeyPair, setGeneratedWireGuardKeyPair] = useState<{ publicKey: string; privateKey: string } | null>(null)
  const [generatedShortId, setGeneratedShortId] = useState<string | null>(null)
  const [generatedShadowsocksPassword, setGeneratedShadowsocksPassword] = useState<{ password: string; encryptionMethod: string } | null>(null)
  const [generatedMldsa65, setGeneratedMldsa65] = useState<{ seed: string; verify: string } | null>(null)
  const [generatedVLESS, setGeneratedVLESS] = useState<any>(null)

  // Helper function to show results in dialog
  const showResultDialog = useCallback((type: string, data: any) => {
    setResultType(type)
    setResultData(data)
    setIsResultsDialogOpen(true)
  }, [])

  const validateJsonContent = useCallback((value: string, showToast = false) => {
    try {
      JSON.parse(value)
      setValidation({ isValid: true })
      return true
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Invalid JSON'
      setValidation({
        isValid: false,
        error: errorMessage,
      })
      if (showToast) {
        toast.error(errorMessage, {
          duration: 3000,
        })
      }
      return false
    }
  }, [])

  const handleEditorValidation = useCallback(
    (markers: any[]) => {
      // Monaco editor provides validation markers
      const hasErrors = markers.length > 0
      if (hasErrors) {
        setValidation({
          isValid: false,
          error: markers[0].message,
        })
        toast.error(markers[0].message, {
          duration: 3000,
        })
      } else {
        validateJsonContent(form.getValues().config, true)
      }
    },
    [form, validateJsonContent],
  )

  const handleAceEditorChange = useCallback(
    (value: string, onChange: (value: string) => void) => {
      onChange(value)
      validateJsonContent(value)
    },
    [validateJsonContent],
  )

  // Optional Xray API services derived from the config JSON (the JSON is the source of truth).
  const watchedConfig = form.watch('config')
  const { selectedApiServices, unknownApiServices } = useMemo(() => {
    let parsed: unknown = null
    try {
      parsed = JSON.parse(watchedConfig || '{}')
    } catch {
      parsed = null
    }
    return {
      selectedApiServices: getSelectedOptional(parsed),
      unknownApiServices: findUnknownApiServices(parsed),
    }
  }, [watchedConfig])

  const handleToggleApiService = useCallback(
    (service: string, enabled: boolean) => {
      let parsed: Record<string, unknown>
      try {
        parsed = JSON.parse(form.getValues('config') || '{}') as Record<string, unknown>
      } catch {
        return
      }
      const nextJson = JSON.stringify(setOptionalService(parsed, service, enabled), null, 2)
      form.setValue('config', nextJson, { shouldDirty: true, shouldValidate: true })
      // ponytail: re-serializing pretty-prints the whole config (2-space) and normalizes
      // number literals — accepted per the "edit api.services in the JSON" design;
      // setOptionalService preserves all other keys.
      validateJsonContent(nextJson)
    },
    [form, validateJsonContent],
  )

  const apiServicesUnknownMessage = (names: string[]) =>
    t('coreConfigModal.apiServicesUnknown', {
      defaultValue: 'Unrecognized API service(s): {{names}}. Remove or fix them to save.',
      names: names.join(', '),
    })

  // Debounce config changes to improve performance
  const debouncedConfigChange = useCallback(
    debounce((value: string) => {
      try {
        const parsedConfig = JSON.parse(value)
        const selectedBackendType = (form.getValues('type') ?? 'xray') as CoreBackendType
        if (selectedBackendType === 'wg') {
          const interfaceName = typeof parsedConfig.interface_name === 'string' ? parsedConfig.interface_name.trim() : ''
          setInboundTags(interfaceName ? [interfaceName] : [])
        } else if (parsedConfig.inbounds && Array.isArray(parsedConfig.inbounds)) {
          const tags = parsedConfig.inbounds.filter((inbound: any) => typeof inbound.tag === 'string' && inbound.tag.trim() !== '').map((inbound: any) => inbound.tag)
          setInboundTags(tags)
        } else {
          setInboundTags([])
        }
      } catch {
        setInboundTags([])
      }
    }, 300),
    [form],
  )

  // Extract inbound tags from config JSON whenever config changes
  useEffect(() => {
    const configValue = form.getValues().config
    if (configValue) {
      debouncedConfigChange(configValue)
    }
  }, [form.watch('config'), backendType, debouncedConfigChange])

  const generatePrivateAndPublicKey = async () => {
    try {
      setIsGeneratingKeyPair(true)
      const keyPair = generateKeyPair()
      const formattedKeyPair = {
        privateKey: encodeURLSafe(keyPair.secretKey).replace(/=/g, '').replace(/\n/g, ''),
        publicKey: encodeURLSafe(keyPair.publicKey).replace(/=/g, '').replace(/\n/g, ''),
      }
      setGeneratedKeyPair(formattedKeyPair)
      showResultDialog('keyPair', formattedKeyPair)
      toast.success(t('coreConfigModal.keyPairGenerated'))
    } catch (error) {
      toast.error(t('coreConfigModal.keyPairGenerationFailed'))
    } finally {
      setIsGeneratingKeyPair(false)
    }
  }

  const generateShortId = async () => {
    try {
      setIsGeneratingShortId(true)
      const randomBytes = new Uint8Array(8)
      crypto.getRandomValues(randomBytes)
      const shortId = Array.from(randomBytes)
        .map(byte => byte.toString(16).padStart(2, '0'))
        .join('')
      setGeneratedShortId(shortId)
      showResultDialog('shortId', { shortId })
      toast.success(t('coreConfigModal.shortIdGenerated'))
    } catch (error) {
      toast.error(t('coreConfigModal.shortIdGenerationFailed'))
    } finally {
      setIsGeneratingShortId(false)
    }
  }
  const generateShadowsocksPassword = async (value: string) => {
    if (!canGenerateShadowsocksPassword(value)) {
      toast.error(t('coreConfigModal.shadowsocksPasswordGenerationFailed'))
      return
    }
    try {
      setIsGeneratingShadowsocksPassword(true)
      const result = kitGenerateShadowsocksPassword(value)
      if (!result) return

      setGeneratedShadowsocksPassword({ password: result.password, encryptionMethod: result.encryptionMethod })
      showResultDialog('shadowsocksPassword', { password: result.password, encryptionMethod: result.encryptionMethod })
      toast.success(t('coreConfigModal.shadowsocksPasswordGenerated'))
    } catch (error) {
      toast.error(t('coreConfigModal.shadowsocksPasswordGenerationFailed'))
    } finally {
      setIsGeneratingShadowsocksPassword(false)
    }
  }
  const handleGenerateMldsa65 = async () => {
    try {
      setIsGeneratingMldsa65(true)
      const result = await generateMldsa65()
      setGeneratedMldsa65(result)
      showResultDialog('mldsa65', result)
      toast.success(t('coreConfigModal.mldsa65Generated'))
    } catch (error) {
      const message = error instanceof Error ? error.message : t('coreConfigModal.mldsa65GenerationFailed', { defaultValue: 'Failed to generate ML-DSA-65 keys' })
      toast.error(message)
    } finally {
      setIsGeneratingMldsa65(false)
    }
  }
  const applyBackendTemplate = useCallback(
    (nextBackendType: CoreBackendType) => {
      let defaultTemplate: string
      if (nextBackendType === 'wg') {
        const keyPair = generateWireGuardKeyPair()
        setGeneratedWireGuardKeyPair(keyPair)
        defaultTemplate = createWireGuardCoreConfigJson(keyPair)
      } else {
        defaultTemplate = DEFAULT_XRAY_CORE_CONFIG_JSON
      }
      form.setValue('config', defaultTemplate, { shouldDirty: true, shouldValidate: true })
      validateJsonContent(defaultTemplate)
      debouncedConfigChange(defaultTemplate)
    },
    [debouncedConfigChange, form, validateJsonContent],
  )

  const generateWireGuardKeys = useCallback(() => {
    try {
      const keyPair = generateWireGuardKeyPair()
      setGeneratedWireGuardKeyPair(keyPair)
      showResultDialog('wireguardKeyPair', keyPair)
      toast.success(t('coreConfigModal.wireguardKeyPairGenerated', { defaultValue: 'WireGuard keypair generated' }))
    } catch (error) {
      toast.error(t('coreConfigModal.wireguardKeyPairGenerationFailed', { defaultValue: 'Failed to generate WireGuard keypair' }))
    }
  }, [showResultDialog, t])

  const viewWireGuardKeys = useCallback(() => {
    if (generatedWireGuardKeyPair) {
      showResultDialog('wireguardKeyPair', generatedWireGuardKeyPair)
      return
    }

    generateWireGuardKeys()
  }, [generateWireGuardKeys, generatedWireGuardKeyPair, showResultDialog])

  const closeModal = useCallback(() => {
    setDiscardChangesOpen(false)
    onOpenChange(false)
  }, [onOpenChange])

  const handleDialogOpenChange = useCallback(
    (open: boolean) => {
      if (open) {
        onOpenChange(true)
        return
      }
      if (createCoreMutation.isPending || modifyCoreMutation.isPending || form.formState.isSubmitting) return
      if (form.formState.isDirty) {
        setDiscardChangesOpen(true)
        return
      }
      closeModal()
    },
    [closeModal, createCoreMutation.isPending, form.formState.isDirty, form.formState.isSubmitting, modifyCoreMutation.isPending, onOpenChange],
  )

  const confirmDiscardChanges = useCallback(() => {
    form.reset()
    closeModal()
  }, [closeModal, form])

  const onSubmit = async (values: CoreConfigFormValues) => {
    try {
      const coreName = values.name.trim()
      // Validate JSON first
      let configObj
      try {
        configObj = JSON.parse(values.config)
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : 'Invalid JSON'
        form.setError('config', {
          type: 'manual',
          message: errorMessage,
        })
        toast.error(errorMessage)
        return
      }

      const unknownServices = findUnknownApiServices(configObj)
      if (unknownServices.length > 0) {
        const message = apiServicesUnknownMessage(unknownServices)
        form.setError('config', { type: 'manual', message })
        toast.error(message)
        return
      }

      const backendType = values.type ?? 'xray'
      const fallbackTags = backendType !== 'wg' ? values.fallback_id || [] : []
      const excludeInboundTags = backendType !== 'wg' ? values.excluded_inbound_ids || [] : []

      if (editingCore && editingCoreId) {
        // Update existing core
        await modifyCoreMutation.mutateAsync({
          coreId: editingCoreId,
          data: {
            name: coreName,
            type: backendType,
            config: configObj,
            fallbacks_inbound_tags: fallbackTags,
            exclude_inbound_tags: excludeInboundTags,
          },
          params: {
            restart_nodes: values.restart_nodes ?? true,
          },
        })
      } else {
        // Create new core
        await createCoreMutation.mutateAsync({
          data: {
            name: coreName,
            type: backendType,
            config: configObj,
            fallbacks_inbound_tags: fallbackTags,
            exclude_inbound_tags: excludeInboundTags,
          },
        })
      }

      toast.success(
        t(editingCore ? 'coreConfigModal.editSuccess' : 'coreConfigModal.createSuccess', {
          name: coreName,
        }),
      )

      // Invalidate core config queries after successful action
      queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
      queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
      form.reset({ ...values, name: coreName })
      closeModal()
    } catch (error: any) {
      console.error('Core config operation failed:', error)
      console.error('Error response:', error?.response)
      // Error data logging removed

      // Reset all previous errors first
      form.clearErrors()

      // Handle validation errors
      if (error?.response?._data && !isEmptyObject(error?.response?._data)) {
        // For zod validation errors
        const fields = ['name', 'type', 'config', 'fallback_id', 'excluded_inbound_ids']

        // Show first error in a toast
        if (error?.response?._data?.detail) {
          const detail = error?.response?._data?.detail
          // If detail is an object with field errors (e.g., { status: "some error" })
          if (typeof detail === 'object' && detail !== null && !Array.isArray(detail)) {
            // Set errors for all fields in the object
            const firstField = Object.keys(detail)[0]
            const firstMessage = detail[firstField]

            Object.entries(detail).forEach(([field, message]) => {
              if (fields.includes(field)) {
                form.setError(field as any, {
                  type: 'manual',
                  message:
                    typeof message === 'string'
                      ? message
                      : t('validation.invalid', {
                          field: t(`coreConfigModal.${field}`, { defaultValue: field }),
                          defaultValue: `${field} is invalid`,
                        }),
                })
              }
            })

            toast.error(
              firstMessage ||
                t('validation.invalid', {
                  field: t(`coreConfigModal.${firstField}`, { defaultValue: firstField }),
                  defaultValue: `${firstField} is invalid`,
                }),
            )
          } else if (typeof detail === 'string' && !Array.isArray(detail)) {
            toast.error(detail)
          }
        }
      } else if (error?.response?.data) {
        // Handle API errors
        const apiError = error.response?.data
        let errorMessage = ''

        if (typeof apiError === 'string') {
          errorMessage = apiError
        } else if (apiError?.detail) {
          if (Array.isArray(apiError.detail)) {
            // Handle array of field errors
            apiError.detail.forEach((err: any) => {
              if (err.loc && err.loc[1]) {
                const fieldName = err.loc[1]
                form.setError(fieldName as any, {
                  type: 'manual',
                  message: err.msg,
                })
              }
            })
            errorMessage = apiError.detail[0]?.msg || 'Validation error'
          } else if (typeof apiError.detail === 'string') {
            errorMessage = apiError.detail
          } else {
            errorMessage = 'Validation error'
          }
        } else if (apiError?.message) {
          errorMessage = apiError.message
        } else {
          errorMessage = 'An unexpected error occurred'
        }

        toast.error(errorMessage)
      } else {
        // Generic error handling
        toast.error(error?.message || t('coreConfigModal.genericError', { defaultValue: 'An error occurred' }))
      }
    }
  }

  const onInvalidSubmit = useCallback(
    (errors: FieldErrors<CoreConfigFormValues>) => {
      const message =
        typeof errors.name?.message === 'string'
          ? errors.name.message
          : typeof errors.config?.message === 'string'
            ? errors.config.message
            : t('coreConfigModal.nameRequired', { defaultValue: 'Core name is required' })
      toast.error(message)
    },
    [t],
  )

  // Initialize form fields when modal opens
  useEffect(() => {
    if (isDialogOpen) {
      if (!editingCore) {
        // Reset form for new core
        form.reset({
          name: '',
          type: 'xray',
          config: DEFAULT_XRAY_CORE_CONFIG_JSON,
          excluded_inbound_ids: [],
          fallback_id: [],
          restart_nodes: true,
        })
      } else {
        // Set restart_nodes to true for editing
        form.setValue('restart_nodes', true)
        if (!form.getValues('type')) {
          form.setValue('type', 'xray')
        }
      }

      // Force editor resize on mobile after modal opens
      // This ensures the editor properly renders on first load
      setTimeout(() => {
        const editorSelector = isMobile ? '.ace_editor' : '.monaco-editor'
        const editorElement = document.querySelector(editorSelector)
        if (editorElement) {
          // Trigger a resize event
          window.dispatchEvent(new Event('resize'))
        }
      }, 300)
    }
  }, [isDialogOpen, editingCore, form, isMobile])

  // Cleanup on modal close
  useEffect(() => {
    if (!isDialogOpen) {
      setIsCodeEditorFullscreen(false)
      setIsResultsDialogOpen(false)
      setResultType(null)
      setResultData(null)
      setSelectedVlessVariant('x25519')
      setValidation({ isValid: true })
      // Don't clear generated values - keep them for reuse
    }
  }, [isDialogOpen])

  // Helper functions to view stored values
  const viewKeyPair = () => {
    if (generatedKeyPair) {
      showResultDialog('keyPair', generatedKeyPair)
    } else {
      generatePrivateAndPublicKey()
    }
  }

  const viewShortId = () => {
    if (generatedShortId) {
      showResultDialog('shortId', { shortId: generatedShortId })
    } else {
      generateShortId()
    }
  }

  const viewShadowsocksPassword = () => {
    if (generatedShadowsocksPassword && canGenerateShadowsocksPassword(selectedEncryptionMethod)) {
      showResultDialog('shadowsocksPassword', generatedShadowsocksPassword)
    } else {
      generateShadowsocksPassword(selectedEncryptionMethod)
    }
  }

  const viewMldsa65 = () => {
    if (generatedMldsa65) {
      showResultDialog('mldsa65', generatedMldsa65)
    } else {
      handleGenerateMldsa65()
    }
  }

  const viewVLESS = () => {
    if (generatedVLESS) {
      showResultDialog('vlessEncryption', generatedVLESS)
    } else {
      setVlessAdvancedSeed(undefined)
      setIsVlessAdvancedModalOpen(true)
    }
  }

  // Add this CSS somewhere in your styles (you might need to create a new CSS file or add to existing one)
  const styles = `
    .monaco-editor-mobile .monaco-menu {
        background-color: var(--background) !important;
    }

    .monaco-editor-mobile .monaco-menu .action-item {
        background-color: var(--background) !important;
    }

    .monaco-editor-mobile .monaco-menu .action-item:hover {
        background-color: var(--muted) !important;
    }

    .monaco-editor-mobile .monaco-menu .action-item.disabled {
        opacity: 0.5;
    }

    .monaco-editor-mobile .monaco-menu .action-item .action-label {
        color: var(--foreground) !important;
    }

    .monaco-editor-mobile .monaco-menu .action-item:hover .action-label {
        color: var(--foreground) !important;
    }
    `

  // Add this useEffect to inject the styles
  useEffect(() => {
    if (isMobile) return
    const styleElement = document.createElement('style')
    styleElement.textContent = styles
    document.head.appendChild(styleElement)
    return () => {
      document.head.removeChild(styleElement)
    }
  }, [isMobile])

  // Handle Monaco Editor web component registration errors
  useEffect(() => {
    if (isMobile) return
    const originalError = console.error
    console.error = (...args) => {
      // Suppress the specific web component registration error
      if (args[0]?.message?.includes('custom element with name') && args[0]?.message?.includes('has already been defined')) {
        return
      }
      originalError.apply(console, args)
    }

    return () => {
      console.error = originalError
    }
  }, [isMobile])

  // Results Dialog Component
  // Reusable components for cleaner code
  const StatusIndicator = ({ color }: { color: string }) => <div className={`h-1.5 w-1.5 shrink-0 rounded-full ${color}`} aria-hidden="true" />

  const SectionLabel = ({ children }: { children: React.ReactNode }) => <p className="text-muted-foreground truncate text-[10px] font-semibold tracking-wide sm:text-xs">{children}</p>

  const CodeBlock = ({ value }: { value: string }) => (
    <div dir="ltr" className="group bg-background/80 relative min-w-0 flex-1 rounded-md border backdrop-blur-sm">
      <code className="block w-full min-w-0 overflow-x-auto px-3 py-2.5 font-mono text-xs leading-relaxed whitespace-nowrap">{value}</code>
    </div>
  )

  const DataField = ({ label, value, statusColor, copiedMessage, defaultMessage }: DataFieldProps) => (
    <div className="space-y-1.5 sm:space-y-2">
      <div className="flex min-w-0 items-center gap-1.5 sm:gap-2">
        <StatusIndicator color={statusColor} />
        <SectionLabel>{label}</SectionLabel>
      </div>
      <div dir="ltr" className="flex min-w-0 items-center gap-2">
        <CodeBlock value={value} />
        <CopyButton value={value} icon="copy" copiedMessage={copiedMessage} defaultMessage={defaultMessage} className="h-8 w-8 shrink-0 text-xs sm:h-9 sm:w-9 sm:text-sm" />
      </div>
    </div>
  )

  // Main render function
  const renderResultDialog = () => {
    if (!resultType || !resultData) return null

    const renderContent = () => {
      switch (resultType) {
        case 'keyPair':
          return (
            <div className="space-y-4">
              <DataField
                label={t('coreConfigModal.publicKey')}
                value={resultData.publicKey || ''}
                statusColor="bg-green-500"
                copiedMessage="coreConfigModal.publicKeyCopied"
                defaultMessage="coreConfigModal.copyPublicKey"
              />
              <DataField
                label={t('coreConfigModal.privateKey')}
                value={resultData.privateKey || ''}
                statusColor="bg-amber-500"
                copiedMessage="coreConfigModal.privateKeyCopied"
                defaultMessage="coreConfigModal.copyPrivateKey"
              />
            </div>
          )

        case 'wireguardKeyPair':
          return (
            <div className="space-y-4">
              <DataField
                label={t('coreConfigModal.publicKey', { defaultValue: 'Public key' })}
                value={resultData.publicKey || ''}
                statusColor="bg-green-500"
                copiedMessage="coreConfigModal.publicKeyCopied"
                defaultMessage="coreConfigModal.copyPublicKey"
              />
              <DataField
                label={t('coreConfigModal.privateKey', { defaultValue: 'Private key' })}
                value={resultData.privateKey || ''}
                statusColor="bg-amber-500"
                copiedMessage="coreConfigModal.privateKeyCopied"
                defaultMessage="coreConfigModal.copyPrivateKey"
              />
            </div>
          )

        case 'shortId':
          return (
            <DataField
              label={t('coreConfigModal.shortId')}
              value={resultData.shortId || ''}
              statusColor="bg-cyan-500"
              copiedMessage="coreConfigModal.shortIdCopied"
              defaultMessage="coreConfigModal.copyShortId"
            />
          )

        case 'shadowsocksPassword':
          return (
            <div>
              <DataField
                label={t('coreConfigModal.shadowsocksPassword')}
                value={resultData.password || ''}
                statusColor="bg-orange-500"
                copiedMessage="coreConfigModal.shadowsocksPasswordCopied"
                defaultMessage="coreConfigModal.copyShadowsocksPassword"
              />
            </div>
          )

        case 'mldsa65':
          return (
            <div className="space-y-4">
              <DataField
                label={t('coreConfigModal.mldsa65Seed')}
                value={resultData.seed || ''}
                statusColor="bg-blue-500"
                copiedMessage="coreConfigModal.mldsa65SeedCopied"
                defaultMessage="coreConfigModal.copyMldsa65Seed"
              />
              <DataField
                label={t('coreConfigModal.mldsa65Verify')}
                value={resultData.verify || ''}
                statusColor="bg-purple-500"
                copiedMessage="coreConfigModal.mldsa65VerifyCopied"
                defaultMessage="coreConfigModal.copyMldsa65Verify"
              />
            </div>
          )

        case 'vlessEncryption': {
          const currentValues = selectedVlessVariant === 'x25519' ? resultData.x25519 : resultData.mlkem768

          if (!currentValues) return null

          return (
            <div className="space-y-4">
              <DataField
                label={t('coreConfigModal.decryption')}
                value={currentValues.decryption}
                statusColor="bg-emerald-500"
                copiedMessage="coreConfigModal.decryptionCopied"
                defaultMessage="coreConfigModal.copyDecryption"
              />
              <DataField
                label={t('coreConfigModal.encryption')}
                value={currentValues.encryption}
                statusColor="bg-violet-500"
                copiedMessage="coreConfigModal.encryptionCopied"
                defaultMessage="coreConfigModal.copyEncryption"
              />
            </div>
          )
        }

        default:
          return null
      }
    }

    return (
      <Dialog open={isResultsDialogOpen} onOpenChange={setIsResultsDialogOpen}>
        <DialogContent className="max-h-[95vh] w-[95vw] max-w-2xl min-w-0 overflow-x-hidden overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5 shrink-0 sm:h-5 sm:w-5" />
              <span className="truncate">{t('coreConfigModal.result', { defaultValue: 'Result' })}</span>
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[70vh] min-w-0 space-y-3 overflow-x-hidden overflow-y-auto pr-1 sm:space-y-4">{renderContent()}</div>
          <DialogFooter>
            <div className="flex w-full gap-2 sm:w-auto">
              <Button
                variant="outline"
                onClick={() => {
                  switch (resultType) {
                    case 'keyPair':
                      generatePrivateAndPublicKey()
                      break
                    case 'wireguardKeyPair':
                      generateWireGuardKeys()
                      break
                    case 'shortId':
                      generateShortId()
                      break
                    case 'shadowsocksPassword':
                      generateShadowsocksPassword(selectedEncryptionMethod)
                      break
                    case 'mldsa65':
                      handleGenerateMldsa65()
                      break
                    case 'vlessEncryption':
                      if (generatedVLESS?.options) {
                        setVlessAdvancedSeed({ ...generatedVLESS.options })
                      }
                      setIsVlessAdvancedModalOpen(true)
                      setIsResultsDialogOpen(false)
                      break
                  }
                }}
                className="h-8 w-full text-xs sm:h-10 sm:w-auto sm:text-sm"
              >
                {t('coreConfigModal.regenerate')}
              </Button>
              <Button onClick={() => setIsResultsDialogOpen(false)} className="h-8 w-full text-xs sm:h-10 sm:w-auto sm:text-sm">
                {t('close')}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <>
      <VlessAdvancedGenerationModal
        open={isVlessAdvancedModalOpen}
        onOpenChange={setIsVlessAdvancedModalOpen}
        seedOptions={vlessAdvancedSeed}
        seedVariant={selectedVlessVariant}
        onSuccess={({ result, variant }) => {
          setGeneratedVLESS(result)
          setSelectedVlessVariant(variant)
          showResultDialog('vlessEncryption', result)
          toast.success(t('coreConfigModal.vlessEncryptionGenerated'))
        }}
      />
      {renderResultDialog()}
      <Dialog open={isDialogOpen} onOpenChange={handleDialogOpenChange}>
        <DialogContent className="h-full w-full max-w-5xl md:h-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {editingCore ? <Pencil className="h-5 w-5" /> : <Cpu className="h-5 w-5" />}
              <span>{editingCore ? t('coreConfigModal.editCore') : t('coreConfigModal.addConfig')}</span>
            </DialogTitle>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit, onInvalidSubmit)} className="space-y-4">
              <div className="-mr-4 max-h-[78dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
                <div className="grid grid-cols-1 gap-4 md:h-full md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:gap-6">
                  <div className="flex flex-col">
                    <div className="flex flex-col space-y-4 md:h-full">
                      {/* Form: Core configuration JSON */}
                      <FormField
                        control={form.control}
                        name="config"
                        render={({ field }) => (
                          <FormItem className="md:flex md:h-full md:flex-col">
                            <FormControl className="md:flex md:flex-1">
                              <CodeEditorPanel
                                value={field.value || ''}
                                language="json"
                                onChange={value => handleAceEditorChange(value, field.onChange)}
                                onValidate={handleEditorValidation}
                                enableFullscreen
                                dialogOpen={isDialogOpen}
                                onFullscreenChange={setIsCodeEditorFullscreen}
                                embeddedContainerClassName="h-[calc(50vh-1rem)] sm:h-[calc(55vh-1rem)] md:h-[600px]"
                              />
                            </FormControl>
                            {validation.error && !validation.isValid && <FormMessage>{validation.error}</FormMessage>}
                          </FormItem>
                        )}
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    {/* Form: Core display name */}
                    <FormField
                      control={form.control}
                      name="name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('coreConfigModal.name')}</FormLabel>
                          <FormControl>
                            <Input
                              isError={!!form.formState.errors.name}
                              placeholder={form.formState.errors.name ? t('coreConfigModal.nameRequired', { defaultValue: 'Core name is required' }) : t('coreConfigModal.namePlaceholder')}
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="type"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('coreConfigModal.backendType', { defaultValue: 'Type' })}</FormLabel>
                          <FormControl>
                            <Select
                              value={field.value ?? 'xray'}
                              onValueChange={value => {
                                const nextBackendType = value as CoreBackendType
                                field.onChange(nextBackendType)
                                form.setValue('fallback_id', [], { shouldDirty: true })
                                form.setValue('excluded_inbound_ids', [], { shouldDirty: true })
                                applyBackendTemplate(nextBackendType)
                              }}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={t('coreConfigModal.backendType', { defaultValue: 'Type' })} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="xray">Xray</SelectItem>
                                <SelectItem value="wg">WireGuard</SelectItem>
                              </SelectContent>
                            </Select>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <div>
                      {!isXrayBackend && (
                        <LoaderButton type="button" onClick={viewWireGuardKeys} className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11" isLoading={false}>
                          <span className="flex items-center gap-2 truncate">
                            {generatedWireGuardKeyPair && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                            {t('coreConfigModal.generateWireGuardKeyPair', { defaultValue: 'Generate WireGuard keypair' })}
                          </span>
                        </LoaderButton>
                      )}
                    </div>

                    {isXrayBackend && (
                      <>
                        <FormField
                          control={form.control}
                          name="fallback_id"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('coreConfigModal.fallback')}</FormLabel>
                              <XrayInboundTagPicker
                                inboundTags={inboundTags}
                                value={field.value ?? []}
                                onChange={field.onChange}
                                emptyHint={t('coreConfigModal.selectFallback')}
                                placeholder={t('coreConfigModal.selectFallback')}
                                clearAllLabel={t('coreConfigModal.clearAllFallbacks')}
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="excluded_inbound_ids"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('coreConfigModal.excludedInbound')}</FormLabel>
                              <XrayInboundTagPicker
                                inboundTags={inboundTags}
                                value={field.value ?? []}
                                onChange={field.onChange}
                                emptyHint={t('coreConfigModal.selectInbound')}
                                placeholder={t('coreConfigModal.selectInbound')}
                                clearAllLabel={t('coreConfigModal.clearAllExcluded')}
                              />
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        {/* API services: opt into optional Xray API services.
                            The node always injects the required ones regardless. */}
                        <div className="space-y-2">
                          <FormLabel>{t('coreConfigModal.apiServices', { defaultValue: 'API Services' })}</FormLabel>
                          <div className="space-y-2 rounded-md border p-3">
                            {REQUIRED_API_SERVICES.map(svc => (
                              <label key={svc} className="flex items-center gap-2 opacity-60">
                                <Checkbox checked disabled />
                                <span className="text-sm">{svc}</span>
                                <span className="text-muted-foreground text-xs">
                                  {t('coreConfigModal.apiServiceAlwaysOn', { defaultValue: 'always on' })}
                                </span>
                              </label>
                            ))}
                            {OPTIONAL_API_SERVICES.map(svc => (
                              <label key={svc} className="flex cursor-pointer items-center gap-2">
                                <Checkbox
                                  checked={selectedApiServices.includes(svc)}
                                  onCheckedChange={checked => handleToggleApiService(svc, checked === true)}
                                  disabled={!validation.isValid}
                                />
                                <span className="text-sm">{svc}</span>
                              </label>
                            ))}
                            {unknownApiServices.length > 0 && (
                              <p className="text-destructive text-xs">{apiServicesUnknownMessage(unknownApiServices)}</p>
                            )}
                          </div>
                        </div>

                        <Tabs dir={dir} defaultValue="reality" className="w-full pb-6">
                          {/* Enhanced TabsList with Text Overflow */}
                          <TabsList dir="ltr" className="bg-muted/50 grid h-auto w-full grid-cols-3 gap-1 p-1">
                            <TabsTrigger
                              value="reality"
                              className="data-[state=active]:bg-background min-w-0 truncate px-2 py-2.5 text-xs font-medium transition-all data-[state=active]:shadow-sm sm:text-sm"
                            >
                              Reality
                            </TabsTrigger>

                            <TabsTrigger
                              value="shadowsocks"
                              className="data-[state=active]:bg-background min-w-0 truncate px-2 py-2.5 text-xs font-medium transition-all data-[state=active]:shadow-sm sm:text-sm"
                            >
                              ShadowSocks
                            </TabsTrigger>

                            <TabsTrigger
                              value="vless"
                              className="data-[state=active]:bg-background min-w-0 truncate px-2 py-2.5 text-xs font-medium transition-all data-[state=active]:shadow-sm sm:text-sm"
                            >
                              VLESS
                            </TabsTrigger>
                          </TabsList>

                          {/* ============================================
          Reality TAB
      ============================================ */}
                          <TabsContent value="reality" className="animate-in fade-in-50 mt-3 space-y-3 duration-300">
                            {/* Action Buttons */}
                            <div className="grid gap-2 sm:grid-cols-2 sm:gap-3">
                              <LoaderButton
                                type="button"
                                onClick={viewKeyPair}
                                className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                isLoading={isGeneratingKeyPair}
                                loadingText={t('coreConfigModal.generatingKeyPair')}
                              >
                                <span className="flex items-center gap-2 truncate">
                                  {generatedKeyPair && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                                  {t('coreConfigModal.generateKeyPair')}
                                </span>
                              </LoaderButton>

                              <LoaderButton
                                type="button"
                                onClick={viewShortId}
                                className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                isLoading={isGeneratingShortId}
                                loadingText={t('coreConfigModal.generatingShortId')}
                              >
                                <span className="flex items-center gap-2 truncate">
                                  {generatedShortId && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                                  {t('coreConfigModal.generateShortId')}
                                </span>
                              </LoaderButton>

                              <LoaderButton
                                type="button"
                                onClick={viewMldsa65}
                                className="col-span-2 h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                isLoading={isGeneratingMldsa65}
                                loadingText={t('coreConfigModal.generatingMldsa65')}
                              >
                                <span className="flex items-center gap-2 truncate">
                                  {generatedMldsa65 && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                                  {t('coreConfigModal.generateMldsa65')}
                                </span>
                              </LoaderButton>
                            </div>
                          </TabsContent>

                          {/* ============================================
          Shadowsocks TAB
      ============================================ */}
                          <TabsContent value="shadowsocks" className="animate-in fade-in-50 mt-3 space-y-3 duration-300">
                            {/* Encryption Method Selector */}
                            <div className="space-y-2.5">
                              <Label className="text-muted-foreground text-xs font-semibold tracking-wide">
                                {t('coreConfigModal.shadowsocksEncryptionMethod', { defaultValue: 'Encryption Method' })}
                              </Label>
                              <Select
                                value={selectedEncryptionMethod}
                                onValueChange={value => {
                                  setSelectedEncryptionMethod(value)
                                  setGeneratedShadowsocksPassword(null)
                                }}
                              >
                                <SelectTrigger className="h-9">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {SHADOWSOCKS_PASSWORD_GENERATION_METHODS.map(method => (
                                    <SelectItem key={method} value={method}>
                                      {method}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>

                            {canGenerateShadowsocksPassword(selectedEncryptionMethod) && (
                              <LoaderButton
                                type="button"
                                onClick={viewShadowsocksPassword}
                                className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                                isLoading={isGeneratingShadowsocksPassword}
                                loadingText={t('coreConfigModal.generatingShadowsocksPassword')}
                              >
                                <span className="flex items-center gap-2 truncate">
                                  {generatedShadowsocksPassword && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                                  {t('coreConfigModal.generateShadowsocksPassword')}
                                </span>
                              </LoaderButton>
                            )}
                          </TabsContent>

                          {/* ============================================
          VLESS TAB
      ============================================ */}
                          <TabsContent value="vless" className="animate-in fade-in-50 mt-3 space-y-3 duration-300">
                            {/* VLESS Buttons */}
                            <LoaderButton type="button" onClick={viewVLESS} className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11" isLoading={false}>
                              <span className="flex items-center gap-2 truncate">
                                {generatedVLESS && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                                {t('coreConfigModal.generateVLESSEncryption')}
                              </span>
                            </LoaderButton>
                          </TabsContent>
                        </Tabs>
                      </>
                    )}
                  </div>
                </div>
              </div>
              {/* Form: Restart nodes toggle */}
              {!isCodeEditorFullscreen && (
                <div className={cn('flex items-center gap-2', editingCore ? 'justify-between' : 'justify-end')}>
                  {editingCore && (
                    <FormField
                      control={form.control}
                      name="restart_nodes"
                      render={({ field }) => (
                        <FormItem className="flex flex-row-reverse items-center gap-2">
                          <FormControl>
                            <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                          <FormLabel className="!m-0 text-sm">{t('coreConfigModal.restartNodes')}</FormLabel>
                        </FormItem>
                      )}
                    />
                  )}

                  <div className="flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={() => handleDialogOpenChange(false)} disabled={createCoreMutation.isPending || modifyCoreMutation.isPending}>
                      {t('cancel')}
                    </Button>
                    <LoaderButton
                      type="submit"
                      disabled={!validation.isValid || unknownApiServices.length > 0 || createCoreMutation.isPending || modifyCoreMutation.isPending || form.formState.isSubmitting}
                      isLoading={createCoreMutation.isPending || modifyCoreMutation.isPending}
                      loadingText={editingCore ? t('modifying') : t('creating')}
                    >
                      {editingCore ? t('modify') : t('create')}
                    </LoaderButton>
                  </div>
                </div>
              )}
            </form>
          </Form>
        </DialogContent>
      </Dialog>
      <AlertDialog open={discardChangesOpen} onOpenChange={setDiscardChangesOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreConfigModal.discardChangesTitle', { defaultValue: 'Discard changes?' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreConfigModal.discardChangesDescription', {
                defaultValue: 'Your unsaved kernel configuration changes will be lost if you close this editor.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDiscardChanges}>{t('coreEditor.leave', { defaultValue: 'Leave' })}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
