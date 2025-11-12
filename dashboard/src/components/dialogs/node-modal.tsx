import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useTranslation } from 'react-i18next'
import { UseFormReturn } from 'react-hook-form'
import { useCreateNode, useModifyNode, NodeConnectionType, useGetAllCores, CoreResponse, getNode, DataLimitResetStrategy } from '@/service/api'
import { toast } from 'sonner'
import { z } from 'zod'
import { cn } from '@/lib/utils'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { queryClient } from '@/utils/query-client'
import useDirDetection from '@/hooks/use-dir-detection'
import React, { useState, useEffect } from 'react'
import { Loader2, Settings, RefreshCw } from 'lucide-react'
import { v4 as uuidv4, v5 as uuidv5, v6 as uuidv6, v7 as uuidv7 } from 'uuid'
import { LoaderButton } from '../ui/loader-button'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { formatBytes, gbToBytes } from '@/utils/formatByte'

export const nodeFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  address: z.string().min(1, 'Address is required'),
  port: z.number().min(1, 'Port is required'),
  usage_coefficient: z.number().optional(),
  connection_type: z.enum([NodeConnectionType.grpc, NodeConnectionType.rest]),
  server_ca: z.string().min(1, 'Server CA is required'),
  keep_alive: z.number().min(0, 'Keep alive must be 0 or greater'),
  keep_alive_unit: z.enum(['seconds', 'minutes', 'hours']).default('seconds'),
  max_logs: z.number().min(1, 'Max logs is required'),
  api_key: z.string().min(1, 'API key is required'),
  core_config_id: z.number().min(1, 'Core configuration is required'),
  gather_logs: z.boolean().default(true),
  data_limit: z.number().min(0).optional().nullable(),
  data_limit_reset_strategy: z.nativeEnum(DataLimitResetStrategy).optional().nullable(),
  reset_time: z.union([z.null(), z.undefined(), z.number().min(-1)]),
})

export type NodeFormValues = z.infer<typeof nodeFormSchema>

interface NodeModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<NodeFormValues>
  editingNode: boolean
  editingNodeId?: number
}

type ConnectionStatus = 'idle' | 'success' | 'error' | 'checking'

export default function NodeModal({ isDialogOpen, onOpenChange, form, editingNode, editingNodeId }: NodeModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const addNodeMutation = useCreateNode()
  const modifyNodeMutation = useModifyNode()
  const handleError = useDynamicErrorHandler()
  const { data: cores } = useGetAllCores()
  const [statusChecking, setStatusChecking] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [errorDetails, setErrorDetails] = useState<string | null>(null)
  const [autoCheck, setAutoCheck] = useState(false)
  const [showErrorDetails, setShowErrorDetails] = useState(false)
  const [debouncedValues, setDebouncedValues] = useState<NodeFormValues | null>(null)
  // Ref to store raw input value for data_limit to allow typing decimals
  const dataLimitInputRef = React.useRef<string>('')

  // Reset status when modal opens/closes
  useEffect(() => {
    if (isDialogOpen) {
      setConnectionStatus('idle')
      setErrorDetails(null)
      setAutoCheck(true)
      dataLimitInputRef.current = ''
    }
  }, [isDialogOpen])

  // Debounce form values changes
  useEffect(() => {
    const values = form.getValues()
    const timer = setTimeout(() => {
      setDebouncedValues(values)
    }, 1000) // Wait 1 second after typing stops

    return () => clearTimeout(timer)
  }, [form.watch('name'), form.watch('address'), form.watch('port'), form.watch('api_key')])

  // Auto-check connection when debounced values change and are valid
  useEffect(() => {
    if (!isDialogOpen || !autoCheck || editingNode || !debouncedValues) return

    const { name, address, port, api_key } = debouncedValues
    if (name && address && port && api_key) {
      checkNodeStatus()
    }
  }, [debouncedValues])

  // Start/stop polling when editing a node
  useEffect(() => {
    if (editingNode && isDialogOpen && editingNodeId) {
      // Start polling immediately
      checkNodeStatus()
    }
  }, [editingNode, isDialogOpen, editingNodeId])

  // Initialize form with node data when editing
  useEffect(() => {
    if (editingNode && editingNodeId) {
      const fetchNodeData = async () => {
        try {
          const nodeData = await getNode(editingNodeId)

          // Set form values with the fetched node data
          const dataLimitBytes = nodeData.data_limit ?? null
          // Convert bytes to GB for form (like user modal)
          const dataLimitGB = dataLimitBytes !== null && dataLimitBytes !== undefined && dataLimitBytes > 0 
            ? dataLimitBytes / (1024 * 1024 * 1024) 
            : 0
          
          // Initialize ref with the GB value if it exists and is > 0
          // Format to avoid floating point precision issues (max 9 decimal places)
          if (dataLimitGB > 0) {
            // Use parseFloat to remove trailing zeros, but limit to reasonable precision
            const formatted = parseFloat(dataLimitGB.toFixed(9))
            dataLimitInputRef.current = String(formatted)
          } else {
            dataLimitInputRef.current = ''
          }
          
          form.reset({
            name: nodeData.name,
            address: nodeData.address,
            port: nodeData.port,
            usage_coefficient: nodeData.usage_coefficient,
            connection_type: nodeData.connection_type,
            server_ca: nodeData.server_ca,
            keep_alive: nodeData.keep_alive,
            max_logs: nodeData.max_logs,
            api_key: (nodeData.api_key as string) || '',
            core_config_id: nodeData.core_config_id ?? cores?.cores?.[0]?.id,
            gather_logs: nodeData.gather_logs ?? true,
            data_limit: dataLimitGB,
            data_limit_reset_strategy: nodeData.data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
            reset_time: nodeData.reset_time ?? null,
          })
        } catch (error) {
          console.error('Error fetching node data:', error)
          toast.error(t('nodes.fetchFailed'))
        }
      }

      fetchNodeData()
    } else {
      // For new nodes, set default values
      form.reset({
        name: '',
        address: '',
        port: 62050,
        usage_coefficient: 1,
        connection_type: NodeConnectionType.grpc,
        server_ca: '',
        keep_alive: 60,
        keep_alive_unit: 'seconds',
        max_logs: 1000,
        api_key: '',
        core_config_id: cores?.cores?.[0]?.id,
        gather_logs: true,
        data_limit: 0,
        data_limit_reset_strategy: DataLimitResetStrategy.no_reset,
        reset_time: -1,
      })
    }
  }, [editingNode, editingNodeId, isDialogOpen, cores])

  // Set default core_config_id when cores become available and field is empty or invalid
  useEffect(() => {
    if (isDialogOpen && cores?.cores?.[0]?.id) {
      const currentValue = form.getValues('core_config_id')
      // Set default if field is empty, null, undefined, or 0 (invalid)
      if (!currentValue || currentValue < 1) {
        form.setValue('core_config_id', cores.cores[0].id, { shouldValidate: true })
      }
    }
  }, [isDialogOpen, cores, form])

  // Set default data_limit_reset_strategy to no_reset when modal opens
  useEffect(() => {
    if (isDialogOpen) {
      const currentValue = form.getValues('data_limit_reset_strategy')
      // Always set to DataLimitResetStrategy.no_reset if field is undefined or null
      if (currentValue === undefined || currentValue === null) {
        form.setValue('data_limit_reset_strategy', DataLimitResetStrategy.no_reset, { shouldValidate: true })
      }
    }
  }, [isDialogOpen, form])

  const checkNodeStatus = async () => {
    // Get current form values
    const values = form.getValues()

    // Validate required fields before checking
    if (!values.name || !values.address || !values.port) {
      return
    }

    setStatusChecking(true)
    setConnectionStatus('checking')
    setErrorDetails(null)

    try {
      if (editingNode && editingNodeId) {
        // For editing mode, use the node's endpoint directly
        const node = await getNode(editingNodeId)
        if (!node) {
          throw new Error('No node data received')
        }

        if (node.status === 'connected') {
          setConnectionStatus('success')
        } else if (node.status === 'error') {
          setConnectionStatus('error')
          setErrorDetails(node.message || 'Node has an error')
        } else {
          setConnectionStatus('idle')
          setErrorDetails(null)
        }
      } else {
        // For new nodes, we can't check status before creation
        setConnectionStatus('idle')
        setErrorDetails(t('nodeModal.statusMessages.checkUnavailableForNew'))
      }
    } catch (error: any) {
      console.error('Node status check failed:', error)
      setConnectionStatus('error')
      setErrorDetails(error?.message || 'Failed to connect to node. Please check your connection settings.')
    } finally {
      setStatusChecking(false)
    }
  }

  const onSubmit = async (values: NodeFormValues) => {
    try {
      // Convert keep_alive to seconds based on unit
      const keepAliveInSeconds = values.keep_alive_unit === 'minutes' ? values.keep_alive * 60 : values.keep_alive_unit === 'hours' ? values.keep_alive * 3600 : values.keep_alive

      // Prepare base data
      const baseData = {
        ...values,
        keep_alive: keepAliveInSeconds,
        // Remove the unit since backend doesn't need it
        keep_alive_unit: undefined,
        // Convert data_limit from GB to bytes (like user modal)
        data_limit: gbToBytes(values.data_limit),
        // reset_time: -1 means interval-based, >= 0 means absolute time
        // Send -1 as default if null/undefined, otherwise send the value
        reset_time: values.reset_time !== null && values.reset_time !== undefined ? values.reset_time : -1,
      }

      let nodeId: number | undefined

      if (editingNode && editingNodeId) {
        // For modify: convert null to DataLimitResetStrategy.no_reset, undefined means don't change
        const modifyData: typeof baseData & { data_limit_reset_strategy?: DataLimitResetStrategy | null } = {
          ...baseData,
          data_limit_reset_strategy: values.data_limit_reset_strategy !== undefined 
            ? (values.data_limit_reset_strategy === null ? DataLimitResetStrategy.no_reset : values.data_limit_reset_strategy)
            : undefined,
        }
        await modifyNodeMutation.mutateAsync({
          nodeId: editingNodeId,
          data: modifyData,
        })
        nodeId = editingNodeId
        toast.success(
          t('nodes.editSuccess', {
            name: values.name,
            defaultValue: 'Node «{name}» has been updated successfully',
          }),
        )
      } else {
        // For create: send DataLimitResetStrategy.no_reset if null/undefined, otherwise send the value
        const createData: typeof baseData & { data_limit_reset_strategy?: DataLimitResetStrategy } = {
          ...baseData,
          data_limit_reset_strategy: values.data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
        }
        const result = await addNodeMutation.mutateAsync({
          data: createData,
        })
        nodeId = result?.id
        toast.success(
          t('nodes.createSuccess', {
            name: values.name,
            defaultValue: 'Node «{name}» has been created successfully',
          }),
        )
      }

      // Check status after successful creation/editing
      if (nodeId) {
        setStatusChecking(true)
        try {
          const node = await getNode(nodeId)
          if (node && node.status === 'connected') {
            setConnectionStatus('success')
          } else if (node && node.status === 'error') {
            setConnectionStatus('error')
            setErrorDetails(node?.message || 'Node has an error')
          } else {
            setConnectionStatus('idle')
            setErrorDetails(null)
          }
        } catch (error: any) {
          setConnectionStatus('error')
          setErrorDetails(error?.message || 'Failed to check node status')
        } finally {
          setStatusChecking(false)
        }
      }

      // Invalidate nodes queries after successful operation
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })
      onOpenChange(false)
      form.reset()
    } catch (error: any) {
      const fields = ['name', 'address', 'port', 'core_config_id', 'api_key', 'max_logs', 'keep_alive_unit', 'keep_alive', 'server_ca', 'connection_type', '']
      handleError({ error, fields, form, contextKey: 'nodes' })
    }
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="h-full max-w-full sm:max-w-[90vw] lg:h-auto lg:max-w-[1000px]" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader className="pb-2">
          <DialogTitle className={cn('text-start text-base font-semibold sm:text-lg', dir === 'rtl' && 'sm:text-right')}>{editingNode ? t('editNode.title') : t('nodeModal.title')}</DialogTitle>
          <p className={cn('text-start text-xs text-muted-foreground', dir === 'rtl' && 'sm:text-right')}>{editingNode ? t('nodes.prompt') : t('nodeModal.description')}</p>
        </DialogHeader>

        {/* Status Check Results - Positioned at the top of the modal */}
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div
                className={`h-2 w-2 rounded-full ${
                  connectionStatus === 'success'
                    ? 'bg-green-500 dark:bg-green-400'
                    : connectionStatus === 'error'
                      ? 'bg-red-500 dark:bg-red-400'
                      : connectionStatus === 'checking'
                        ? 'bg-yellow-500 dark:bg-yellow-400'
                        : 'bg-gray-500 dark:bg-gray-400'
                }`}
              />
              <span className="text-sm font-medium text-foreground">
                {connectionStatus === 'success'
                  ? t('nodeModal.status.connected')
                  : connectionStatus === 'error'
                    ? t('nodeModal.status.error')
                    : connectionStatus === 'checking'
                      ? t('nodeModal.status.connecting')
                      : t('nodeModal.status.disabled')}
              </span>
              {connectionStatus === 'error' && (
                <Button variant="ghost" size="sm" onClick={() => setShowErrorDetails(!showErrorDetails)} className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground">
                  {showErrorDetails ? t('nodeModal.hideDetails') : t('nodeModal.showDetails')}
                </Button>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={checkNodeStatus} disabled={statusChecking || !form.formState.isValid} className="flex-shrink-0 px-2 text-xs">
              {statusChecking ? (
                <div className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span className="text-xs">{t('nodeModal.statusChecking')}</span>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <RefreshCw className="h-3 w-3" />
                  <span className="text-xs">{t('nodeModal.statusCheck')}</span>
                </div>
              )}
            </Button>
          </div>
          {showErrorDetails && connectionStatus === 'error' && (
            <div
              className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words rounded bg-red-50 p-3 text-xs text-red-500 dark:bg-red-900/20 dark:text-red-400"
              style={{ whiteSpace: 'pre-line' }}
            >
              {errorDetails}
            </div>
          )}
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col">
            <div className="-mr-2 max-h-[65dvh] overflow-y-auto px-1 pr-2 sm:-mr-4 sm:max-h-[65dvh] sm:px-2 sm:pr-4">
              <div className="flex h-full flex-col items-start gap-4 lg:flex-row">
                <div className="w-full flex-1 space-y-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('nodeModal.name')}</FormLabel>
                        <FormControl>
                          <Input isError={!!form.formState.errors.name} placeholder={t('nodeModal.namePlaceholder')} {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="address"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('nodeModal.address')}</FormLabel>
                          <FormControl>
                            <Input isError={!!form.formState.errors.address} placeholder={t('nodeModal.addressPlaceholder')} {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="port"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t('nodeModal.port')}</FormLabel>
                          <FormControl>
                            <Input
                              isError={!!form.formState.errors.port}
                              type="number"
                              placeholder={t('nodeModal.portPlaceholder')}
                              {...field}
                              onChange={e => field.onChange(parseInt(e.target.value))}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <FormField
                    control={form.control}
                    name="core_config_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('nodeModal.coreConfig')}</FormLabel>
                        <Select 
                          onValueChange={value => field.onChange(parseInt(value))} 
                          value={field.value ? field.value.toString() : t('nodeModal.selectCoreConfig')}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('nodeModal.selectCoreConfig')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {cores?.cores?.map((core: CoreResponse) => (
                              <SelectItem key={core.id} value={core.id.toString()}>
                                {core.name}
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
                    name="api_key"
                    render={({ field }) => {
                      const [uuidVersion, setUuidVersion] = useState<'v4' | 'v5' | 'v6' | 'v7'>('v4')

                      const generateUUID = () => {
                        switch (uuidVersion) {
                          case 'v4':
                            field.onChange(uuidv4())
                            break
                          case 'v5':
                            // Using a fixed namespace for v5 UUIDs
                            const namespace = '6ba7b810-9dad-11d1-80b4-00c04fd430c8'
                            field.onChange(uuidv5(field.value || 'default', namespace))
                            break
                          case 'v6':
                            field.onChange(uuidv6())
                            break
                          case 'v7':
                            field.onChange(uuidv7())
                            break
                        }
                      }

                      return (
                        <FormItem className={'min-h-[100px]'}>
                          <FormLabel>{t('nodeModal.apiKey')}</FormLabel>
                          <FormControl>
                            <div className="flex items-center gap-2">
                              <Input
                                isError={!!form.formState.errors.api_key}
                                type="text"
                                placeholder={t('nodeModal.apiKeyPlaceholder')}
                                autoComplete="off"
                                {...field}
                                onChange={e => field.onChange(e.target.value)}
                              />
                              <div className={cn('flex items-center gap-0', dir === 'rtl' && 'flex-row-reverse')}>
                                <Select value={uuidVersion} onValueChange={(value: 'v4' | 'v5' | 'v6' | 'v7') => setUuidVersion(value)}>
                                  <SelectTrigger className="h-10 w-[60px] rounded-r-none border-r-0">
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="v4">v4</SelectItem>
                                    <SelectItem value="v5">v5</SelectItem>
                                    <SelectItem value="v6">v6</SelectItem>
                                    <SelectItem value="v7">v7</SelectItem>
                                  </SelectContent>
                                </Select>
                                <Button type="button" variant="outline" onClick={generateUUID} className="h-10 rounded-l-none px-3">
                                  <RefreshCw className="h-3 w-3" />
                                </Button>
                              </div>
                            </div>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )
                    }}
                  />

                  <Accordion type="single" collapsible className="mb-4 mt-0 w-full pb-4">
                    <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="advanced-settings">
                      <AccordionTrigger>
                        <div className="flex items-center gap-2">
                          <Settings className="h-4 w-4" />
                          <span>{t('settings.notifications.advanced.title')}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-2">
                        <div className="flex flex-col gap-4">
                          <div className="flex flex-col gap-4 sm:flex-row">
                            <FormField
                              control={form.control}
                              name="usage_coefficient"
                              render={({ field }) => (
                                <FormItem className="flex-1">
                                  <FormLabel>{t('nodeModal.usageRatio')}</FormLabel>
                                  <FormControl>
                                    <Input
                                      isError={!!form.formState.errors.usage_coefficient}
                                      type="number"
                                      step="0.1"
                                      placeholder={t('nodeModal.usageRatioPlaceholder')}
                                      {...field}
                                      onChange={e => field.onChange(parseFloat(e.target.value))}
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="max_logs"
                              render={({ field }) => (
                                <FormItem className="flex-1">
                                  <FormLabel>{t('nodes.maxLogs')}</FormLabel>
                                  <FormControl>
                                    <Input
                                      isError={!!form.formState.errors.max_logs}
                                      type="number"
                                      placeholder={t('nodes.maxLogsPlaceholder')}
                                      {...field}
                                      onChange={e => field.onChange(parseInt(e.target.value))}
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>

                          <FormField
                            control={form.control}
                            name="connection_type"
                            render={({ field }) => (
                              <FormItem className="w-full">
                                <FormLabel>{t('nodeModal.connectionType')}</FormLabel>
                                <Select onValueChange={field.onChange} defaultValue={field.value}>
                                  <FormControl>
                                    <SelectTrigger>
                                      <SelectValue placeholder="Rest" />
                                    </SelectTrigger>
                                  </FormControl>
                                  <SelectContent>
                                    <SelectItem value={NodeConnectionType.grpc}>gRPC</SelectItem>
                                    <SelectItem value={NodeConnectionType.rest}>Rest</SelectItem>
                                  </SelectContent>
                                </Select>
                                <FormMessage />
                              </FormItem>
                            )}
                          />

                          <FormField
                            control={form.control}
                            name="keep_alive"
                            render={({ field }) => {
                              const [displayValue, setDisplayValue] = useState<string>(field.value?.toString() || '')
                              const [unit, setUnit] = useState<'seconds' | 'minutes' | 'hours'>('seconds')

                              const convertToSeconds = (value: number, fromUnit: 'seconds' | 'minutes' | 'hours') => {
                                switch (fromUnit) {
                                  case 'minutes':
                                    return value * 60
                                  case 'hours':
                                    return value * 3600
                                  default:
                                    return value
                                }
                              }

                              const convertFromSeconds = (seconds: number, toUnit: 'seconds' | 'minutes' | 'hours') => {
                                switch (toUnit) {
                                  case 'minutes':
                                    return Math.floor(seconds / 60)
                                  case 'hours':
                                    return Math.floor(seconds / 3600)
                                  default:
                                    return seconds
                                }
                              }

                              return (
                                <FormItem>
                                  <FormLabel>{t('nodeModal.keepAlive')}</FormLabel>
                                  <div className="flex flex-col gap-1.5">
                                    <p className="text-xs text-muted-foreground">{t('nodeModal.keepAliveDescription')}</p>
                                    <div className="flex flex-col gap-2 sm:flex-row">
                                      <FormControl>
                                        <Input
                                          isError={!!form.formState.errors.keep_alive}
                                          type="number"
                                          value={displayValue ?? ''}
                                          onChange={e => {
                                            const value = e.target.value
                                            setDisplayValue(value)
                                            const numValue = parseInt(value) || 0
                                            field.onChange(convertToSeconds(numValue, unit))
                                          }}
                                        />
                                      </FormControl>
                                      <Select
                                        value={unit}
                                        onValueChange={(value: 'seconds' | 'minutes' | 'hours') => {
                                          setUnit(value)
                                          const currentSeconds = field.value || 0
                                          const newDisplayValue = convertFromSeconds(currentSeconds, value)
                                          setDisplayValue(newDisplayValue.toString())
                                        }}
                                      >
                                        <SelectTrigger className="flex-1">
                                          <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                          <SelectItem value="seconds">{t('nodeModal.seconds')}</SelectItem>
                                          <SelectItem value="minutes">{t('nodeModal.minutes')}</SelectItem>
                                          <SelectItem value="hours">{t('nodeModal.hours')}</SelectItem>
                                        </SelectContent>
                                      </Select>
                                    </div>
                                  </div>
                                  <FormMessage />
                                </FormItem>
                              )
                            }}
                          />

                          <FormField
                            control={form.control}
                            name="gather_logs"
                            render={({ field }) => (
                              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                                <div className="space-y-0.5">
                                  <FormLabel className="text-sm">{t('nodeModal.gatherLogs')}</FormLabel>
                                  <p className="text-xs text-muted-foreground">{t('nodeModal.gatherLogsDescription')}</p>
                                </div>
                                <FormControl>
                                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                                </FormControl>
                              </FormItem>
                            )}
                          />

                          <div className="flex flex-col gap-4">
                            <FormField
                              control={form.control}
                              name="data_limit"
                              render={({ field }) => {
                                if (dataLimitInputRef.current === '' && field.value !== null && field.value !== undefined && field.value > 0) {
                                  // Format to avoid floating point precision issues (max 9 decimal places)
                                  const formatted = parseFloat(field.value.toFixed(9))
                                  dataLimitInputRef.current = String(formatted)
                                } else if ((field.value === null || field.value === undefined) && dataLimitInputRef.current !== '') {
                                  dataLimitInputRef.current = ''
                                }

                                const displayValue = dataLimitInputRef.current !== '' 
                                  ? dataLimitInputRef.current 
                                  : (field.value !== null && field.value !== undefined && field.value > 0 ? (() => {
                                      // Format to avoid floating point precision issues
                                      const formatted = parseFloat(field.value.toFixed(9))
                                      return String(formatted)
                                    })() : '')

                                return (
                                <FormItem className="h-full flex-1 relative">
                                  <FormLabel>{t('nodeModal.dataLimit')}</FormLabel>
                                  <FormControl>
                                    <Input
                                      isError={!!form.formState.errors.data_limit}
                                      type="text"
                                      inputMode="decimal"
                                      placeholder={t('nodeModal.dataLimitPlaceholder', { defaultValue: 'e.g. 1' })}
                                      value={displayValue}
                                      onChange={e => {
                                        const rawValue = e.target.value.trim()
                                        
                                        dataLimitInputRef.current = rawValue
                                        
                                        if (rawValue === '') {
                                          field.onChange(0)
                                          return
                                        }

                                        const validNumberPattern = /^-?\d*\.?\d*$/
                                        if (validNumberPattern.test(rawValue)) {
                                          if (rawValue.endsWith('.') && rawValue.length > 1) {
                                            const prevValue = field.value !== null && field.value !== undefined ? field.value : 0
                                            field.onChange(prevValue)
                                          } else if (rawValue === '.') {
                                            field.onChange(0)
                                          } else {
                                            const numValue = parseFloat(rawValue)
                                            if (!isNaN(numValue) && numValue >= 0) {
                                              field.onChange(numValue)
                                            }
                                          }
                                        }
                                      }}
                                      onBlur={() => {
                                        const rawValue = dataLimitInputRef.current.trim()
                                        if (rawValue === '' || rawValue === '.' || rawValue === '0') {
                                          dataLimitInputRef.current = ''
                                          field.onChange(0)
                                        } else {
                                          const numValue = parseFloat(rawValue)
                                          if (!isNaN(numValue) && numValue >= 0) {
                                            const finalValue = numValue
                                            // Format to avoid floating point precision issues (max 9 decimal places)
                                            const formatted = parseFloat(finalValue.toFixed(9))
                                            dataLimitInputRef.current = formatted > 0 ? String(formatted) : ''
                                            field.onChange(formatted)
                                          } else {
                                            dataLimitInputRef.current = ''
                                            field.onChange(0)
                                          }
                                        }
                                      }}
                                    />
                                  </FormControl>
                                  {field.value !== null && field.value !== undefined && field.value > 0 && field.value < 1 && (
                                    <p className="mt-1 text-end right-0 absolute top-full text-xs text-muted-foreground">{formatBytes(Math.round(field.value * 1024 * 1024 * 1024))}</p>
                                  )}
                                  <FormMessage />
                                </FormItem>
                                )
                              }}
                            />

                            {form.watch('data_limit') !== null && form.watch('data_limit') !== undefined && Number(form.watch('data_limit')) > 0 && (
                              <FormField
                                control={form.control}
                                name="data_limit_reset_strategy"
                                render={({ field }) => {
                                  // Convert null/undefined/no_reset to 'none' for the Select component
                                  const selectValue = (field.value === null || field.value === undefined || field.value === DataLimitResetStrategy.no_reset ? 'none' : field.value) || 'none'

                                  return (
                                  <FormItem>
                                    <FormLabel>{t('nodeModal.dataLimitResetStrategy')}</FormLabel>
                                    <Select
                                        onValueChange={value => {
                                          // Convert 'none' to DataLimitResetStrategy.no_reset, otherwise use the selected value
                                          field.onChange(value === 'none' ? DataLimitResetStrategy.no_reset : value)
                                        }}
                                        value={selectValue}
                                    >
                                      <FormControl>
                                        <SelectTrigger>
                                          <SelectValue placeholder={t('nodeModal.selectDataLimitResetStrategy')} />
                                        </SelectTrigger>
                                      </FormControl>
                                      <SelectContent>
                                        <SelectItem value="none">{t('nodeModal.noReset')}</SelectItem>
                                        <SelectItem value={DataLimitResetStrategy.day}>{t('nodeModal.day')}</SelectItem>
                                        <SelectItem value={DataLimitResetStrategy.week}>{t('nodeModal.week')}</SelectItem>
                                        <SelectItem value={DataLimitResetStrategy.month}>{t('nodeModal.month')}</SelectItem>
                                        <SelectItem value={DataLimitResetStrategy.year}>{t('nodeModal.year')}</SelectItem>
                                      </SelectContent>
                                    </Select>
                                    <FormMessage />
                                  </FormItem>
                                  )
                                }}
                              />
                            )}

                            <FormField
                              control={form.control}
                              name="reset_time"
                              render={({ field }) => {
                                const resetStrategy = form.watch('data_limit_reset_strategy')
                                
                                // Helper functions for encoding/decoding reset_time based on strategy
                                const decodeResetTime = (value: number | null | undefined, strategy: string | null | undefined): { day?: number; time: Date | null } => {
                                  if (value === null || value === undefined || value === -1 || !strategy || strategy === DataLimitResetStrategy.no_reset) {
                                    return { time: null }
                                  }

                                  const SECONDS_PER_DAY = 86400
                                  let day: number | undefined
                                  let seconds: number

                                  switch (strategy) {
                                    case DataLimitResetStrategy.day:
                                      seconds = value
                                      break
                                    case DataLimitResetStrategy.week:
                                      day = Math.floor(value / SECONDS_PER_DAY) // 0-6 (Monday-Sunday)
                                      seconds = value % SECONDS_PER_DAY
                                      break
                                    case DataLimitResetStrategy.month:
                                      day = Math.floor(value / SECONDS_PER_DAY) // 1-28
                                      seconds = value % SECONDS_PER_DAY
                                      break
                                    case DataLimitResetStrategy.year:
                                      day = Math.floor(value / SECONDS_PER_DAY) // 1-365 (day of year)
                                      seconds = value % SECONDS_PER_DAY
                                      break
                                    default:
                                      seconds = value
                                  }

                                  const hours = Math.floor(seconds / 3600)
                                  const minutes = Math.floor((seconds % 3600) / 60)
                                  const date = new Date()
                                  date.setHours(hours, minutes, 0, 0)

                                  return { day, time: date }
                                }

                                const encodeResetTime = (day: number | undefined, time: Date | null, strategy: string | null | undefined): number | null => {
                                  if (!time || !strategy || strategy === DataLimitResetStrategy.no_reset) return -1

                                  const SECONDS_PER_DAY = 86400
                                  const hours = time.getHours()
                                  const minutes = time.getMinutes()
                                  const seconds = hours * 3600 + minutes * 60

                                  switch (strategy) {
                                    case DataLimitResetStrategy.day:
                                      return seconds
                                    case DataLimitResetStrategy.week:
                                      return day !== undefined ? day * SECONDS_PER_DAY + seconds : seconds
                                    case DataLimitResetStrategy.month:
                                      return day !== undefined ? day * SECONDS_PER_DAY + seconds : seconds
                                    case DataLimitResetStrategy.year:
                                      return day !== undefined ? day * SECONDS_PER_DAY + seconds : seconds
                                    default:
                                      return seconds
                                  }
                                }

                                const decoded = decodeResetTime(field.value, resetStrategy)
                                // Always call hooks in the same order - before any conditional returns
                                const [useIntervalBased, setUseIntervalBased] = useState(field.value === -1 || field.value === null || field.value === undefined)
                                const [selectedDay, setSelectedDay] = useState<number | undefined>(decoded.day)
                                const [selectedTime, setSelectedTime] = useState<Date | null>(decoded.time)
                                const prevFieldValueRef = React.useRef<number | null | undefined>(field.value)
                                const isUpdatingFromFieldRef = React.useRef(false)
                                const prevStateRef = React.useRef<{ useIntervalBased: boolean; selectedDay?: number; selectedTime?: number; resetStrategy?: string | null }>({ 
                                  useIntervalBased, 
                                  selectedDay, 
                                  selectedTime: selectedTime?.getTime(), 
                                  resetStrategy: resetStrategy ?? undefined
                                })

                                // Update decoded values when field.value or strategy changes (only when field value actually changes from external source)
                                useEffect(() => {
                                  // Skip if we're updating from our own onChange
                                  if (isUpdatingFromFieldRef.current) {
                                    isUpdatingFromFieldRef.current = false
                                    prevFieldValueRef.current = field.value
                                    return
                                  }
                                  
                                  // Only update if field.value actually changed
                                  if (prevFieldValueRef.current === field.value && prevStateRef.current.resetStrategy === resetStrategy) {
                                    return
                                  }
                                  
                                  prevFieldValueRef.current = field.value
                                  const newDecoded = decodeResetTime(field.value, resetStrategy)
                                  const newUseIntervalBased = field.value === -1 || field.value === null || field.value === undefined
                                  
                                  setUseIntervalBased(newUseIntervalBased)
                                  setSelectedDay(newDecoded.day)
                                  setSelectedTime(newDecoded.time)
                                  prevStateRef.current = { 
                                    useIntervalBased: newUseIntervalBased, 
                                    selectedDay: newDecoded.day, 
                                    selectedTime: newDecoded.time?.getTime(), 
                                    resetStrategy: resetStrategy ?? undefined
                                  }
                                }, [field.value, resetStrategy])

                                // Update field when day or time changes (but skip if updating from field.value change)
                                useEffect(() => {
                                  if (!resetStrategy || resetStrategy === DataLimitResetStrategy.no_reset) {
                                    return
                                  }
                                  
                                  // Check if state actually changed
                                  const stateChanged = 
                                    prevStateRef.current.useIntervalBased !== useIntervalBased ||
                                    prevStateRef.current.selectedDay !== selectedDay ||
                                    prevStateRef.current.selectedTime !== selectedTime?.getTime() ||
                                    prevStateRef.current.resetStrategy !== resetStrategy
                                  
                                  if (!stateChanged) {
                                    return
                                  }
                                  
                                  prevStateRef.current = { useIntervalBased, selectedDay, selectedTime: selectedTime?.getTime(), resetStrategy }
                                  
                                  let newValue: number | null
                                  
                                  if (useIntervalBased) {
                                    newValue = -1
                                  } else {
                                    newValue = encodeResetTime(selectedDay, selectedTime, resetStrategy)
                                  }
                                  
                                  // Only update if value actually changed
                                  if (newValue !== null && newValue !== field.value) {
                                    isUpdatingFromFieldRef.current = true
                                    field.onChange(newValue)
                                  }
                                }, [useIntervalBased, selectedDay, selectedTime, resetStrategy, field.value])

                                // Get day options based on strategy
                                const getDayOptions = () => {
                                  switch (resetStrategy) {
                                    case DataLimitResetStrategy.week:
                                      return [
                                        { value: 0, label: t('nodeModal.monday', { defaultValue: 'Monday' }) },
                                        { value: 1, label: t('nodeModal.tuesday', { defaultValue: 'Tuesday' }) },
                                        { value: 2, label: t('nodeModal.wednesday', { defaultValue: 'Wednesday' }) },
                                        { value: 3, label: t('nodeModal.thursday', { defaultValue: 'Thursday' }) },
                                        { value: 4, label: t('nodeModal.friday', { defaultValue: 'Friday' }) },
                                        { value: 5, label: t('nodeModal.saturday', { defaultValue: 'Saturday' }) },
                                        { value: 6, label: t('nodeModal.sunday', { defaultValue: 'Sunday' }) },
                                      ]
                                    case DataLimitResetStrategy.month:
                                      return Array.from({ length: 28 }, (_, i) => ({
                                        value: i + 1,
                                        label: String(i + 1),
                                      }))
                                    case DataLimitResetStrategy.year:
                                      // For year, we need month + day
                                      // This is more complex, so we'll use a simpler approach with day of year
                                      return Array.from({ length: 365 }, (_, i) => ({
                                        value: i + 1,
                                        label: `${i + 1}`,
                                      }))
                                    default:
                                      return []
                                  }
                                }

                                const dayOptions = getDayOptions()
                                const dataLimit = form.watch('data_limit')

                                // Only show reset_time if data_limit is set and strategy is set and not "no_reset"
                                if (!dataLimit || dataLimit === null || dataLimit === undefined || Number(dataLimit) <= 0 || !resetStrategy || resetStrategy === DataLimitResetStrategy.no_reset) {
                                  return <></>
                                }

                                return (
                                  <FormItem>
                                    <div className="space-y-3">
                                      <div className="flex items-center justify-between">
                                    <FormLabel>{t('nodeModal.resetTime')}</FormLabel>
                                        <div className="flex items-center gap-2">
                                          <span className="text-xs text-muted-foreground">
                                            {useIntervalBased 
                                              ? t('nodeModal.intervalBased', { defaultValue: 'Interval-based' })
                                              : t('nodeModal.absoluteTime', { defaultValue: 'Absolute time' })}
                                          </span>
                                          <Switch
                                            checked={!useIntervalBased}
                                            onCheckedChange={(checked) => {
                                              const newUseIntervalBased = !checked
                                              setUseIntervalBased(newUseIntervalBased)
                                              
                                              if (newUseIntervalBased) {
                                                // Switching to interval-based, set to -1
                                                isUpdatingFromFieldRef.current = true
                                                field.onChange(-1)
                                              } else {
                                                // Switching to absolute time, set default based on strategy
                                                const defaultDay = resetStrategy === DataLimitResetStrategy.week ? 0 
                                                  : resetStrategy === DataLimitResetStrategy.month ? 1
                                                  : resetStrategy === DataLimitResetStrategy.year ? 1
                                                  : undefined
                                                const defaultTime = new Date()
                                                defaultTime.setHours(0, 0, 0, 0)
                                                setSelectedDay(defaultDay)
                                                setSelectedTime(defaultTime)
                                                // The useEffect will handle updating the field value
                                              }
                                            }}
                                          />
                                        </div>
                                      </div>
                                      
                                      {!useIntervalBased && (
                                        <div className="space-y-3">
                                          {dayOptions.length > 0 && (
                                            <Select
                                              value={selectedDay?.toString() || ''}
                                              onValueChange={(value) => {
                                                setSelectedDay(parseInt(value))
                                              }}
                                            >
                                              <SelectTrigger>
                                                <SelectValue placeholder={
                                                  resetStrategy === DataLimitResetStrategy.week
                                                    ? t('nodeModal.selectDayOfWeek', { defaultValue: 'Select day of week' })
                                                    : resetStrategy === DataLimitResetStrategy.month
                                                    ? t('nodeModal.selectDayOfMonth', { defaultValue: 'Select day of month' })
                                                    : t('nodeModal.selectDayOfYear', { defaultValue: 'Select day of year' })
                                                } />
                                              </SelectTrigger>
                                              <SelectContent>
                                                {dayOptions.map((option) => (
                                                  <SelectItem key={option.value} value={option.value.toString()}>
                                                    {option.label}
                                                  </SelectItem>
                                                ))}
                                              </SelectContent>
                                            </Select>
                                          )}
                                          
                                          <Input
                                            type="time"
                                            value={selectedTime 
                                              ? `${String(selectedTime.getHours()).padStart(2, '0')}:${String(selectedTime.getMinutes()).padStart(2, '0')}` 
                                              : ''}
                                            onChange={(e) => {
                                              const [hours, minutes] = e.target.value.split(':')
                                              if (hours && minutes) {
                                                const newTime = new Date()
                                                newTime.setHours(parseInt(hours), parseInt(minutes), 0, 0)
                                                setSelectedTime(newTime)
                                              } else {
                                                setSelectedTime(null)
                                              }
                                            }}
                                            placeholder={t('nodeModal.resetTimePlaceholder', { defaultValue: 'Select time' })}
                                            dir="ltr"
                                          />
                                        </div>
                                      )}
                                      
                                      {useIntervalBased && (
                                        <p className="text-xs text-muted-foreground">
                                          {t('nodeModal.intervalBasedDescription', { 
                                            defaultValue: 'Reset will occur every period from the last reset time'
                                          })}
                                        </p>
                                      )}
                                    </div>
                                    <FormMessage />
                                  </FormItem>
                                )
                              }}
                            />
                          </div>
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  </Accordion>
                </div>
                <FormField
                  control={form.control}
                  name="server_ca"
                  render={({ field }) => (
                    <FormItem className="h-full w-full flex-1 pb-4 lg:mb-0">
                      <FormLabel>{t('nodeModal.certificate')}</FormLabel>
                      <FormControl>
                        <Textarea
                          dir="ltr"
                          placeholder={t('nodeModal.certificatePlaceholder')}
                          className={cn('h-[200px] font-mono text-xs lg:h-5/6', !!form.formState.errors.server_ca && 'border-destructive')}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-3">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={addNodeMutation.isPending || modifyNodeMutation.isPending} size="sm">
                {t('cancel')}
              </Button>
              <LoaderButton
                type="submit"
                disabled={addNodeMutation.isPending || modifyNodeMutation.isPending}
                isLoading={addNodeMutation.isPending || modifyNodeMutation.isPending}
                loadingText={editingNode ? t('modifying') : t('creating')}
                size="sm"
              >
                {editingNode ? t('modify') : t('create')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}