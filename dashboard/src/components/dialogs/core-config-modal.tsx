import { CopyButton } from '@/components/common/copy-button'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoaderButton } from '@/components/ui/loader-button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useCreateCoreConfig, useModifyCoreConfig } from '@/service/api'
import { isEmptyObject } from '@/utils/isEmptyObject.ts'
import { generateMldsa65 } from '@/utils/mldsa65'
import { queryClient } from '@/utils/query-client'
import Editor from '@monaco-editor/react'
import { encodeURLSafe } from '@stablelib/base64'
import { generateKeyPair } from '@stablelib/x25519'
import { debounce } from 'es-toolkit'
import { Info, Key, Maximize2, Minimize2, Sparkles, Shield } from 'lucide-react'
import { MlKem768 } from 'mlkem'
import { useCallback, useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useTheme } from '@/components/common/theme-provider'
import type { CoreConfigFormValues } from '@/components/forms/core-config-form'

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
// Add encryption methods enum
const SHADOWSOCKS_ENCRYPTION_METHODS = [
  { value: '2022-blake3-aes-128-gcm', label: '2022-blake3-aes-128-gcm', length: 16 },
  { value: '2022-blake3-aes-256-gcm', label: '2022-blake3-aes-256-gcm', length: 32 },
] as const
type VlessVariant = 'x25519' | 'mlkem768'
const DEFAULT_VLESS_HANDSHAKE = 'mlkem768x25519plus'
const DEFAULT_VLESS_ENCRYPTION = 'native'
const DEFAULT_VLESS_PADDING = '100-111-1111.75-0-111.50-0-3333'
const DEFAULT_VLESS_SERVER_TICKET = '600s'
const VLESS_HANDSHAKE_OPTIONS = [{ value: DEFAULT_VLESS_HANDSHAKE, label: 'mlkem768x25519plus', translationKey: 'coreConfigModal.vlessHandshakeOptionMlkem768x25519plus' }] as const
const VLESS_RESUME_OPTIONS = [
  { value: '0rtt', label: '0rtt', translationKey: 'coreConfigModal.vlessResumeOption0rtt' },
  { value: '1rtt', label: '1rtt', translationKey: 'coreConfigModal.vlessResumeOption1rtt' },
] as const
const DEFAULT_VLESS_RESUME = VLESS_RESUME_OPTIONS[0].value
const VLESS_ENCRYPTION_METHODS = [
  { value: 'native', label: 'native', translationKey: 'coreConfigModal.vlessEncryptionOptionNative' },
  { value: 'xorpub', label: 'xorpub', translationKey: 'coreConfigModal.vlessEncryptionOptionXorpub' },
  { value: 'random', label: 'random', translationKey: 'coreConfigModal.vlessEncryptionOptionRandom' },
] as const

interface VlessBuilderOptions {
  handshakeMethod: string
  encryptionMethod: string
  serverTicket: string
  clientTicket: string
  serverPadding: string
  clientPadding: string
  includeServerPadding: boolean
  includeClientPadding: boolean
}

interface DataFieldProps {
  label: string
  value: string
  statusColor: string
  copiedMessage: string
  defaultMessage: string
}

const createDefaultVlessOptions = (): VlessBuilderOptions => ({
  handshakeMethod: DEFAULT_VLESS_HANDSHAKE,
  encryptionMethod: DEFAULT_VLESS_ENCRYPTION,
  serverTicket: DEFAULT_VLESS_SERVER_TICKET,
  clientTicket: DEFAULT_VLESS_RESUME,
  serverPadding: DEFAULT_VLESS_PADDING,
  clientPadding: DEFAULT_VLESS_PADDING,
  includeServerPadding: false,
  includeClientPadding: false,
})

export default function CoreConfigModal({ isDialogOpen, onOpenChange, form, editingCore, editingCoreId }: CoreConfigModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { resolvedTheme } = useTheme()
  const [validation, setValidation] = useState<ValidationResult>({ isValid: true })
  const [isEditorReady, setIsEditorReady] = useState(false)
  const createCoreMutation = useCreateCoreConfig()
  const modifyCoreMutation = useModifyCoreConfig()
  const [isEditorFullscreen, setIsEditorFullscreen] = useState(false)
  const [inboundTags, setInboundTags] = useState<string[]>([])
  const [isGeneratingKeyPair, setIsGeneratingKeyPair] = useState(false)
  const [isGeneratingShortId, setIsGeneratingShortId] = useState(false)
  const [isGeneratingVLESSEncryption, setIsGeneratingVLESSEncryption] = useState(false)
  const [selectedEncryptionMethod, setSelectedEncryptionMethod] = useState<string>(SHADOWSOCKS_ENCRYPTION_METHODS[0].value)
  const [isGeneratingShadowsocksPassword, setIsGeneratingShadowsocksPassword] = useState(false)
  const [isGeneratingMldsa65, setIsGeneratingMldsa65] = useState(false)
  const [selectedVlessVariant, setSelectedVlessVariant] = useState<VlessVariant>('x25519')
  const [vlessOptions, setVlessOptions] = useState<VlessBuilderOptions>(() => createDefaultVlessOptions())
  const [isVlessAdvancedModalOpen, setIsVlessAdvancedModalOpen] = useState(false)
  const [editorInstance, setEditorInstance] = useState<any>(null)

  // Results dialog state
  const [isResultsDialogOpen, setIsResultsDialogOpen] = useState(false)
  const [resultType, setResultType] = useState<string | null>(null)
  const [resultData, setResultData] = useState<any>(null)

  // Store generated values
  const [generatedKeyPair, setGeneratedKeyPair] = useState<{ publicKey: string; privateKey: string } | null>(null)
  const [generatedShortId, setGeneratedShortId] = useState<string | null>(null)
  const [generatedShadowsocksPassword, setGeneratedShadowsocksPassword] = useState<{ password: string; encryptionMethod: string } | null>(null)
  const [generatedMldsa65, setGeneratedMldsa65] = useState<{ seed: string; verify: string } | null>(null)
  const [generatedVLESS, setGeneratedVLESS] = useState<any>(null)
  const handleVlessVariantChange = useCallback(
    (value: string) => {
      if (value === 'x25519' || value === 'mlkem768') {
        setSelectedVlessVariant(value)
      }
    },
    [setSelectedVlessVariant],
  )

  // Helper function to show results in dialog
  const showResultDialog = useCallback((type: string, data: any) => {
    setResultType(type)
    setResultData(data)
    setIsResultsDialogOpen(true)
  }, [])

  // Handle fullscreen toggle with editor resize
  const handleToggleFullscreen = useCallback(() => {
    setIsEditorFullscreen(prev => {
      const newValue = !prev

      // Force editor layout update when toggling fullscreen
      setTimeout(() => {
        if (editorInstance) {
          editorInstance.layout()
        }
        // Also trigger window resize event for Monaco to recalculate
        window.dispatchEvent(new Event('resize'))
      }, 50)

      return newValue
    })
  }, [editorInstance])

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
          position: 'bottom-right',
        })
      } else {
        try {
          // Additional validation - try parsing the JSON
          JSON.parse(form.getValues().config)
          setValidation({ isValid: true })
        } catch (e) {
          const errorMessage = e instanceof Error ? e.message : 'Invalid JSON'
          setValidation({
            isValid: false,
            error: errorMessage,
          })
          toast.error(errorMessage, {
            duration: 3000,
            position: 'bottom-right',
          })
        }
      }
    },
    [form],
  )

  // Debounce config changes to improve performance
  const debouncedConfigChange = useCallback(
    debounce((value: string) => {
      try {
        const parsedConfig = JSON.parse(value)
        if (parsedConfig.inbounds && Array.isArray(parsedConfig.inbounds)) {
          const tags = parsedConfig.inbounds.filter((inbound: any) => typeof inbound.tag === 'string' && inbound.tag.trim() !== '').map((inbound: any) => inbound.tag)
          setInboundTags(tags)
        } else {
          setInboundTags([])
        }
      } catch {
        setInboundTags([])
      }
    }, 300),
    [],
  )

  // Extract inbound tags from config JSON whenever config changes
  useEffect(() => {
    const configValue = form.getValues().config
    if (configValue) {
      debouncedConfigChange(configValue)
    }
  }, [form.watch('config'), debouncedConfigChange])

  const handleEditorDidMount = useCallback((editor: any) => {
    setIsEditorReady(true)
    setEditorInstance(editor)

    // Force layout recalculation for mobile devices
    // This ensures the editor properly calculates its dimensions on first load
    requestAnimationFrame(() => {
      if (editor) {
        editor.layout()
        // Also trigger a resize after a short delay to handle mobile viewport adjustments
        setTimeout(() => {
          editor.layout()
        }, 100)
      }
    })
  }, [])

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
    try {
      setIsGeneratingShadowsocksPassword(true)
      const method = SHADOWSOCKS_ENCRYPTION_METHODS.find(m => m.value === value)
      if (!method) return

      const randomBytes = new Uint8Array(method.length)
      crypto.getRandomValues(randomBytes)
      // Shadowsocks 2022 requires standard base64 encoding (not URL-safe)
      const password = btoa(String.fromCharCode(...randomBytes))
      setGeneratedShadowsocksPassword({ password, encryptionMethod: method.label })
      showResultDialog('shadowsocksPassword', { password, encryptionMethod: method.label })
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
  const generateVLESSEncryption = async () => {
    try {
      setIsGeneratingVLESSEncryption(true)

      const x25519KeyPair = generateKeyPair()
      const x25519ServerKey = encodeURLSafe(x25519KeyPair.secretKey).replace(/=/g, '')
      const x25519ClientKey = encodeURLSafe(x25519KeyPair.publicKey).replace(/=/g, '')

      const mlkem768Seed = new Uint8Array(64)
      crypto.getRandomValues(mlkem768Seed)
      const mlkem768 = new MlKem768()
      const [mlkem768Client] = await mlkem768.deriveKeyPair(mlkem768Seed)
      const mlkem768ServerKey = encodeURLSafe(mlkem768Seed).replace(/=/g, '')
      const mlkem768ClientKey = encodeURLSafe(mlkem768Client).replace(/=/g, '')

      const sanitizeSegments = (value: string) =>
        value
          .split('.')
          .map(segment => segment.trim())
          .filter(segment => segment.length > 0)

      const normalizeOption = (value: string | undefined, fallback: string) => {
        if (!value) return fallback
        const trimmed = value.trim()
        return trimmed.length > 0 ? trimmed : fallback
      }

      const handshakeMethod = normalizeOption(vlessOptions.handshakeMethod, DEFAULT_VLESS_HANDSHAKE)
      const encryptionMethod = normalizeOption(vlessOptions.encryptionMethod, DEFAULT_VLESS_ENCRYPTION)

      const buildConfig = ({
        ticketValue,
        paddingValue,
        includePadding,
        authParam,
        fallbackTicket,
      }: {
        ticketValue: string
        paddingValue: string
        includePadding: boolean
        authParam: string
        fallbackTicket: string
      }) => {
        const segments = [handshakeMethod, encryptionMethod, normalizeOption(ticketValue, fallbackTicket)]
        if (includePadding) {
          const paddingSegments = sanitizeSegments(normalizeOption(paddingValue, DEFAULT_VLESS_PADDING))
          segments.push(...paddingSegments)
        }
        segments.push(authParam)
        return segments.join('.')
      }

      const x25519Decryption = buildConfig({
        ticketValue: vlessOptions.serverTicket,
        paddingValue: vlessOptions.serverPadding,
        includePadding: vlessOptions.includeServerPadding,
        authParam: x25519ServerKey,
        fallbackTicket: DEFAULT_VLESS_SERVER_TICKET,
      })
      const x25519Encryption = buildConfig({
        ticketValue: vlessOptions.clientTicket,
        paddingValue: vlessOptions.clientPadding,
        includePadding: vlessOptions.includeClientPadding,
        authParam: x25519ClientKey,
        fallbackTicket: DEFAULT_VLESS_RESUME,
      })
      const mlkem768Decryption = buildConfig({
        ticketValue: vlessOptions.serverTicket,
        paddingValue: vlessOptions.serverPadding,
        includePadding: vlessOptions.includeServerPadding,
        authParam: mlkem768ServerKey,
        fallbackTicket: DEFAULT_VLESS_SERVER_TICKET,
      })
      const mlkem768Encryption = buildConfig({
        ticketValue: vlessOptions.clientTicket,
        paddingValue: vlessOptions.clientPadding,
        includePadding: vlessOptions.includeClientPadding,
        authParam: mlkem768ClientKey,
        fallbackTicket: DEFAULT_VLESS_RESUME,
      })

      const resultData = {
        x25519: {
          decryption: x25519Decryption,
          encryption: x25519Encryption,
        },
        mlkem768: {
          decryption: mlkem768Decryption,
          encryption: mlkem768Encryption,
        },
        options: vlessOptions,
      }

      setGeneratedVLESS(resultData)
      showResultDialog('vlessEncryption', resultData)
      toast.success(t('coreConfigModal.vlessEncryptionGenerated'))
    } catch (error) {
      toast.error(t('coreConfigModal.vlessEncryptionGenerationFailed'))
    } finally {
      setIsGeneratingVLESSEncryption(false)
    }
  }

  const defaultConfig = JSON.stringify(
    {
      log: {
        loglevel: 'info',
      },
      inbounds: [
        {
          tag: 'Shadowsocks TCP',
          listen: '0.0.0.0',
          port: 1080,
          protocol: 'shadowsocks',
          settings: {
            clients: [],
            network: 'tcp,udp',
          },
        },
      ],
      outbounds: [
        {
          protocol: 'freedom',
          tag: 'DIRECT',
        },
        {
          protocol: 'blackhole',
          tag: 'BLOCK',
        },
      ],
      routing: {
        rules: [
          {
            ip: ['geoip:private'],
            outboundTag: 'BLOCK',
            type: 'field',
          },
        ],
      },
    },
    null,
    2,
  )

  const onSubmit = async (values: CoreConfigFormValues) => {
    try {
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

      const fallbackTags = values.fallback_id || []
      const excludeInboundTags = values.excluded_inbound_ids || []

      if (editingCore && editingCoreId) {
        // Update existing core
        await modifyCoreMutation.mutateAsync({
          coreId: editingCoreId,
          data: {
            name: values.name,
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
            name: values.name,
            config: configObj,
            fallbacks_inbound_tags: fallbackTags,
            exclude_inbound_tags: excludeInboundTags,
          },
        })
      }

      toast.success(
        t(editingCore ? 'coreConfigModal.editSuccess' : 'coreConfigModal.createSuccess', {
          name: values.name,
        }),
      )

      // Invalidate core config queries after successful action
      queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
      onOpenChange(false)
      form.reset()
    } catch (error: any) {
      console.error('Core config operation failed:', error)
      console.error('Error response:', error?.response)
      // Error data logging removed

      // Reset all previous errors first
      form.clearErrors()

      // Handle validation errors
      if (error?.response?._data && !isEmptyObject(error?.response?._data)) {
        // For zod validation errors
        const fields = ['name', 'config', 'fallback_id', 'excluded_inbound_ids']

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

  // Initialize form fields when modal opens
  useEffect(() => {
    if (isDialogOpen) {
      if (!editingCore) {
        // Reset form for new core
        form.reset({
          name: '',
          config: defaultConfig,
          excluded_inbound_ids: [],
          fallback_id: [],
          restart_nodes: true,
        })
      } else {
        // Set restart_nodes to true for editing
        form.setValue('restart_nodes', true)
      }

      // Force editor resize on mobile after modal opens
      // This ensures the editor properly renders on first load
      setTimeout(() => {
        const editorElement = document.querySelector('.monaco-editor')
        if (editorElement) {
          // Trigger a resize event
          window.dispatchEvent(new Event('resize'))
        }
      }, 300)
    }
  }, [isDialogOpen, editingCore, form, defaultConfig])

  // Cleanup on modal close
  useEffect(() => {
    if (!isDialogOpen) {
      setIsEditorFullscreen(false)
      setIsResultsDialogOpen(false)
      setResultType(null)
      setResultData(null)
      setSelectedVlessVariant('x25519')
      setVlessOptions(createDefaultVlessOptions())
      setValidation({ isValid: true })
      setEditorInstance(null)
      setIsEditorReady(false)
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
    if (generatedShadowsocksPassword) {
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
    const styleElement = document.createElement('style')
    styleElement.textContent = styles
    document.head.appendChild(styleElement)
    return () => {
      document.head.removeChild(styleElement)
    }
  }, [])

  // Handle Monaco Editor web component registration errors
  useEffect(() => {
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
  }, [])

  // Handle window resize for editor layout updates
  useEffect(() => {
    const handleResize = () => {
      // Force editor to recalculate its dimensions
      setTimeout(() => {
        if (editorInstance) {
          editorInstance.layout()
        }
      }, 100)
    }

    window.addEventListener('resize', handleResize)

    // Also listen for orientation changes on mobile
    window.addEventListener('orientationchange', () => {
      setTimeout(() => {
        if (editorInstance) {
          editorInstance.layout()
        }
      }, 300)
    })

    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('orientationchange', handleResize)
    }
  }, [editorInstance])

  // Trigger layout update when fullscreen state changes
  useEffect(() => {
    if (editorInstance && isEditorReady) {
      setTimeout(() => {
        editorInstance.layout()
      }, 150)
    }
  }, [isEditorFullscreen, editorInstance, isEditorReady])

  // VLESS Advanced Settings Modal Component
  const renderVlessAdvancedModal = () => {
    return (
      <Dialog open={isVlessAdvancedModalOpen} onOpenChange={setIsVlessAdvancedModalOpen}>
        <DialogContent className="h-full max-w-full px-2 py-6 sm:h-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 px-2 text-base sm:text-lg">
              <span className="truncate">{t('coreConfigModal.vlessAdvancedSettings', { defaultValue: 'VLESS Advanced Settings' })}</span>
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[calc(100dvh-120px)] space-y-4 overflow-y-auto px-2">
            {/* Variant Selector */}
            <div className="space-y-2">
              <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.chooseAuthentication')}</Label>
              <Select value={selectedVlessVariant} onValueChange={handleVlessVariantChange}>
                <SelectTrigger className="h-9 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="x25519">
                    <span className="flex items-center gap-2">
                      <Key className="h-3.5 w-3.5" />
                      <span>{t('coreConfigModal.x25519Authentication')}</span>
                    </span>
                  </SelectItem>
                  <SelectItem value="mlkem768">
                    <span className="flex items-center gap-2">
                      <Shield className="h-3.5 w-3.5" />
                      <span>{t('coreConfigModal.mlkem768Authentication')}</span>
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Handshake and Encryption Methods */}
            <div className="flex flex-col gap-3 sm:flex-row">
              {/* Handshake Method */}
              <div className="flex flex-1 flex-col justify-end space-y-2">
                <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessHandshakeLabel')}</Label>
                <Select value={vlessOptions.handshakeMethod} onValueChange={value => setVlessOptions(prev => ({ ...prev, handshakeMethod: value }))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VLESS_HANDSHAKE_OPTIONS.map(option => (
                      <SelectItem key={option.value} value={option.value}>
                        <span className="truncate">{t(option.translationKey, { defaultValue: option.label })}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Encryption Method */}
              <div className="flex flex-1 flex-col justify-end space-y-2">
                <div className="flex items-center gap-1.5">
                  <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessEncryptionLabel')}</Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                        <Info className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[280px] p-3 sm:w-[340px]" side="top" align="start" sideOffset={5}>
                      <div className="space-y-1.5">
                        <h4 className="mb-2 text-[12px] font-medium">{t('coreConfigModal.vlessEncryptionInfoTitle')}</h4>
                        <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessEncryptionHint')}</p>
                        <p className="text-[11px] text-muted-foreground">• {t('coreConfigModal.vlessEncryptionNativeInfo')}</p>
                        <p className="text-[11px] text-muted-foreground">• {t('coreConfigModal.vlessEncryptionXorpubInfo')}</p>
                        <p className="text-[11px] text-muted-foreground">• {t('coreConfigModal.vlessEncryptionRandomInfo')}</p>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
                <Select value={vlessOptions.encryptionMethod} onValueChange={value => setVlessOptions(prev => ({ ...prev, encryptionMethod: value }))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VLESS_ENCRYPTION_METHODS.map(method => (
                      <SelectItem key={method.value} value={method.value}>
                        <span className="truncate">{t(method.translationKey, { defaultValue: method.label })}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Configuration Grid */}
            <div className="grid gap-3 sm:grid-cols-2">
              {/* Server Ticket */}
              <div className="space-y-2">
                <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessServerTicket')}</Label>
                <Input value={vlessOptions.serverTicket} placeholder="600s or 100-500s" className="h-9" onChange={event => setVlessOptions(prev => ({ ...prev, serverTicket: event.target.value }))} />
              </div>

              {/* Client Ticket */}
              <div className="space-y-2">
                <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessClientTicket')}</Label>
                <Select value={vlessOptions.clientTicket} onValueChange={value => setVlessOptions(prev => ({ ...prev, clientTicket: value }))}>
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VLESS_RESUME_OPTIONS.map(option => (
                      <SelectItem key={option.value} value={option.value}>
                        <span className="truncate">{t(option.translationKey, { defaultValue: option.label })}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Padding Configuration */}
            <div className="space-y-3">
              <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.padding', { defaultValue: 'Padding' })}</Label>

              <div className="grid gap-3 sm:grid-cols-2">
                {/* Server Padding */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="vless-server-padding-modal"
                      checked={vlessOptions.includeServerPadding}
                      onCheckedChange={checked => setVlessOptions(prev => ({ ...prev, includeServerPadding: checked === true }))}
                      className="h-4 w-4"
                    />
                    <Label htmlFor="vless-server-padding-modal" className="cursor-pointer text-xs font-medium">
                      {t('coreConfigModal.vlessServerPaddingToggle')}
                    </Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                          <Info className="h-3.5 w-3.5 text-muted-foreground" />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-[280px] p-3 sm:w-[340px]" side="top" align="start" sideOffset={5}>
                        <div className="space-y-1.5">
                          <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessPaddingHint')}</p>
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>
                  <Input
                    value={vlessOptions.serverPadding}
                    placeholder={DEFAULT_VLESS_PADDING}
                    disabled={!vlessOptions.includeServerPadding}
                    className="h-8 text-xs"
                    onChange={event => setVlessOptions(prev => ({ ...prev, serverPadding: event.target.value }))}
                  />
                </div>

                {/* Client Padding */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="vless-client-padding-modal"
                      checked={vlessOptions.includeClientPadding}
                      onCheckedChange={checked => setVlessOptions(prev => ({ ...prev, includeClientPadding: checked === true }))}
                      className="h-4 w-4"
                    />
                    <Label htmlFor="vless-client-padding-modal" className="cursor-pointer text-xs font-medium">
                      {t('coreConfigModal.vlessClientPaddingToggle')}
                    </Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                          <Info className="h-3.5 w-3.5 text-muted-foreground" />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-[280px] p-3 sm:w-[340px]" side="top" align="start" sideOffset={5}>
                        <div className="space-y-1.5">
                          <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessPaddingHint')}</p>
                          <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessClientPaddingHint')}</p>
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>
                  <Input
                    value={vlessOptions.clientPadding}
                    placeholder={DEFAULT_VLESS_PADDING}
                    disabled={!vlessOptions.includeClientPadding}
                    className="h-8 text-xs"
                    onChange={event => setVlessOptions(prev => ({ ...prev, clientPadding: event.target.value }))}
                  />
                </div>
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 px-4">
            <Button type="button" variant="outline" onClick={() => setIsVlessAdvancedModalOpen(false)} size="sm" disabled={isGeneratingVLESSEncryption}>
              {t('close')}
            </Button>
            <LoaderButton type="button" onClick={generateVLESSEncryption} isLoading={isGeneratingVLESSEncryption} loadingText={t('coreConfigModal.generatingVLESSEncryption')} size="sm">
              {t('coreConfigModal.generate')}
            </LoaderButton>
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  // Results Dialog Component
  // Reusable components for cleaner code
  const StatusIndicator = ({ color }: { color: string }) => <div className={`h-1.5 w-1.5 shrink-0 rounded-full ${color}`} aria-hidden="true" />

  const SectionLabel = ({ children }: { children: React.ReactNode }) => <p className="truncate text-[10px] font-semibold tracking-wide text-muted-foreground sm:text-xs">{children}</p>

  const CodeBlock = ({ value }: { value: string }) => (
    <div dir="ltr" className="group relative min-w-0 flex-1 rounded-md border bg-background/80 backdrop-blur-sm">
      <code className="block w-full overflow-x-auto whitespace-nowrap px-3 py-2.5 font-mono text-xs leading-relaxed">{value}</code>
    </div>
  )

  const DataField = ({ label, value, statusColor, copiedMessage, defaultMessage }: DataFieldProps) => (
    <div className="space-y-1.5 sm:space-y-2">
      <div className="flex min-w-0 items-center gap-1.5 sm:gap-2">
        <StatusIndicator color={statusColor} />
        <SectionLabel>{label}</SectionLabel>
      </div>
      <div dir="ltr" className="flex min-w-0 items-start gap-2">
        <CodeBlock value={value} />
        <CopyButton value={value} icon="copy" copiedMessage={copiedMessage} defaultMessage={defaultMessage} className="h-8 w-full shrink-0 text-xs sm:h-9 sm:w-auto sm:px-3 sm:text-sm" />
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
        <DialogContent className="max-h-[95vh] w-[95vw] max-w-2xl overflow-y-auto p-3 sm:p-6">
          <DialogHeader className="pb-3">
            <DialogTitle className="flex items-center gap-1.5 text-sm sm:gap-2 sm:text-base">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary sm:h-5 sm:w-5" />
              <span className="truncate">{t('coreConfigModal.result', { defaultValue: 'Result' })}</span>
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[70vh] space-y-3 overflow-y-auto pr-1 sm:space-y-4">{renderContent()}</div>
          <DialogFooter className="pt-3 sm:pt-4">
            <div className="flex w-full gap-2 sm:w-auto">
              <Button
                variant="outline"
                onClick={() => {
                  switch (resultType) {
                    case 'keyPair':
                      generatePrivateAndPublicKey()
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
      {renderVlessAdvancedModal()}
      {renderResultDialog()}
      <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
        <DialogContent className="h-full max-w-full px-4 py-6 sm:h-auto sm:max-w-[1000px]" onOpenAutoFocus={e => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle className={cn('text-start text-xl font-semibold', dir === 'rtl' && 'sm:text-right')}>
              {editingCore ? t('coreConfigModal.editCore') : t('coreConfigModal.addConfig')}
            </DialogTitle>
            <DialogDescription className="sr-only">
              {editingCore ? t('coreConfigModal.editConfig', { defaultValue: 'Edit the core configuration' }) : t('coreConfigModal.createNewConfig')}
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <div className="-mr-4 max-h-[69dvh] overflow-y-auto px-2 pr-4 sm:max-h-[72dvh]">
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
                              <div
                                className={cn(
                                  'relative flex flex-col rounded-lg border bg-background',
                                  // Responsive heights for normal mode
                                  isEditorFullscreen ? 'fixed inset-0 z-[60] flex items-center justify-center' : 'h-[calc(50vh-1rem)] sm:h-[calc(55vh-1rem)] md:h-[600px]',
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

                                {/* Fullscreen Mode */}
                                {isEditorFullscreen ? (
                                  <div className="relative z-10 flex h-full w-full flex-col bg-background sm:my-8 sm:h-auto sm:w-full sm:max-w-[95vw] sm:rounded-lg sm:border sm:shadow-xl">
                                    {/* Header - hidden on mobile, visible on desktop */}
                                    <div className="hidden items-center justify-between rounded-t-lg border-b bg-background px-3 py-2.5 sm:flex">
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium">Xray Core Configuration</span>
                                      </div>
                                      <Button type="button" size="icon" variant="ghost" className="h-8 w-8 shrink-0" onClick={handleToggleFullscreen} aria-label={t('exitFullscreen')}>
                                        <Minimize2 className="h-4 w-4" />
                                      </Button>
                                    </div>
                                    {/* Floating minimize button for mobile */}
                                    <Button
                                      type="button"
                                      size="icon"
                                      variant="default"
                                      className="absolute right-2 top-2 z-20 h-9 w-9 rounded-full shadow-lg sm:hidden"
                                      onClick={handleToggleFullscreen}
                                      aria-label={t('exitFullscreen')}
                                    >
                                      <Minimize2 className="h-4 w-4" />
                                    </Button>
                                    <div className="relative h-full sm:h-[calc(100vh-160px)]" style={{ width: '100%' }}>
                                      <Editor
                                        height="100%"
                                        defaultLanguage="json"
                                        value={field.value}
                                        theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
                                        onChange={field.onChange}
                                        onValidate={handleEditorValidation}
                                        onMount={handleEditorDidMount}
                                        options={{
                                          minimap: { enabled: false },
                                          fontSize: 14,
                                          fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
                                          lineNumbers: 'on',
                                          roundedSelection: true,
                                          scrollBeyondLastLine: false,
                                          automaticLayout: true,
                                          formatOnPaste: true,
                                          formatOnType: true,
                                          renderWhitespace: 'none',
                                          wordWrap: 'on',
                                          folding: true,
                                          suggestOnTriggerCharacters: true,
                                          quickSuggestions: true,
                                          renderLineHighlight: 'all',
                                          scrollbar: {
                                            vertical: 'visible',
                                            horizontal: 'visible',
                                            useShadows: false,
                                            verticalScrollbarSize: 10,
                                            horizontalScrollbarSize: 10,
                                          },
                                          // Mobile-friendly options
                                          contextmenu: true,
                                          copyWithSyntaxHighlighting: false,
                                          multiCursorModifier: 'alt',
                                          accessibilitySupport: 'on',
                                          mouseWheelZoom: true,
                                          quickSuggestionsDelay: 0,
                                          occurrencesHighlight: 'singleFile',
                                          wordBasedSuggestions: 'currentDocument',
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
                                        }}
                                      />
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
                                        aria-label={t('fullscreen')}
                                      >
                                        <Maximize2 className="h-4 w-4" />
                                      </Button>
                                    )}
                                    <div className="relative min-h-0 flex-1" style={{ minHeight: 0 }}>
                                      <Editor
                                        height={undefined}
                                        defaultLanguage="json"
                                        value={field.value}
                                        theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
                                        onChange={field.onChange}
                                        onValidate={handleEditorValidation}
                                        onMount={handleEditorDidMount}
                                        options={{
                                          minimap: { enabled: false },
                                          fontSize: 14,
                                          fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
                                          lineNumbers: 'on',
                                          roundedSelection: true,
                                          scrollBeyondLastLine: false,
                                          automaticLayout: true,
                                          formatOnPaste: true,
                                          formatOnType: true,
                                          renderWhitespace: 'none',
                                          wordWrap: 'on',
                                          folding: true,
                                          suggestOnTriggerCharacters: true,
                                          quickSuggestions: true,
                                          renderLineHighlight: 'all',
                                          scrollbar: {
                                            vertical: 'visible',
                                            horizontal: 'visible',
                                            useShadows: false,
                                            verticalScrollbarSize: 10,
                                            horizontalScrollbarSize: 10,
                                          },
                                          contextmenu: true,
                                          copyWithSyntaxHighlighting: false,
                                          multiCursorModifier: 'alt',
                                          accessibilitySupport: 'on',
                                          mouseWheelZoom: true,
                                          quickSuggestionsDelay: 0,
                                          occurrencesHighlight: 'singleFile',
                                          wordBasedSuggestions: 'currentDocument',
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
                                        }}
                                      />
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
                    {/* Form: Core display name */}
                    <FormField
                      control={form.control}
                      name="name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('coreConfigModal.name')}</FormLabel>
                          <FormControl>
                            <Input isError={!!form.formState.errors.name} placeholder={t('coreConfigModal.namePlaceholder')} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    {/* Form: Fallback inbound selectors */}
                    <FormField
                      control={form.control}
                      name="fallback_id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('coreConfigModal.fallback')}</FormLabel>
                          <div className="flex flex-col gap-2">
                            <div className="flex flex-wrap gap-2">
                              {field.value && field.value.length > 0 ? (
                                field.value.map((tag: string) => (
                                  <span key={tag} className="flex items-center gap-2 rounded-md bg-muted/80 px-2 py-1 text-sm">
                                    {tag}
                                    <button type="button" className="hover:text-destructive" onClick={() => field.onChange((field.value || []).filter((t: string) => t !== tag))}>
                                      ×
                                    </button>
                                  </span>
                                ))
                              ) : (
                                <span className="text-sm text-muted-foreground">{t('coreConfigModal.selectFallback')}</span>
                              )}
                            </div>
                            <Select
                              value={undefined}
                              onValueChange={(value: string) => {
                                if (!value || value.trim() === '') return
                                const currentValue = field.value || []
                                if (!currentValue.includes(value)) {
                                  field.onChange([...currentValue, value])
                                }
                              }}
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder={t('coreConfigModal.selectFallback')} />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {inboundTags.length > 0 ? (
                                  inboundTags.map(tag => (
                                    <SelectItem key={tag} value={tag} disabled={field.value?.includes(tag)} className="cursor-pointer">
                                      {tag}
                                    </SelectItem>
                                  ))
                                ) : (
                                  <SelectItem key="no-inbounds" value="no-inbounds" disabled>
                                    {t('coreConfigModal.noInboundsFound')}
                                  </SelectItem>
                                )}
                              </SelectContent>
                            </Select>
                            {field.value && field.value.length > 0 && (
                              <Button type="button" variant="outline" size="sm" onClick={() => field.onChange([])} className="w-full">
                                {t('coreConfigModal.clearAllFallbacks')}
                              </Button>
                            )}
                          </div>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    {/* Form: Excluded inbound selectors */}
                    <FormField
                      control={form.control}
                      name="excluded_inbound_ids"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('coreConfigModal.excludedInbound')}</FormLabel>
                          <div className="flex flex-col gap-2">
                            <div className="flex flex-wrap gap-2">
                              {field.value && field.value.length > 0 ? (
                                field.value.map((tag: string) => (
                                  <span key={tag} className="flex items-center gap-2 rounded-md bg-muted/80 px-2 py-1 text-sm">
                                    {tag}
                                    <button type="button" className="hover:text-destructive" onClick={() => field.onChange((field.value || []).filter((t: string) => t !== tag))}>
                                      ×
                                    </button>
                                  </span>
                                ))
                              ) : (
                                <span className="text-sm text-muted-foreground">{t('coreConfigModal.selectInbound')}</span>
                              )}
                            </div>
                            <Select
                              value={undefined}
                              onValueChange={(value: string) => {
                                if (!value || value.trim() === '') return
                                const currentValue = field.value || []
                                if (!currentValue.includes(value)) {
                                  field.onChange([...currentValue, value])
                                }
                              }}
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder={t('coreConfigModal.selectInbound')} />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {inboundTags.length > 0 ? (
                                  inboundTags.map(tag => (
                                    <SelectItem key={tag} value={tag} disabled={field.value?.includes(tag)} className="cursor-pointer">
                                      {tag}
                                    </SelectItem>
                                  ))
                                ) : (
                                  <SelectItem key="no-inbounds" value="no-inbounds" disabled>
                                    {t('coreConfigModal.noInboundsFound')}
                                  </SelectItem>
                                )}
                              </SelectContent>
                            </Select>
                            {field.value && field.value.length > 0 && (
                              <Button type="button" variant="outline" size="sm" onClick={() => field.onChange([])} className="w-full">
                                {t('coreConfigModal.clearAllExcluded')}
                              </Button>
                            )}
                          </div>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <Tabs dir={dir} defaultValue="reality" className="w-full pb-6">
                      {/* Enhanced TabsList with Text Overflow */}
                      <TabsList dir="ltr" className="grid h-auto w-full grid-cols-3 gap-1 bg-muted/50 p-1">
                        <TabsTrigger
                          value="reality"
                          className="min-w-0 truncate px-2 py-2.5 text-xs font-medium transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm sm:text-sm"
                        >
                          Reality
                        </TabsTrigger>

                        <TabsTrigger
                          value="shadowsocks"
                          className="min-w-0 truncate px-2 py-2.5 text-xs font-medium transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm sm:text-sm"
                        >
                          ShadowSocks
                        </TabsTrigger>

                        <TabsTrigger
                          value="vless"
                          className="min-w-0 truncate px-2 py-2.5 text-xs font-medium transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm sm:text-sm"
                        >
                          VLESS
                        </TabsTrigger>
                      </TabsList>

                      {/* ============================================
          Reality TAB
      ============================================ */}
                      <TabsContent value="reality" className="mt-3 space-y-3 duration-300 animate-in fade-in-50">
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
                            onClick={viewMldsa65}
                            className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                            isLoading={isGeneratingMldsa65}
                            loadingText={t('coreConfigModal.generatingMldsa65')}
                          >
                            <span className="flex items-center gap-2 truncate">
                              {generatedMldsa65 && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                              {t('coreConfigModal.generateMldsa65')}
                            </span>
                          </LoaderButton>

                          <LoaderButton
                            type="button"
                            onClick={viewShortId}
                            className="col-span-2 h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                            isLoading={isGeneratingShortId}
                            loadingText={t('coreConfigModal.generatingShortId')}
                          >
                            <span className="flex items-center gap-2 truncate">
                              {generatedShortId && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                              {t('coreConfigModal.generateShortId')}
                            </span>
                          </LoaderButton>
                        </div>
                      </TabsContent>

                      {/* ============================================
          Shadowsocks TAB
      ============================================ */}
                      <TabsContent value="shadowsocks" className="mt-3 space-y-3 duration-300 animate-in fade-in-50">
                        {/* Encryption Method Selector */}
                        <div className="space-y-2">
                          <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.shadowsocksEncryptionMethod', { defaultValue: 'Encryption Method' })}</Label>
                          <Select value={selectedEncryptionMethod} onValueChange={setSelectedEncryptionMethod}>
                            <SelectTrigger className="h-9">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {SHADOWSOCKS_ENCRYPTION_METHODS.map(method => (
                                <SelectItem key={method.value} value={method.value}>
                                  {method.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>

                        {/* Action Buttons */}
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
                      </TabsContent>

                      {/* ============================================
          VLESS TAB
      ============================================ */}
                      <TabsContent value="vless" className="mt-3 space-y-3 duration-300 animate-in fade-in-50">
                        {/* VLESS Buttons */}
                        <LoaderButton type="button" onClick={viewVLESS} className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11" isLoading={false}>
                          <span className="flex items-center gap-2 truncate">
                            {generatedVLESS && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-green-500 ring-2 ring-green-500/20" />}
                            {t('coreConfigModal.generateVLESSEncryption')}
                          </span>
                        </LoaderButton>
                      </TabsContent>
                    </Tabs>
                  </div>
                </div>
              </div>
              {/* Form: Restart nodes toggle */}
              {!isEditorFullscreen && (
                <div className="flex flex-col gap-2">
                  {editingCore && (
                    <FormField
                      control={form.control}
                      name="restart_nodes"
                      render={({ field }) => (
                        <FormItem className={'mb-2 flex flex-row-reverse items-center gap-2'}>
                          <FormControl>
                            <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                          <FormLabel className="!m-0 text-sm">{t('coreConfigModal.restartNodes')}</FormLabel>
                        </FormItem>
                      )}
                    />
                  )}

                  <div className="flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={createCoreMutation.isPending || modifyCoreMutation.isPending}>
                      {t('cancel')}
                    </Button>
                    <LoaderButton
                      type="submit"
                      disabled={!validation.isValid || createCoreMutation.isPending || modifyCoreMutation.isPending || form.formState.isSubmitting}
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
    </>
  )
}

