import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import useDirDetection from '@/hooks/use-dir-detection'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { cn } from '@/lib/utils'
import { CoreResponse, DataLimitResetStrategy, getNode, NodeConnectionType, NodeResponse, useCreateNode, useGetAllCores, useGetNode, useModifyNode } from '@/service/api'
import { formatBytes, gbToBytes } from '@/utils/formatByte'
import { queryClient } from '@/utils/query-client'
import { Loader2, RefreshCw, Settings } from 'lucide-react'
import React, { useEffect, useRef, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { v4 as uuidv4 } from 'uuid'
import { z } from 'zod'
import { LoaderButton } from '../ui/loader-button'

export const nodeFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  address: z.string().min(1, 'Address is required'),
  port: z.number().min(1, 'Port is required'),
  api_port: z.number().min(1).optional().nullable(),
  usage_coefficient: z.number().optional(),
  connection_type: z.enum([NodeConnectionType.grpc, NodeConnectionType.rest]),
  server_ca: z.string().min(1, 'Server CA is required'),
  keep_alive: z.number().min(0, 'Keep alive must be 0 or greater'),
  keep_alive_unit: z.enum(['seconds', 'minutes', 'hours']).default('seconds'),
  api_key: z.string().min(1, 'API key is required'),
  core_config_id: z.number().min(1, 'Core configuration is required'),
  data_limit: z.number().min(0).optional().nullable(),
  data_limit_reset_strategy: z.nativeEnum(DataLimitResetStrategy).optional().nullable(),
  reset_time: z.union([z.null(), z.undefined(), z.number().min(-1)]),
  default_timeout: z.number().min(3, 'Default timeout must be 3 or greater').max(60, 'Default timeout must be 60 or lower').optional(),
  internal_timeout: z.number().min(3, 'Internal timeout must be 3 or greater').max(60, 'Internal timeout must be 60 or lower').optional(),
  user_data_limit: z.number().min(0).optional().nullable(),
  user_data_limit_reset_strategy: z.nativeEnum(DataLimitResetStrategy).optional().nullable(),
  user_reset_time: z.union([z.null(), z.undefined(), z.number().min(-1)]),
})

export type NodeFormValues = z.infer<typeof nodeFormSchema>

interface NodeModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<NodeFormValues>
  editingNode: boolean
  editingNodeId?: number
  initialNodeData?: NodeResponse
}

export default function NodeModal({ isDialogOpen, onOpenChange, form, editingNode, editingNodeId, initialNodeData }: NodeModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const addNodeMutation = useCreateNode()
  const modifyNodeMutation = useModifyNode()
  const handleError = useDynamicErrorHandler()
  const { data: cores } = useGetAllCores()
  const [statusChecking, setStatusChecking] = useState(false)
  const [errorDetails, setErrorDetails] = useState<string | null>(null)
  const [autoCheck, setAutoCheck] = useState(false)
  const [showErrorDetails, setShowErrorDetails] = useState(false)
  const [debouncedValues, setDebouncedValues] = useState<NodeFormValues | null>(null)
  const [isFetchingNodeData, setIsFetchingNodeData] = useState(false)
  const dataLimitInputRef = React.useRef<string>('')
  const userDataLimitInputRef = React.useRef<string>('')

  const { data: node, refetch: refetchNode } = useGetNode(
    editingNodeId || 0,
    editingNode && editingNodeId
      ? {
          query: {
            enabled: editingNode && !!editingNodeId && isDialogOpen,
            initialData: initialNodeData,
            refetchInterval: 5000,
            refetchOnMount: false,
            staleTime: 0,
            gcTime: 0,
          },
        }
      : { query: { enabled: false } },
  )

  const currentNode = node || initialNodeData
  const lastSyncedNodeRef = useRef<NodeResponse | null>(null)

  useEffect(() => {
    if (isDialogOpen) {
      setErrorDetails(null)
      setAutoCheck(true)
      dataLimitInputRef.current = ''
      setIsFetchingNodeData(false)
      lastSyncedNodeRef.current = null
    }
  }, [isDialogOpen])

  // Update form when node data changes (from auto-refresh or external updates)
  useEffect(() => {
    if (!isDialogOpen || !editingNode || !editingNodeId || !node) return

    // Skip if form is dirty (user has made changes)
    if (form.formState.isDirty) return

    // Skip if this is the same node data we already synced
    // Compare key fields that change externally (status, message, versions, usage)
    const lastSynced = lastSyncedNodeRef.current
    if (
      lastSynced &&
      lastSynced.id === node.id &&
      lastSynced.status === node.status &&
      lastSynced.message === node.message &&
      lastSynced.xray_version === node.xray_version &&
      lastSynced.node_version === node.node_version &&
      lastSynced.uplink === node.uplink &&
      lastSynced.downlink === node.downlink &&
      lastSynced.name === node.name &&
      lastSynced.address === node.address &&
      lastSynced.port === node.port
    ) {
      return
    }

    // Update form with new node data
    const dataLimitBytes = node.data_limit ?? null
    const dataLimitGB = dataLimitBytes !== null && dataLimitBytes !== undefined && dataLimitBytes > 0 ? dataLimitBytes / (1024 * 1024 * 1024) : 0

    if (dataLimitGB > 0) {
      const formatted = parseFloat(dataLimitGB.toFixed(9))
      dataLimitInputRef.current = String(formatted)
    } else {
      dataLimitInputRef.current = ''
    }

    form.reset(
      {
        name: node.name,
        address: node.address,
        port: node.port,
        api_port: node.api_port ?? null,
        usage_coefficient: node.usage_coefficient,
        connection_type: node.connection_type,
        server_ca: node.server_ca,
        keep_alive: node.keep_alive,
        api_key: (node.api_key as string) || '',
        core_config_id: node.core_config_id ?? cores?.cores?.[0]?.id,
        data_limit: dataLimitGB,
        data_limit_reset_strategy: node.data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
        reset_time: node.reset_time ?? null,
        default_timeout: node.default_timeout ?? 10,
        internal_timeout: node.internal_timeout ?? 15,
        user_data_limit: null,
      },
      { keepDirty: false, keepValues: false },
    )

    lastSyncedNodeRef.current = node
  }, [node, isDialogOpen, editingNode, editingNodeId, form, cores])

  useEffect(() => {
    const values = form.getValues()
    const timer = setTimeout(() => {
      setDebouncedValues(values)
    }, 1000)

    return () => clearTimeout(timer)
  }, [form.watch('name'), form.watch('address'), form.watch('port'), form.watch('api_key')])

  useEffect(() => {
    if (!isDialogOpen || !autoCheck || editingNode || !debouncedValues) return

    const { name, address, port, api_key } = debouncedValues
    if (name && address && port && api_key) {
      checkNodeStatus()
    }
  }, [debouncedValues])

  useEffect(() => {
    if (editingNode && isDialogOpen && editingNodeId) {
      checkNodeStatus()
    }
  }, [editingNode, isDialogOpen, editingNodeId])
  useEffect(() => {
    if (editingNode && editingNodeId) {
      if (initialNodeData) {
        const nodeData = initialNodeData

        const dataLimitBytes = nodeData.data_limit ?? null
        const dataLimitGB = dataLimitBytes !== null && dataLimitBytes !== undefined && dataLimitBytes > 0 ? dataLimitBytes / (1024 * 1024 * 1024) : 0

        if (dataLimitGB > 0) {
          const formatted = parseFloat(dataLimitGB.toFixed(9))
          dataLimitInputRef.current = String(formatted)
        } else {
          dataLimitInputRef.current = ''
        }

        const userDataLimitBytes = nodeData.user_data_limit ?? null
        const userDataLimitGB = userDataLimitBytes !== null && userDataLimitBytes !== undefined && userDataLimitBytes > 0 ? userDataLimitBytes / (1024 * 1024 * 1024) : 0

        form.reset({
          name: nodeData.name,
          address: nodeData.address,
          port: nodeData.port,
          api_port: nodeData.api_port ?? null,
          usage_coefficient: nodeData.usage_coefficient,
          connection_type: nodeData.connection_type,
          server_ca: nodeData.server_ca,
          keep_alive: nodeData.keep_alive,
          api_key: (nodeData.api_key as string) || '',
          core_config_id: nodeData.core_config_id ?? cores?.cores?.[0]?.id,
          data_limit: dataLimitGB,
          data_limit_reset_strategy: nodeData.data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
          reset_time: nodeData.reset_time ?? null,
          default_timeout: nodeData.default_timeout ?? 10,
          internal_timeout: nodeData.internal_timeout ?? 15,
          user_data_limit: userDataLimitGB,
          user_data_limit_reset_strategy: nodeData.user_data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
          user_reset_time: nodeData.user_reset_time ?? -1,
        })
        lastSyncedNodeRef.current = nodeData
        setIsFetchingNodeData(false)
      } else {
        const fetchNodeData = async () => {
          setIsFetchingNodeData(true)
          try {
            const nodeData = await getNode(editingNodeId)

            const dataLimitBytes = nodeData.data_limit ?? null
            const dataLimitGB = dataLimitBytes !== null && dataLimitBytes !== undefined && dataLimitBytes > 0 ? dataLimitBytes / (1024 * 1024 * 1024) : 0

            if (dataLimitGB > 0) {
              const formatted = parseFloat(dataLimitGB.toFixed(9))
              dataLimitInputRef.current = String(formatted)
            } else {
              dataLimitInputRef.current = ''
            }

            const userDataLimitBytes = nodeData.user_data_limit ?? null
            const userDataLimitGB = userDataLimitBytes !== null && userDataLimitBytes !== undefined && userDataLimitBytes > 0 ? userDataLimitBytes / (1024 * 1024 * 1024) : 0

            form.reset({
              name: nodeData.name,
              address: nodeData.address,
              port: nodeData.port,
              api_port: nodeData.api_port ?? null,
              usage_coefficient: nodeData.usage_coefficient,
              connection_type: nodeData.connection_type,
              server_ca: nodeData.server_ca,
              keep_alive: nodeData.keep_alive,
              api_key: (nodeData.api_key as string) || '',
              core_config_id: nodeData.core_config_id ?? cores?.cores?.[0]?.id,
              data_limit: dataLimitGB,
              data_limit_reset_strategy: nodeData.data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
              reset_time: nodeData.reset_time ?? null,
              default_timeout: nodeData.default_timeout ?? 10,
              internal_timeout: nodeData.internal_timeout ?? 15,
              user_data_limit: userDataLimitGB,
              user_data_limit_reset_strategy: nodeData.user_data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
              user_reset_time: nodeData.user_reset_time ?? -1,
            })
            lastSyncedNodeRef.current = nodeData
          } catch (error) {
            console.error('Error fetching node data:', error)
            toast.error(t('nodes.fetchFailed'))
          } finally {
            setIsFetchingNodeData(false)
          }
        }

        fetchNodeData()
      }
    } else {
      form.reset({
        name: '',
        address: '',
        port: 62050,
        api_port: 62051,
        usage_coefficient: 1,
        connection_type: NodeConnectionType.grpc,
        server_ca: '',
        keep_alive: 60,
        keep_alive_unit: 'seconds',
        api_key: '',
        core_config_id: cores?.cores?.[0]?.id,
        data_limit: 0,
        data_limit_reset_strategy: DataLimitResetStrategy.no_reset,
        reset_time: -1,
        default_timeout: 10,
        internal_timeout: 15,
      })
    }
  }, [editingNode, editingNodeId, isDialogOpen, cores, initialNodeData, form])

  useEffect(() => {
    if (isDialogOpen && cores?.cores?.[0]?.id) {
      const currentValue = form.getValues('core_config_id')
      if (!currentValue || currentValue < 1) {
        form.setValue('core_config_id', cores.cores[0].id, { shouldValidate: true })
      }
    }
  }, [isDialogOpen, cores, form])

  useEffect(() => {
    if (isDialogOpen) {
      const currentValue = form.getValues('data_limit_reset_strategy')
      if (currentValue === undefined || currentValue === null) {
        form.setValue('data_limit_reset_strategy', DataLimitResetStrategy.no_reset, { shouldValidate: true })
      }
    }
  }, [isDialogOpen, form])

  const checkNodeStatus = async () => {
    const values = form.getValues()

    if (!values.name || !values.address || !values.port) {
      return
    }

    setStatusChecking(true)
    setErrorDetails(null)

    try {
      if (editingNode && editingNodeId) {
        await refetchNode()
      } else {
        setErrorDetails(t('nodeModal.statusMessages.checkUnavailableForNew'))
      }
    } catch (error: any) {
      console.error('Node status check failed:', error)
      setErrorDetails(error?.message || 'Failed to connect to node. Please check your connection settings.')
    } finally {
      setStatusChecking(false)
    }
  }
  useEffect(() => {
    if (currentNode?.status === 'error') {
      setErrorDetails(currentNode.message || 'Node has an error')
    } else if (currentNode?.status) {
      setErrorDetails(null)
    }
  }, [currentNode?.status, currentNode?.message])

  const onSubmit = async (values: NodeFormValues) => {
    try {
      const keepAliveInSeconds = values.keep_alive_unit === 'minutes' ? values.keep_alive * 60 : values.keep_alive_unit === 'hours' ? values.keep_alive * 3600 : values.keep_alive

      const baseData = {
        ...values,
        keep_alive: keepAliveInSeconds,
        keep_alive_unit: undefined,
        data_limit: gbToBytes(values.data_limit),
        reset_time: values.reset_time !== null && values.reset_time !== undefined ? values.reset_time : -1,
        api_port: values.api_port ?? undefined,
        user_data_limit: gbToBytes(values.user_data_limit) ?? null,
        user_data_limit_reset_strategy: values.user_data_limit_reset_strategy ?? DataLimitResetStrategy.no_reset,
        user_reset_time: values.user_reset_time !== null && values.user_reset_time !== undefined ? values.user_reset_time : -1,
      }

      let nodeId: number | undefined

      if (editingNode && editingNodeId) {
        const modifyData: typeof baseData & { data_limit_reset_strategy?: DataLimitResetStrategy | null } = {
          ...baseData,
          data_limit_reset_strategy:
            values.data_limit_reset_strategy !== undefined ? (values.data_limit_reset_strategy === null ? DataLimitResetStrategy.no_reset : values.data_limit_reset_strategy) : undefined,
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

      if (nodeId && editingNode) {
        queryClient.invalidateQueries({ queryKey: [`/api/node/${nodeId}`] })
        lastSyncedNodeRef.current = null
      }
      queryClient.invalidateQueries({ queryKey: ['/api/nodes'] })

      // Apply bulk user limits if set
      if (nodeId && values.user_data_limit !== null && values.user_data_limit !== undefined) {
        const token = localStorage.getItem('token')
        await fetch(`/api/node-user-limits/bulk-set`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            node_id: nodeId,
            data_limit: Math.floor(values.user_data_limit * 1073741824), // GB to bytes
            data_limit_reset_strategy: values.user_data_limit_reset_strategy || 'no_reset',
            reset_time: values.user_reset_time ?? -1,
          }),
        })
        toast.success(t('nodes.userLimits.bulkApplySuccess'))
      }

      onOpenChange(false)
      form.reset()
    } catch (error: any) {
      const fields = ['name', 'address', 'port', 'core_config_id', 'api_key', 'keep_alive_unit', 'keep_alive', 'server_ca', 'connection_type', '']
      handleError({ error, fields, form, contextKey: 'nodes' })
    }
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="h-full max-w-full focus:outline-none sm:max-w-[90vw] lg:h-auto lg:max-w-[1000px]" onOpenAutoFocus={e => e.preventDefault()}>
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
                  currentNode?.status === 'connecting' || (statusChecking && !currentNode?.status)
                    ? 'bg-yellow-500 dark:bg-yellow-400'
                    : currentNode?.status === 'connected'
                      ? 'bg-green-500 dark:bg-green-400'
                      : currentNode?.status === 'error'
                        ? 'bg-red-500 dark:bg-red-400'
                        : 'bg-gray-500 dark:bg-gray-400'
                }`}
              />
              <span className="text-sm font-medium text-foreground">
                {currentNode?.status === 'connecting' || (statusChecking && !currentNode?.status)
                  ? t('nodeModal.status.connecting')
                  : currentNode?.status === 'connected'
                    ? t('nodeModal.status.connected')
                    : currentNode?.status === 'error'
                      ? t('nodeModal.status.error')
                      : t('nodeModal.status.disabled')}
              </span>
              {currentNode?.status === 'error' && (
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
          {showErrorDetails && currentNode?.status === 'error' && (
            <div
              dir="ltr"
              className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words rounded bg-red-50 p-3 text-xs text-red-500 dark:bg-red-900/20 dark:text-red-400"
              style={{ whiteSpace: 'pre-line' }}
            >
              {errorDetails || currentNode?.message}
            </div>
          )}
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col">
            <div
              className={cn(
                '-mr-2 overflow-y-auto px-1 pr-2 sm:-mr-4 sm:px-2 sm:pr-4',
                showErrorDetails && currentNode?.status === 'error' ? 'max-h-[55dvh] sm:max-h-[55dvh]' : 'max-h-[65dvh] sm:max-h-[65dvh]',
                isFetchingNodeData && 'pointer-events-none blur-sm',
              )}
            >
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
                        <Select onValueChange={value => field.onChange(parseInt(value))} value={field.value ? field.value.toString() : t('nodeModal.selectCoreConfig')}>
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
                      const generateUUID = () => {
                        field.onChange(uuidv4())
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
                  <Accordion type="single" collapsible className="!mt-0 mb-4 w-full pb-4">
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
                              name="api_port"
                              render={({ field }) => (
                                <FormItem className="flex-1">
                                  <FormLabel>{t('nodeModal.apiPort')}</FormLabel>
                                  <FormControl>
                                    <Input
                                      isError={!!form.formState.errors.api_port}
                                      type="number"
                                      placeholder={t('nodeModal.apiPortPlaceholder')}
                                      {...field}
                                      value={field.value ?? ''}
                                      onChange={e => {
                                        const value = e.target.value
                                        if (value === '') {
                                          field.onChange(null)
                                        } else {
                                          const numValue = parseInt(value)
                                          if (!isNaN(numValue) && numValue > 0) {
                                            field.onChange(numValue)
                                          }
                                        }
                                      }}
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

                          <div className="flex flex-col gap-4">
                            <FormField
                              control={form.control}
                              name="data_limit"
                              render={({ field }) => {
                                if (dataLimitInputRef.current === '' && field.value !== null && field.value !== undefined && field.value > 0) {
                                  const formatted = parseFloat(field.value.toFixed(9))
                                  dataLimitInputRef.current = String(formatted)
                                } else if ((field.value === null || field.value === undefined) && dataLimitInputRef.current !== '') {
                                  dataLimitInputRef.current = ''
                                }

                                const displayValue =
                                  dataLimitInputRef.current !== ''
                                    ? dataLimitInputRef.current
                                    : field.value !== null && field.value !== undefined && field.value > 0
                                      ? (() => {
                                          const formatted = parseFloat(field.value.toFixed(9))
                                          return String(formatted)
                                        })()
                                      : ''

                                return (
                                  <FormItem className="relative h-full flex-1">
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
                                      <p className="absolute right-0 top-full mt-1 text-end text-xs text-muted-foreground">{formatBytes(Math.round(field.value * 1024 * 1024 * 1024))}</p>
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
                                  const selectValue = (field.value === null || field.value === undefined || field.value === DataLimitResetStrategy.no_reset ? 'none' : field.value) || 'none'

                                  return (
                                    <FormItem>
                                      <FormLabel>{t('nodeModal.dataLimitResetStrategy')}</FormLabel>
                                      <Select
                                        onValueChange={value => {
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
                              name="user_data_limit"
                              render={({ field }) => {
                                if (userDataLimitInputRef.current === '' && field.value !== null && field.value !== undefined && field.value > 0) {
                                  userDataLimitInputRef.current = String(field.value)
                                } else if ((field.value === null || field.value === undefined) && userDataLimitInputRef.current !== '') {
                                  userDataLimitInputRef.current = ''
                                }

                                const displayValue =
                                  userDataLimitInputRef.current !== '' ? userDataLimitInputRef.current : field.value !== null && field.value !== undefined && field.value > 0 ? String(field.value) : ''

                                return (
                                  <FormItem className="relative h-full flex-1">
                                    <FormLabel>{t('nodes.userLimits.perUserDataLimit', 'Data Limit Per User (GB)')}</FormLabel>
                                    <FormControl>
                                      <Input
                                        isError={!!form.formState.errors.user_data_limit}
                                        type="text"
                                        inputMode="decimal"
                                        placeholder={t('nodeModal.dataLimitPlaceholder', { defaultValue: 'e.g. 1' })}
                                        value={displayValue}
                                        onChange={e => {
                                          const rawValue = e.target.value.trim()
                                          userDataLimitInputRef.current = rawValue
                                          if (rawValue === '') {
                                            field.onChange(null)
                                            return
                                          }
                                          const validNumberPattern = /^-?\d*\.?\d*$/
                                          if (validNumberPattern.test(rawValue)) {
                                            if (rawValue.endsWith('.') && rawValue.length > 1) {
                                              field.onChange(field.value)
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
                                          const rawValue = userDataLimitInputRef.current.trim()
                                          if (rawValue === '' || rawValue === '.' || rawValue === '0') {
                                            userDataLimitInputRef.current = ''
                                            field.onChange(null)
                                          } else {
                                            const numValue = parseFloat(rawValue)
                                            if (!isNaN(numValue) && numValue >= 0) {
                                              userDataLimitInputRef.current = String(numValue)
                                              field.onChange(numValue)
                                            } else {
                                              userDataLimitInputRef.current = ''
                                              field.onChange(null)
                                            }
                                          }
                                        }}
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )
                              }}
                            />

                            {form.watch('user_data_limit') !== null && form.watch('user_data_limit') !== undefined && Number(form.watch('user_data_limit')) > 0 && (
                              <FormField
                                control={form.control}
                                name="user_data_limit_reset_strategy"
                                render={({ field }) => {
                                  const selectValue = (field.value === null || field.value === undefined || field.value === DataLimitResetStrategy.no_reset ? 'none' : field.value) || 'none'

                                  return (
                                    <FormItem>
                                      <FormLabel>{t('nodeModal.perUserResetStrategy', 'Per-User Reset Strategy')}</FormLabel>
                                      <Select
                                        onValueChange={value => {
                                          field.onChange(value === 'none' ? DataLimitResetStrategy.no_reset : value)
                                        }}
                                        value={selectValue}
                                      >
                                        <FormControl>
                                          <SelectTrigger>
                                            <SelectValue placeholder={t('nodeModal.selectResetStrategy')} />
                                          </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                          <SelectItem value="none">{t('nodeModal.noReset', 'No Reset')}</SelectItem>
                                          <SelectItem value={DataLimitResetStrategy.day}>{t('nodeModal.day', 'Day')}</SelectItem>
                                          <SelectItem value={DataLimitResetStrategy.week}>{t('nodeModal.week', 'Week')}</SelectItem>
                                          <SelectItem value={DataLimitResetStrategy.month}>{t('nodeModal.month', 'Month')}</SelectItem>
                                          <SelectItem value={DataLimitResetStrategy.year}>{t('nodeModal.year', 'Year')}</SelectItem>
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
                                      day = Math.floor(value / SECONDS_PER_DAY)
                                      seconds = value % SECONDS_PER_DAY
                                      break
                                    case DataLimitResetStrategy.month:
                                      day = Math.floor(value / SECONDS_PER_DAY)
                                      seconds = value % SECONDS_PER_DAY
                                      break
                                    case DataLimitResetStrategy.year:
                                      day = Math.floor(value / SECONDS_PER_DAY)
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
                                const [useIntervalBased, setUseIntervalBased] = useState(field.value === -1 || field.value === null || field.value === undefined)
                                const [selectedDay, setSelectedDay] = useState<number | undefined>(decoded.day)
                                const [selectedTime, setSelectedTime] = useState<Date | null>(decoded.time)
                                const prevFieldValueRef = React.useRef<number | null | undefined>(field.value)
                                const isUpdatingFromFieldRef = React.useRef(false)
                                const prevStateRef = React.useRef<{ useIntervalBased: boolean; selectedDay?: number; selectedTime?: number; resetStrategy?: string | null }>({
                                  useIntervalBased,
                                  selectedDay,
                                  selectedTime: selectedTime?.getTime(),
                                  resetStrategy: resetStrategy ?? undefined,
                                })

                                useEffect(() => {
                                  if (isUpdatingFromFieldRef.current) {
                                    isUpdatingFromFieldRef.current = false
                                    prevFieldValueRef.current = field.value
                                    return
                                  }

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
                                    resetStrategy: resetStrategy ?? undefined,
                                  }
                                }, [field.value, resetStrategy])

                                useEffect(() => {
                                  if (!resetStrategy || resetStrategy === DataLimitResetStrategy.no_reset) {
                                    return
                                  }

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

                                  if (newValue !== null && newValue !== field.value) {
                                    isUpdatingFromFieldRef.current = true
                                    field.onChange(newValue)
                                  }
                                }, [useIntervalBased, selectedDay, selectedTime, resetStrategy, field.value])

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
                                            {useIntervalBased ? t('nodeModal.intervalBased', { defaultValue: 'Interval-based' }) : t('nodeModal.absoluteTime', { defaultValue: 'Absolute time' })}
                                          </span>
                                          <Switch
                                            checked={!useIntervalBased}
                                            onCheckedChange={checked => {
                                              const newUseIntervalBased = !checked
                                              setUseIntervalBased(newUseIntervalBased)

                                              if (newUseIntervalBased) {
                                                isUpdatingFromFieldRef.current = true
                                                field.onChange(-1)
                                              } else {
                                                const defaultDay =
                                                  resetStrategy === DataLimitResetStrategy.week
                                                    ? 0
                                                    : resetStrategy === DataLimitResetStrategy.month
                                                      ? 1
                                                      : resetStrategy === DataLimitResetStrategy.year
                                                        ? 1
                                                        : undefined
                                                const defaultTime = new Date()
                                                defaultTime.setHours(0, 0, 0, 0)
                                                setSelectedDay(defaultDay)
                                                setSelectedTime(defaultTime)
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
                                              onValueChange={value => {
                                                setSelectedDay(parseInt(value))
                                              }}
                                            >
                                              <SelectTrigger>
                                                <SelectValue
                                                  placeholder={
                                                    resetStrategy === DataLimitResetStrategy.week
                                                      ? t('nodeModal.selectDayOfWeek', { defaultValue: 'Select day of week' })
                                                      : resetStrategy === DataLimitResetStrategy.month
                                                        ? t('nodeModal.selectDayOfMonth', { defaultValue: 'Select day of month' })
                                                        : t('nodeModal.selectDayOfYear', { defaultValue: 'Select day of year' })
                                                  }
                                                />
                                              </SelectTrigger>
                                              <SelectContent>
                                                {dayOptions.map(option => (
                                                  <SelectItem key={option.value} value={option.value.toString()}>
                                                    {option.label}
                                                  </SelectItem>
                                                ))}
                                              </SelectContent>
                                            </Select>
                                          )}

                                          <Input
                                            type="time"
                                            value={selectedTime ? `${String(selectedTime.getHours()).padStart(2, '0')}:${String(selectedTime.getMinutes()).padStart(2, '0')}` : ''}
                                            onChange={e => {
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
                                            defaultValue: 'Reset will occur every period from the last reset time',
                                          })}
                                        </p>
                                      )}
                                    </div>
                                    <FormMessage />
                                  </FormItem>
                                )
                              }}
                            />
                            <div className="flex flex-col gap-2 sm:flex-row">
                              <FormField
                                control={form.control}
                                name="default_timeout"
                                render={({ field }) => (
                                  <FormItem className="flex-1">
                                    <FormLabel>{t('nodeModal.defaultTimeout')}</FormLabel>
                                    <FormControl>
                                      <Input
                                        isError={!!form.formState.errors.default_timeout}
                                        type="number"
                                        step="1"
                                        placeholder={t('nodeModal.defaultTimeoutPlaceholder')}
                                        {...field}
                                        onChange={e => field.onChange(parseInt(e.target.value))}
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name="internal_timeout"
                                render={({ field }) => (
                                  <FormItem className="flex-1">
                                    <FormLabel>{t('nodeModal.internalTimeout')}</FormLabel>
                                    <FormControl>
                                      <Input
                                        isError={!!form.formState.errors.internal_timeout}
                                        type="number"
                                        step="1"
                                        placeholder={t('nodeModal.internalTimeoutPlaceholder')}
                                        {...field}
                                        onChange={e => field.onChange(parseInt(e.target.value))}
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>
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
