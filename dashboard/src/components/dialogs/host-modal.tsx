import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { VariablesList, VariablesPopover } from '@/components/ui/variables-popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { UserStatus, getHosts, getInbounds } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { useQuery } from '@tanstack/react-query'
import { Cable, Check, ChevronsLeftRightEllipsis, Copy, Edit, GlobeLock, Info, Lock, Network, Plus, Route, Trash2, X } from 'lucide-react'
import { memo, useCallback, useMemo, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { HostFormValues } from '../hosts/hosts-list'
import { LoaderButton } from '../ui/loader-button'

interface HostModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: HostFormValues) => Promise<{ status: number }>
  editingHost?: boolean
  form: UseFormReturn<HostFormValues>
}

// Update status options constant
const statusOptions = [
  { value: UserStatus.active, label: 'hostsDialog.status.active' },
  { value: UserStatus.disabled, label: 'hostsDialog.status.disabled' },
  { value: UserStatus.limited, label: 'hostsDialog.status.limited' },
  { value: UserStatus.expired, label: 'hostsDialog.status.expired' },
  { value: UserStatus.on_hold, label: 'hostsDialog.status.onHold' },
] as const

// Memoized Noise Item Component for optimal performance
interface NoiseItemProps {
  index: number
  form: UseFormReturn<HostFormValues>
  onRemove: (index: number) => void
  onDuplicate: (index: number) => void
  t: (key: string) => string
}

const NoiseItem = memo<NoiseItemProps>(({ index, form, onRemove, onDuplicate, t }) => {
  const handleRemove = useCallback(() => {
    onRemove(index)
  }, [index, onRemove])

  const handleDuplicate = useCallback(() => {
    onDuplicate(index)
  }, [index, onDuplicate])

  return (
    <div className="grid grid-cols-2 gap-2 rounded-md border p-2 md:grid-cols-[minmax(100px,120px),1fr,1fr,1fr,auto] md:border-none md:p-0">
      <FormField
        control={form.control}
        name={`noise_settings.xray.${index}.type`}
        render={({ field }) => (
          <FormItem>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger className="h-8">
                  <SelectValue placeholder={t('hostsDialog.noise.type')} />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem value="rand">rand</SelectItem>
                <SelectItem value="str">str</SelectItem>
                <SelectItem value="base64">base64</SelectItem>
                <SelectItem value="hex">hex</SelectItem>
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`noise_settings.xray.${index}.packet`}
        render={({ field }) => (
          <FormItem className="order-3 md:order-none">
            <FormControl>
              <Input placeholder={t('hostsDialog.noise.packetPlaceholder')} {...field} value={field.value || ''} className="h-8" />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`noise_settings.xray.${index}.delay`}
        render={({ field }) => (
          <FormItem className="order-4 md:order-none">
            <FormControl>
              <Input placeholder={t('hostsDialog.noise.delayPlaceholder')} {...field} value={field.value || ''} className="h-8" />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`noise_settings.xray.${index}.apply_to`}
        render={({ field }) => (
          <FormItem className="order-2 md:order-none">
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger className="h-8">
                  <SelectValue placeholder={t('hostsDialog.noise.applyTo')} />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem value="ip">ip</SelectItem>
                <SelectItem value="ipv4">ipv4</SelectItem>
                <SelectItem value="ipv6">ipv6</SelectItem>
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="order-5 col-span-2 flex items-center justify-end gap-1 md:order-none md:col-auto md:justify-start">
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0 transition-colors hover:bg-muted/70" onClick={handleDuplicate} title={t('hostsDialog.noise.duplicateNoise')}>
          <Copy className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
          onClick={handleRemove}
          title={t('hostsDialog.noise.removeNoise')}
        >
          <Trash2 className="h-4 w-4 text-red-500" />
        </Button>
      </div>
    </div>
  )
})

NoiseItem.displayName = 'NoiseItem'

// Reusable ArrayInput component for type-and-enter functionality
interface ArrayInputProps {
  field: any
  placeholder: string
  label: string
  infoContent?: React.ReactNode
}

const ArrayInput = memo<ArrayInputProps>(({ field, placeholder, label, infoContent }) => {
  const [inputValue, setInputValue] = useState('')
  const [isPopoverOpen, setIsPopoverOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editingValue, setEditingValue] = useState('')
  const { t } = useTranslation()
  const dir = useDirDetection()

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault()
      addItem()
    } else if (e.key === 'Escape') {
      setInputValue('')
      setIsPopoverOpen(false)
    }
  }

  const handleEditKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    if (e.key === 'Enter' && editingValue.trim()) {
      e.preventDefault()
      saveEdit(index)
    } else if (e.key === 'Escape') {
      cancelEdit()
    }
  }

  const addItem = () => {
    if (inputValue.trim()) {
      const currentValue = field.value || []
      const trimmedValue = inputValue.trim()

      // Prevent duplicates
      if (!currentValue.includes(trimmedValue)) {
        const newValue = [...currentValue, trimmedValue]
        field.onChange(newValue)
        setInputValue('')
      } else {
        // Show visual feedback for duplicate
        toast.error(t('arrayInput.duplicateError'))
      }
    }
  }

  const removeItem = (index: number) => {
    const currentValue = field.value || []
    const newValue = currentValue.filter((_: any, i: number) => i !== index)
    field.onChange(newValue)
    setEditingIndex(null)
    setEditingValue('')
  }

  const startEdit = (index: number, currentValue: string) => {
    setEditingIndex(index)
    setEditingValue(currentValue)
  }

  const saveEdit = (index: number) => {
    if (editingValue.trim()) {
      const currentValue = field.value || []
      const trimmedValue = editingValue.trim()

      // Check for duplicates (excluding the current item being edited)
      const isDuplicate = currentValue.some((item: string, i: number) => i !== index && item === trimmedValue)

      if (!isDuplicate) {
        const newValue = [...currentValue]
        newValue[index] = trimmedValue
        field.onChange(newValue)
        setEditingIndex(null)
        setEditingValue('')
      } else {
        toast.error(t('arrayInput.duplicateError'))
      }
    }
  }

  const cancelEdit = () => {
    setEditingIndex(null)
    setEditingValue('')
  }

  const displayValue = field.value && field.value.length > 0 ? (field.value.length <= 3 ? field.value.join(', ') : `${field.value.slice(0, 3).join(', ')}... (+${field.value.length - 3} more)`) : ''

  return (
    <FormItem>
      <div dir="ltr" className="flex items-center gap-2">
        <FormLabel>{label}</FormLabel>
        {infoContent && (
          <Popover>
            <PopoverTrigger asChild>
              <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                <Info className="h-4 w-4 text-muted-foreground" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[280px] p-3 sm:w-[320px]" side="top" align="start" sideOffset={5}>
              <div className="space-y-1.5">
                <h4 className="mb-2 text-[12px] font-medium">{t('hostsDialog.variables.title')}</h4>
                <div className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">{infoContent}</div>
              </div>
            </PopoverContent>
          </Popover>
        )}
      </div>
      <Popover
        open={isPopoverOpen}
        onOpenChange={open => {
          // Only close if we're not in edit mode
          if (!open && editingIndex === null) {
            setIsPopoverOpen(false)
          } else if (open) {
            setIsPopoverOpen(true)
          }
        }}
      >
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" className="h-auto w-full min-w-0 p-2 text-left" title={displayValue || placeholder}>
            <span className={`max-w-[100px] flex-1 truncate sm:max-w-none ${displayValue ? 'text-foreground' : 'text-muted-foreground'}`} title={displayValue || placeholder}>
              {displayValue || placeholder}
            </span>
            <div className="ml-2 flex shrink-0 items-center gap-1">
              {field.value && field.value.length > 0 && (
                <Badge variant="secondary" className="px-1.5 py-0.5 text-xs">
                  {field.value.length}
                </Badge>
              )}
              <ChevronsLeftRightEllipsis className="h-3 w-3 text-muted-foreground" />
            </div>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(90vw,400px)] p-3" align={dir === 'rtl' ? 'end' : 'start'} side="bottom" dir={dir}>
          <div className="max-h-64 space-y-3 overflow-y-auto">
            {/* Input for adding new items with submit button */}
            <div className="m-1.5 flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input
                placeholder={t('arrayInput.addPlaceholder')}
                value={inputValue}
                onChange={e => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                className="min-w-0 flex-1 text-sm"
                autoFocus={isPopoverOpen}
              />
              <Button type="button" size="sm" variant="default" onClick={addItem} disabled={!inputValue.trim()} className="h-8 w-full shrink-0 px-3 py-1 sm:w-auto" title={t('arrayInput.addButton')}>
                <Plus className="h-4 w-4" />
                <span className="ml-1 sm:hidden">{t('arrayInput.addButton')}</span>
              </Button>
            </div>

            {/* Selected items list */}
            {field.value && field.value.length > 0 && (
              <div dir="ltr" className="space-y-2">
                <div dir={dir} className="text-xs font-medium text-muted-foreground">
                  {t('arrayInput.items')} ({field.value.length})
                </div>
                <div className="max-h-48 space-y-1 overflow-y-auto">
                  {field.value.map((item: string, index: number) => (
                    <div key={index} className="group flex min-w-0 items-center gap-2 rounded-md border p-2 transition-colors hover:bg-accent/50" onClick={e => e.stopPropagation()}>
                      {editingIndex === index ? (
                        <Input
                          value={editingValue}
                          onChange={e => setEditingValue(e.target.value)}
                          onKeyDown={e => handleEditKeyDown(e, index)}
                          className="h-7 min-w-0 flex-1 text-sm"
                          autoFocus
                          onBlur={e => {
                            // Only save if the blur is not caused by clicking a button
                            if (!e.relatedTarget || !e.relatedTarget.closest('button')) {
                              saveEdit(index)
                            }
                          }}
                          dir="ltr"
                        />
                      ) : (
                        <span
                          className="min-w-0 flex-1 cursor-text truncate text-sm leading-tight transition-colors hover:text-primary"
                          onClick={() => startEdit(index, item)}
                          title={t('arrayInput.clickToEdit')}
                        >
                          {item}
                        </span>
                      )}

                      <div className="flex shrink-0 items-center gap-1">
                        {editingIndex === index ? (
                          <>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={e => {
                                e.preventDefault()
                                e.stopPropagation()
                                saveEdit(index)
                              }}
                              className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                              title={t('arrayInput.saveEdit')}
                              disabled={!editingValue.trim()}
                            >
                              <Check className="h-3 w-3" />
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={e => {
                                e.preventDefault()
                                e.stopPropagation()
                                cancelEdit()
                              }}
                              className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                              title={t('arrayInput.cancelEdit')}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </>
                        ) : (
                          <>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={e => {
                                e.preventDefault()
                                e.stopPropagation()
                                startEdit(index, item)
                              }}
                              className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                              title={t('arrayInput.editItem')}
                            >
                              <Edit className="h-3 w-3" />
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={e => {
                                e.preventDefault()
                                e.stopPropagation()
                                removeItem(index)
                              }}
                              className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                              title={t('arrayInput.removeItem')}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(!field.value || field.value.length === 0) && <div className="py-6 text-center text-sm text-muted-foreground">{t('arrayInput.noItems')}</div>}
          </div>
        </PopoverContent>
      </Popover>
      <FormMessage />
    </FormItem>
  )
})

ArrayInput.displayName = 'ArrayInput'

const HostModal: React.FC<HostModalProps> = ({ isDialogOpen, onOpenChange, onSubmit, editingHost, form }) => {
  const [openSection, setOpenSection] = useState<string | undefined>(undefined)
  const [isTransportOpen, setIsTransportOpen] = useState(false)
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [_isSubmitting, setIsSubmitting] = useState(false)
  const xPaddingObfsEnabled = form.watch('transport_settings.xhttp_settings.x_padding_obfs_mode') === true

  // Optimized noise settings handlers with useCallback for performance
  const addNoiseSetting = useCallback(() => {
    const currentNoiseSettings = form.getValues('noise_settings.xray') || []
    form.setValue(
      'noise_settings.xray',
      [
        ...currentNoiseSettings,
        {
          type: 'rand',
          packet: '',
          delay: '',
          apply_to: 'ip',
        },
      ],
      {
        shouldDirty: true,
        shouldTouch: true,
      },
    )
  }, [form])

  const removeNoiseSetting = useCallback(
    (index: number) => {
      const currentNoiseSettings = form.getValues('noise_settings.xray') || []
      const newNoiseSettings = currentNoiseSettings.filter((_, i) => i !== index)
      form.setValue('noise_settings.xray', newNoiseSettings, {
        shouldDirty: true,
        shouldTouch: true,
      })
    },
    [form],
  )

  const duplicateNoiseSetting = useCallback(
    (index: number) => {
      const currentNoiseSettings = form.getValues('noise_settings.xray') || []
      const targetNoise = currentNoiseSettings[index]
      if (!targetNoise) {
        return
      }

      const duplicatedNoise = { ...targetNoise }
      const newNoiseSettings = [...currentNoiseSettings.slice(0, index + 1), duplicatedNoise, ...currentNoiseSettings.slice(index + 1)]

      form.setValue('noise_settings.xray', newNoiseSettings, {
        shouldDirty: true,
        shouldTouch: true,
      })
    },
    [form],
  )

  // Memoized noise settings array to prevent unnecessary re-renders
  const noiseSettings = useMemo(() => {
    return form.getValues('noise_settings.xray') || []
  }, [form.watch('noise_settings.xray')])

  const cleanPayload = (data: any): any => {
    // Helper function to check if an object has any non-empty values
    const hasNonEmptyValues = (obj: any): boolean => {
      if (!obj || typeof obj !== 'object') return false
      return Object.values(obj).some(value => {
        if (value === null || value === undefined || value === '') return false
        if (typeof value === 'object') return hasNonEmptyValues(value)
        return true
      })
    }

    // Helper function to clean nested objects
    const cleanObject = (obj: any, path: string[] = []): any => {
      const result: any = {}
      Object.entries(obj).forEach(([key, value]) => {
        const currentPath = [...path, key]

        // Always preserve priority field even if it's 0
        if (key === 'priority') {
          result[key] = value
          return
        }

        // Always preserve boolean values (including false)
        if (typeof value === 'boolean') {
          result[key] = value
          return
        }

        if (value === null || value === undefined || value === '') return

        if (typeof value === 'object' && !Array.isArray(value)) {
          const cleanedNested = cleanObject(value, currentPath)
          if (Object.keys(cleanedNested).length > 0) {
            result[key] = cleanedNested
          }
        } else if (Array.isArray(value)) {
          if (value.length > 0) {
            result[key] = value
          }
        } else {
          result[key] = value
        }
      })
      return result
    }

    return cleanObject(data)
  }

  const handleModalOpenChange = (open: boolean) => {
    if (!open) {
      // Let the parent component handle the form reset
      setOpenSection(undefined)
    }
    onOpenChange(open)
  }

  const { data: inbounds = [] } = useQuery({
    queryKey: ['getInboundsQueryKey'],
    queryFn: () => getInbounds(),
  })

  // Update the hosts query to refetch only when needed (not on dialog open)
  const { data: hosts = [] } = useQuery({
    queryKey: ['getHostsQueryKey'],
    queryFn: () => getHosts(),
    enabled: isTransportOpen,
    select: data => data.filter(host => host.id != null),
  })

  // No automatic refresh when dialog opens - only fetch on specific actions

  const handleAccordionChange = (value: string) => {
    if (value === 'transport') {
      setIsTransportOpen(true)
    }
    setOpenSection(prevSection => (prevSection === value ? undefined : value))
  }

  const handleSubmit = async (data: HostFormValues) => {
    setIsSubmitting(true)
    try {
      // Clean the payload before sending
      const payload = { ...data }

      // If SingBox fragment is disabled, clear related fields
      if (!payload.fragment_settings?.sing_box?.fragment && payload.fragment_settings?.sing_box) {
        const singBox = payload.fragment_settings.sing_box!
        ;(singBox as any).fragment_fallback_delay = undefined
        ;(singBox as any).record_fragment = undefined
      }

      // Convert fragment_fallback_delay number to ms format
      if (payload.fragment_settings?.sing_box?.fragment_fallback_delay) {
        const delay = payload.fragment_settings.sing_box.fragment_fallback_delay
        if (/^\d+$/.test(delay)) {
          payload.fragment_settings.sing_box.fragment_fallback_delay = delay + 'ms'
        }
      }

      const cleanedData = cleanPayload(payload)
      const response = await onSubmit(cleanedData)
      if (response.status >= 400) {
        throw new Error(`Operation failed with status: ${response.status}`)
      }
      handleModalOpenChange(false)
      queryClient.invalidateQueries({
        queryKey: ['getHostsQueryKey'],
      })
    } catch (error) {
      console.error(error)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleModalOpenChange}>
      <DialogContent className="h-full w-full max-w-2xl sm:max-h-[95dvh] sm:py-4" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className={cn('mt-2', dir === 'rtl' ? 'text-right' : 'text-left')}>{editingHost ? t('editHost.title') : t('hostsDialog.addHost')}</DialogTitle>
          <DialogDescription className="sr-only">Modify the host settings below</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            <div className="-mr-4 max-h-[80dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <FormField
                control={form.control}
                name="inbound_tag"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('inbound')}</FormLabel>
                    <Select dir={dir} onValueChange={field.onChange} value={field.value}>
                      <FormControl className={cn(!!form.formState.errors.inbound_tag && 'border-destructive')}>
                        <SelectTrigger className="py-5">
                          <SelectValue placeholder={t('hostsDialog.selectInbound')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent dir="ltr">
                        {inbounds.map(tag => (
                          <SelectItem className="cursor-pointer px-4" value={tag} key={tag}>
                            {tag}
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
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('hostsDialog.status.label')}</FormLabel>
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap gap-1">
                        {field.value && field.value.length > 0 ? (
                          field.value.map(status => {
                            const option = statusOptions.find(opt => opt.value === status)
                            if (!option) return null
                            return (
                              <span key={status} className="flex items-center gap-2 rounded-md bg-muted/80 px-2 py-1 text-sm">
                                {t(option.label)}
                                <button
                                  type="button"
                                  className="hover:text-destructive"
                                  onClick={() => {
                                    field.onChange(field.value.filter(s => s !== status))
                                  }}
                                >
                                  ×
                                </button>
                              </span>
                            )
                          })
                        ) : (
                          <span className="text-sm text-muted-foreground">{t('hostsDialog.noStatus')}</span>
                        )}
                      </div>
                      <Select
                        value=""
                        onValueChange={(value: UserStatus) => {
                          if (!value) return
                          const currentValue = field.value || []
                          if (!currentValue.includes(value)) {
                            field.onChange([...currentValue, value])
                          }
                        }}
                      >
                        <FormControl>
                          <SelectTrigger dir={dir} className="w-full py-5">
                            <SelectValue placeholder={t('hostsDialog.selectStatus')} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent dir={dir} className="bg-background">
                          {statusOptions.map(option => (
                            <SelectItem
                              key={option.value}
                              value={option.value}
                              className="flex cursor-pointer items-center gap-2 px-4 py-2 focus:bg-accent"
                              disabled={field.value?.includes(option.value)}
                            >
                              <div className="flex w-full items-center gap-3">
                                <Checkbox checked={field.value?.includes(option.value)} className="h-4 w-4" />
                                <span className="text-sm font-normal">{t(option.label)}</span>
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {field.value && field.value.length > 0 && (
                        <Button type="button" variant="outline" size="sm" onClick={() => field.onChange([])} className="w-full">
                          {t('hostsDialog.clearAllStatuses')}
                        </Button>
                      )}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="remark"
                render={({ field }) => (
                  <FormItem>
                    <div className="flex items-center gap-2">
                      <FormLabel>{t('remark')}</FormLabel>
                      <VariablesPopover includeProtocolTransport />
                    </div>
                    <FormControl>
                      <Input placeholder="Remark (e.g. PasarGuard-Host)" isError={!!form.formState.errors.remark} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="!mb-4 flex justify-between gap-4">
                <div className="flex-[2]">
                  <FormField
                    control={form.control}
                    name="address"
                    render={({ field }) => {
                      const infoContent = <VariablesList includeProtocolTransport />

                      return <ArrayInput field={field} placeholder="example.com" label={t('hostsDialog.address')} infoContent={infoContent} />
                    }}
                  />
                </div>
                <div className="flex-1">
                  <FormField
                    control={form.control}
                    name="port"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center gap-2">
                          <FormLabel>{t('hostsDialog.port')}</FormLabel>
                          <Popover>
                            <PopoverTrigger asChild>
                              <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                <Info className="h-4 w-4 text-muted-foreground" />
                              </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                              <p className="text-[11px] text-muted-foreground">{t('hostsDialog.port.info')}</p>
                            </PopoverContent>
                          </Popover>
                        </div>
                        <FormControl>
                          <Input
                            placeholder="443"
                            isError={!!form.formState.errors.port}
                            type="number"
                            {...field}
                            onChange={e => {
                              const val = e.target.value
                              field.onChange(val === '' ? '' : Number.parseInt(val, 10))
                            }}
                            value={field.value === null || field.value === undefined ? '' : field.value}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>

              <Accordion type="single" collapsible value={openSection} onValueChange={handleAccordionChange} className="!mt-0 mb-6 flex w-full flex-col gap-y-6">
                <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="network">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <GlobeLock className="h-4 w-4" />
                      <span>{t('hostsDialog.networkSettings')}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-2">
                    <div className="space-y-6">
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <FormField
                          control={form.control}
                          name="host"
                          render={({ field }) => {
                            const infoContent = (
                              <div className="space-y-1.5">
                                <p className="text-[11px] text-muted-foreground">{t('hostsDialog.host.info')}</p>
                                <p className="text-[11px] text-muted-foreground">{t('hostsDialog.host.multiHost')}</p>
                                <p className="text-[11px] text-muted-foreground">{t('hostsDialog.host.wildcard')}</p>
                              </div>
                            )

                            return <ArrayInput field={field} placeholder="example.com" label={t('hostsDialog.host')} infoContent={infoContent} />
                          }}
                        />
                        <FormField
                          control={form.control}
                          name="path"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center gap-2">
                                <FormLabel>{t('hostsDialog.path')}</FormLabel>
                                <Popover>
                                  <PopoverTrigger asChild>
                                    <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                      <Info className="h-4 w-4 text-muted-foreground" />
                                    </Button>
                                  </PopoverTrigger>
                                  <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                                    <p className="text-[11px] text-muted-foreground">{t('hostsDialog.path.info')}</p>
                                  </PopoverContent>
                                </Popover>
                              </div>
                              <FormControl>
                                <Input placeholder="Path (e.g. /xray)" {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      <FormField
                        control={form.control}
                        name="random_user_agent"
                        render={({ field }) => (
                          <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                            <div className="space-y-0.5">
                              <FormLabel className="text-base">{t('hostsDialog.randomUserAgent')}</FormLabel>
                            </div>
                            <FormControl>
                              <div onClick={e => e.stopPropagation()}>
                                <Switch checked={field.value} onCheckedChange={field.onChange} />
                              </div>
                            </FormControl>
                          </FormItem>
                        )}
                      />

                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <h4 className="text-sm font-medium">{t('hostsDialog.httpHeaders')}</h4>
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => {
                              const currentHeaders = form.getValues('http_headers') || {}
                              const newKey = `header_${Object.keys(currentHeaders).length + 1}`
                              form.setValue(
                                'http_headers',
                                {
                                  ...currentHeaders,
                                  [newKey]: '',
                                },
                                {
                                  shouldDirty: true,
                                  shouldTouch: true,
                                },
                              )
                            }}
                            title={t('hostsDialog.addHeader')}
                          >
                            <Plus className="h-4 w-4" />
                          </Button>
                        </div>
                        <div className="space-y-2">
                          {Object.entries(form.watch('http_headers') || {}).map(([key, value]) => (
                            <div key={key} className="grid grid-cols-[minmax(120px,1fr),1fr,auto] gap-2">
                              <Input
                                placeholder={t('hostsDialog.headersName')}
                                defaultValue={key}
                                onBlur={e => {
                                  if (e.target.value !== key) {
                                    const currentHeaders = { ...form.getValues('http_headers') }
                                    const oldValue = currentHeaders[key]
                                    delete currentHeaders[key]
                                    currentHeaders[e.target.value] = oldValue
                                    form.setValue('http_headers', currentHeaders, {
                                      shouldDirty: true,
                                      shouldTouch: true,
                                    })
                                  }
                                }}
                              />
                              <Input
                                placeholder={t('hostsDialog.headersValue')}
                                value={value || ''}
                                onChange={e => {
                                  const currentHeaders = { ...form.getValues('http_headers') }
                                  currentHeaders[key] = e.target.value
                                  form.setValue('http_headers', currentHeaders, {
                                    shouldDirty: true,
                                    shouldTouch: true,
                                  })
                                }}
                              />
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 shrink-0 border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                                onClick={() => {
                                  const currentHeaders = { ...form.getValues('http_headers') }
                                  delete currentHeaders[key]
                                  form.setValue('http_headers', currentHeaders, {
                                    shouldDirty: true,
                                    shouldTouch: true,
                                  })
                                }}
                                title={t('hostsDialog.removeHeader')}
                              >
                                <Trash2 className="h-4 w-4 text-red-500" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="security">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Lock className="h-4 w-4" />
                      <span>{t('hostsDialog.securitySettings')}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-2">
                    <div className="space-y-6">
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <FormField
                          control={form.control}
                          name="security"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center gap-2">
                                <FormLabel>{t('hostsDialog.security')}</FormLabel>
                                <Popover>
                                  <PopoverTrigger asChild>
                                    <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                      <Info className="h-4 w-4 text-muted-foreground" />
                                    </Button>
                                  </PopoverTrigger>
                                  <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                                    <p className="text-[11px] text-muted-foreground">{t('hostsDialog.security.info')}</p>
                                  </PopoverContent>
                                </Popover>
                              </div>
                              <Select onValueChange={field.onChange} value={field.value}>
                                <FormControl>
                                  <SelectTrigger>
                                    <SelectValue />
                                  </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                  <SelectItem value="none">None</SelectItem>
                                  <SelectItem value="tls">TLS</SelectItem>
                                  <SelectItem value="inbound_default">Inbound's default</SelectItem>
                                </SelectContent>
                              </Select>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="sni"
                          render={({ field }) => {
                            const infoContent = (
                              <div className="space-y-1.5">
                                <p className="text-[11px] text-muted-foreground">{t('hostsDialog.sni.info')}</p>
                              </div>
                            )

                            return <ArrayInput field={field} placeholder={t('hostsDialog.sniPlaceholder')} label={t('hostsDialog.sni')} infoContent={infoContent} />
                          }}
                        />
                      </div>

                      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <FormField
                          control={form.control}
                          name="alpn"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('hostsDialog.alpn')}</FormLabel>
                              <Popover>
                                <PopoverTrigger asChild>
                                  <Button variant="outline" role="combobox" className="h-auto min-h-[40px] w-full justify-between p-2">
                                    <div className="flex flex-1 flex-wrap gap-2">
                                      {field.value && field.value.length > 0 ? (
                                        field.value.map((protocol: string) => (
                                          <Badge key={protocol} variant="secondary" className="flex items-center gap-1">
                                            {protocol}
                                            <X
                                              className="h-3 w-3 cursor-pointer hover:text-destructive"
                                              onClick={e => {
                                                e.stopPropagation()
                                                const newValue = (field.value || []).filter((p: string) => p !== protocol)
                                                field.onChange(newValue)
                                              }}
                                            />
                                          </Badge>
                                        ))
                                      ) : (
                                        <span className="text-sm text-muted-foreground">{t('hostsDialog.selectAlpn', 'Select ALPN protocols')}</span>
                                      )}
                                    </div>
                                  </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-full p-1" align="start">
                                  <div className="space-y-1">
                                    {['h3', 'h2', 'http/1.1'].map(protocol => {
                                      const isSelected = field.value?.includes(protocol)
                                      return (
                                        <div
                                          key={protocol}
                                          onClick={() => {
                                            const currentValue = field.value || []
                                            const newValue = isSelected ? currentValue.filter((p: string) => p !== protocol) : [...currentValue, protocol]
                                            field.onChange(newValue)
                                          }}
                                          className="flex cursor-pointer items-center gap-2 rounded-sm p-2 hover:bg-accent"
                                        >
                                          <div className={cn('mr-2 flex h-4 w-4 items-center justify-center rounded-sm border', isSelected ? 'border-primary bg-primary' : 'border-muted')}>
                                            {isSelected && <X className="h-3 w-3 text-primary-foreground" />}
                                          </div>
                                          {protocol}
                                        </div>
                                      )
                                    })}
                                  </div>
                                </PopoverContent>
                              </Popover>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="fingerprint"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('hostsDialog.fingerprint')}</FormLabel>
                              <Select onValueChange={value => field.onChange(value === 'default' ? '' : value)} value={field.value || 'default'}>
                                <FormControl>
                                  <SelectTrigger>
                                    <SelectValue placeholder={t('hostsDialog.fingerprint')} />
                                  </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                  <SelectItem value="default">{t('default')}</SelectItem>
                                  <SelectItem value="chrome">{t('chrome')}</SelectItem>
                                  <SelectItem value="firefox">{t('firefox')}</SelectItem>
                                  <SelectItem value="safari">{t('safari')}</SelectItem>
                                  <SelectItem value="ios">{t('ios')}</SelectItem>
                                  <SelectItem value="android">{t('android')}</SelectItem>
                                  <SelectItem value="edge">{t('edge')}</SelectItem>
                                  <SelectItem value="360">{t('360')}</SelectItem>
                                  <SelectItem value="qq">{t('qq')}</SelectItem>
                                  <SelectItem value="random">{t('random')}</SelectItem>
                                  <SelectItem value="randomized">{t('randomized')}</SelectItem>
                                  <SelectItem value="randomizednoalpn">{t('randomizednoalpn')}</SelectItem>
                                  <SelectItem value="unsafe">{t('unsafe')}</SelectItem>
                                </SelectContent>
                              </Select>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      <FormField
                        control={form.control}
                        name="allowinsecure"
                        render={({ field }) => (
                          <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                            <div className="space-y-0.5">
                              <FormLabel className="text-base">{t('hostsDialog.allowInsecure')}</FormLabel>
                            </div>
                            <FormControl>
                              <div onClick={e => e.stopPropagation()}>
                                <Switch checked={field.value} onCheckedChange={field.onChange} />
                              </div>
                            </FormControl>
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="use_sni_as_host"
                        render={({ field }) => (
                          <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                            <div className="space-y-0.5">
                              <FormLabel className="text-base">{t('hostsDialog.useSniAsHost')}</FormLabel>
                            </div>
                            <FormControl>
                              <div onClick={e => e.stopPropagation()}>
                                <Switch checked={field.value} onCheckedChange={field.onChange} />
                              </div>
                            </FormControl>
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="ech_config_list"
                        render={({ field }) => (
                          <FormItem>
                            <div className="flex items-center gap-2">
                              <FormLabel>{t('hostsDialog.echConfigList')}</FormLabel>
                              <Popover>
                                <PopoverTrigger asChild>
                                  <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                    <Info className="h-4 w-4 text-muted-foreground" />
                                  </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                                  <p className="text-[11px] text-muted-foreground">{t('hostsDialog.echConfigList.info')}</p>
                                </PopoverContent>
                              </Popover>
                            </div>
                            <FormControl>
                              <Input placeholder={t('hostsDialog.echConfigListPlaceholder')} {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="routing">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Route className="h-4 w-4" />
                      <span>{t('hostsDialog.routingSettings')}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-2">
                    <FormField
                      control={form.control}
                      name="vless_route"
                      render={({ field }) => (
                        <FormItem>
                          <div className="flex items-center gap-2">
                            <FormLabel>{t('hostsDialog.vlessRoute')}</FormLabel>
                            <Popover>
                              <PopoverTrigger asChild>
                                <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                  <Info className="h-4 w-4 text-muted-foreground" />
                                </Button>
                              </PopoverTrigger>
                              <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                                <p className="text-[11px] text-muted-foreground">{t('hostsDialog.vlessRoute.info')}</p>
                              </PopoverContent>
                            </Popover>
                          </div>
                          <FormControl>
                            <Input
                              placeholder={t('hostsDialog.vlessRoutePlaceholder')}
                              maxLength={4}
                              value={field.value ?? ''}
                              onChange={e => {
                                const normalized = e.target.value.replace(/[^0-9a-fA-F]/g, '').slice(0, 4)
                                field.onChange(normalized)
                              }}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="transport">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Network className="h-4 w-4" />
                      <span>{t('hostsDialog.transportSettingsAccordion')}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-4">
                      <Tabs defaultValue="xhttp" className="w-full">
                        <div className="flex w-full items-center justify-center">
                          <TabsList className="mb-4 flex h-auto w-full flex-wrap gap-1 overflow-x-auto px-1 sm:w-fit sm:flex-nowrap sm:gap-4">
                            <TabsTrigger className="flex-1 px-1 text-xs sm:flex-none sm:px-2 sm:text-sm" value="xhttp">
                              <span className="hidden sm:inline">XHTTP</span>
                              <span className="text-[11.5px] sm:hidden">XHTTP</span>
                            </TabsTrigger>
                            <TabsTrigger className="flex-1 px-1 text-xs sm:flex-none sm:px-2 sm:text-sm" value="grpc">
                              <span className="hidden sm:inline">gRPC</span>
                              <span className="text-[11.5px] sm:hidden">gRPC</span>
                            </TabsTrigger>
                            <TabsTrigger className="flex-1 px-1 text-xs sm:flex-none sm:px-2 sm:text-sm" value="kcp">
                              <span className="hidden sm:inline">KCP</span>
                              <span className="text-[11.5px] sm:hidden">KCP</span>
                            </TabsTrigger>
                            <TabsTrigger className="flex-1 px-1 text-xs sm:flex-none sm:px-2 sm:text-sm" value="tcp">
                              <span className="hidden sm:inline">TCP</span>
                              <span className="text-[11.5px] sm:hidden">TCP</span>
                            </TabsTrigger>
                            <TabsTrigger className="flex-1 px-1 text-xs sm:flex-none sm:px-2 sm:text-sm" value="websocket">
                              <span className="hidden sm:inline">WebSocket</span>
                              <span className="text-[11.5px] sm:hidden">WS</span>
                            </TabsTrigger>
                          </TabsList>
                        </div>

                        {/* XHTTP Settings */}
                        <TabsContent dir={dir} value="xhttp" className="space-y-4 p-2">
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <FormField
                              control={form.control}
                              name="transport_settings.xhttp_settings.mode"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.xhttp.mode')}</FormLabel>
                                  <Select
                                    onValueChange={value => field.onChange(value === '__default' ? undefined : value)}
                                    value={field.value ?? '__default'}
                                  >
                                    <FormControl>
                                      <SelectTrigger>
                                        <SelectValue />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      <SelectItem value="__default">{t('hostsDialog.xhttp.defaultMode', { defaultValue: 'Use default' })}</SelectItem>
                                      <SelectItem value="auto">Auto</SelectItem>
                                      <SelectItem value="packet-up">Packet Up</SelectItem>
                                      <SelectItem value="stream-up">Stream Up</SelectItem>
                                      <SelectItem value="stream-one">Stream One</SelectItem>
                                    </SelectContent>
                                  </Select>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.xhttp_settings.no_grpc_header"
                              render={({ field }) => (
                                <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                  <div className="space-y-0.5">
                                    <FormLabel className="text-base">{t('hostsDialog.xhttp.noGrpcHeader')}</FormLabel>
                                  </div>
                                  <FormControl>
                                    <div onClick={e => e.stopPropagation()}>
                                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                                    </div>
                                  </FormControl>
                                </FormItem>
                              )}
                            />
                          </div>

                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <FormField
                              control={form.control}
                              name="transport_settings.xhttp_settings.x_padding_obfs_mode"
                              render={({ field }) => (
                                <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                  <div className="space-y-0.5">
                                    <FormLabel className="text-base">{t('hostsDialog.xhttp.xPaddingObfsMode')}</FormLabel>
                                  </div>
                                  <FormControl>
                                    <div onClick={e => e.stopPropagation()}>
                                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                                    </div>
                                  </FormControl>
                                </FormItem>
                              )}
                            />
                          </div>

                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <FormField
                              control={form.control}
                              name="transport_settings.xhttp_settings.x_padding_bytes"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.xhttp.xPaddingBytes')}</FormLabel>
                                  <FormControl>
                                    <Input {...field} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.xhttp_settings.sc_max_each_post_bytes"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.xhttp.scMaxEachPostBytes')}</FormLabel>
                                  <FormControl>
                                    <Input {...field} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.xhttp_settings.sc_min_posts_interval_ms"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.xhttp.scMinPostsIntervalMs')}</FormLabel>
                                  <FormControl>
                                    <Input {...field} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                          </div>

                          {xPaddingObfsEnabled ? (
                            <div className="space-y-4 rounded-lg border border-dashed p-4">
                              <div className="space-y-1">
                                <h4 className="text-sm font-medium">{t('hostsDialog.xhttp.xPaddingAdvanced')}</h4>
                                <p className="text-xs text-muted-foreground">{t('hostsDialog.xhttp.xPaddingAdvancedHint', { defaultValue: 'Shown only when X-Padding Obfs Mode is enabled.' })}</p>
                              </div>
                              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormField
                                  control={form.control}
                                  name="transport_settings.xhttp_settings.x_padding_key"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.xhttp.xPaddingKey')}</FormLabel>
                                      <FormControl>
                                        <Input {...field} />
                                      </FormControl>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />

                                <FormField
                                  control={form.control}
                                  name="transport_settings.xhttp_settings.x_padding_header"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.xhttp.xPaddingHeader')}</FormLabel>
                                      <FormControl>
                                        <Input {...field} />
                                      </FormControl>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />

                                <FormField
                                  control={form.control}
                                  name="transport_settings.xhttp_settings.x_padding_placement"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.xhttp.xPaddingPlacement')}</FormLabel>
                                      <Select onValueChange={value => field.onChange(value === '__default' ? undefined : value)} value={field.value ?? '__default'}>
                                        <FormControl>
                                          <SelectTrigger>
                                            <SelectValue />
                                          </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                          <SelectItem value="__default">{t('hostsDialog.xhttp.defaultMode', { defaultValue: 'Use default' })}</SelectItem>
                                          <SelectItem value="queryInHeader">Query In Header</SelectItem>
                                          <SelectItem value="query">Query</SelectItem>
                                          <SelectItem value="header">Header</SelectItem>
                                          <SelectItem value="cookie">Cookie</SelectItem>
                                        </SelectContent>
                                      </Select>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />

                                <FormField
                                  control={form.control}
                                  name="transport_settings.xhttp_settings.x_padding_method"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.xhttp.xPaddingMethod')}</FormLabel>
                                      <Select onValueChange={value => field.onChange(value === '__default' ? undefined : value)} value={field.value ?? '__default'}>
                                        <FormControl>
                                          <SelectTrigger>
                                            <SelectValue />
                                          </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                          <SelectItem value="__default">{t('hostsDialog.xhttp.defaultMode', { defaultValue: 'Use default' })}</SelectItem>
                                          <SelectItem value="repeat-x">Repeat-X</SelectItem>
                                          <SelectItem value="tokenish">Tokenish</SelectItem>
                                        </SelectContent>
                                      </Select>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />
                              </div>
                            </div>
                          ) : null}

                          <div className="space-y-4">
                            <h4 className="text-sm font-medium">{t('hostsDialog.xhttp.uplinkSettings')}</h4>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.uplink_http_method"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.uplinkHttpMethod')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.uplink_data_placement"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.uplinkDataPlacement')}</FormLabel>
                                    <Select onValueChange={value => field.onChange(value === '__default' ? undefined : value)} value={field.value ?? '__default'}>
                                      <FormControl>
                                        <SelectTrigger>
                                          <SelectValue />
                                        </SelectTrigger>
                                      </FormControl>
                                      <SelectContent>
                                        <SelectItem value="__default">{t('hostsDialog.xhttp.defaultMode', { defaultValue: 'Use default' })}</SelectItem>
                                        <SelectItem value="body">Body</SelectItem>
                                        <SelectItem value="header">Header</SelectItem>
                                        <SelectItem value="cookie">Cookie</SelectItem>
                                      </SelectContent>
                                    </Select>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.uplink_data_key"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.uplinkDataKey')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.uplink_chunk_size"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.uplinkChunkSize')}</FormLabel>
                                    <FormControl>
                                      <Input
                                        type="number"
                                        {...field}
                                        value={field.value ?? ''}
                                        onChange={e => {
                                          const value = e.target.value
                                          field.onChange(value === '' ? null : parseInt(value, 10))
                                        }}
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>
                          </div>

                          <div className="space-y-4">
                            <h4 className="text-sm font-medium">{t('hostsDialog.xhttp.sessionSettings')}</h4>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.session_placement"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.sessionPlacement')}</FormLabel>
                                    <Select onValueChange={value => field.onChange(value === '__default' ? undefined : value)} value={field.value ?? '__default'}>
                                      <FormControl>
                                        <SelectTrigger>
                                          <SelectValue />
                                        </SelectTrigger>
                                      </FormControl>
                                      <SelectContent>
                                        <SelectItem value="__default">{t('hostsDialog.xhttp.defaultMode', { defaultValue: 'Use default' })}</SelectItem>
                                        <SelectItem value="path">Path</SelectItem>
                                        <SelectItem value="query">Query</SelectItem>
                                        <SelectItem value="header">Header</SelectItem>
                                        <SelectItem value="cookie">Cookie</SelectItem>
                                      </SelectContent>
                                    </Select>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.session_key"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.sessionKey')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.seq_placement"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.seqPlacement')}</FormLabel>
                                    <Select onValueChange={value => field.onChange(value === '__default' ? undefined : value)} value={field.value ?? '__default'}>
                                      <FormControl>
                                        <SelectTrigger>
                                          <SelectValue />
                                        </SelectTrigger>
                                      </FormControl>
                                      <SelectContent>
                                        <SelectItem value="__default">{t('hostsDialog.xhttp.defaultMode', { defaultValue: 'Use default' })}</SelectItem>
                                        <SelectItem value="path">Path</SelectItem>
                                        <SelectItem value="query">Query</SelectItem>
                                        <SelectItem value="header">Header</SelectItem>
                                        <SelectItem value="cookie">Cookie</SelectItem>
                                      </SelectContent>
                                    </Select>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.seq_key"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.xhttp.seqKey')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>
                          </div>

                          <div className="space-y-4">
                            <h4 className="text-sm font-medium">{t('hostsDialog.xhttp.xmux')}</h4>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.xmux.max_concurrency"
                                render={({ field }) => (
                                  <FormItem className="col-span-2 md:col-span-1">
                                    <FormLabel>{t('hostsDialog.xhttp.maxConcurrency')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.xmux.max_connections"
                                render={({ field }) => (
                                  <FormItem className="col-span-2 md:col-span-1">
                                    <FormLabel>{t('hostsDialog.xhttp.maxConnections')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.xmux.c_max_reuse_times"
                                render={({ field }) => (
                                  <FormItem className="col-span-2 md:col-span-1">
                                    <FormLabel>{t('hostsDialog.xhttp.cMaxReuseTimes')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.xmux.h_max_reusable_secs"
                                render={({ field }) => (
                                  <FormItem className="col-span-2 md:col-span-1">
                                    <FormLabel>{t('hostsDialog.xhttp.hMaxReusableSecs')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.xmux.h_max_request_times"
                                render={({ field }) => (
                                  <FormItem className="col-span-2 md:col-span-1">
                                    <FormLabel>{t('hostsDialog.xhttp.hMaxRequestTimes')}</FormLabel>
                                    <FormControl>
                                      <Input {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />

                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.xmux.h_keep_alive_period"
                                render={({ field }) => (
                                  <FormItem className="col-span-2 md:col-span-1">
                                    <FormLabel>{t('hostsDialog.xhttp.hKeepAlivePeriod')}</FormLabel>
                                    <FormControl>
                                      <Input
                                        type="number"
                                        {...field}
                                        value={field.value ?? ''} // Ensure controlled component, handle null/undefined
                                        onChange={e => {
                                          const value = e.target.value
                                          field.onChange(value === '' ? null : parseInt(value, 10))
                                        }}
                                      />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name="transport_settings.xhttp_settings.download_settings"
                                render={({ field }) => (
                                  <FormItem className="col-span-2 w-full">
                                    <div className="flex items-center gap-2">
                                      <FormLabel>{t('hostsDialog.xhttp.downloadSettings')}</FormLabel>
                                      <Popover>
                                        <PopoverTrigger asChild>
                                          <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                            <Info className="h-4 w-4 text-muted-foreground" />
                                          </Button>
                                        </PopoverTrigger>
                                        <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                                          <p className="text-[11px] text-muted-foreground">{t('hostsDialog.xhttp.downloadSettingsInfo')}</p>
                                        </PopoverContent>
                                      </Popover>
                                    </div>
                                    <Select
                                      onValueChange={value => field.onChange(value ? parseInt(value) : 0)}
                                      value={field.value?.toString() ?? '0'}
                                      onOpenChange={open => {
                                        // Refresh hosts list when dropdown is opened
                                        if (open) {
                                          queryClient.invalidateQueries({
                                            queryKey: ['getHostsQueryKey'],
                                          })
                                        }
                                      }}
                                    >
                                      <FormControl>
                                        <SelectTrigger className="w-full">
                                          <SelectValue placeholder={t('hostsDialog.xhttp.selectDownloadSettings')} />
                                        </SelectTrigger>
                                      </FormControl>
                                      <SelectContent className="w-full">
                                        <SelectItem value="0">{t('none')}</SelectItem>
                                        {hosts.map(host => (
                                          <SelectItem key={host.id} value={host.id?.toString() ?? ''}>
                                            {host.remark}
                                          </SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>
                          </div>
                        </TabsContent>

                        {/* gRPC Settings */}
                        <TabsContent dir={dir} value="grpc" className="space-y-4 p-2">
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <FormField
                              control={form.control}
                              name="transport_settings.grpc_settings.multi_mode"
                              render={({ field }) => (
                                <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                  <div className="space-y-0.5">
                                    <FormLabel className="text-base">{t('hostsDialog.grpc.multiMode')}</FormLabel>
                                  </div>
                                  <FormControl>
                                    <div onClick={e => e.stopPropagation()}>
                                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                                    </div>
                                  </FormControl>
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.grpc_settings.idle_timeout"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.grpc.idleTimeout')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.grpc_settings.health_check_timeout"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.grpc.healthCheckTimeout')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.grpc_settings.permit_without_stream"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.grpc.permitWithoutStream')}</FormLabel>
                                  <FormControl>
                                    <Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.grpc_settings.initial_windows_size"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.grpc.initialWindowsSize')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                        </TabsContent>

                        {/* KCP Settings */}
                        <TabsContent dir={dir} value="kcp" className="space-y-4 p-2">
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.header"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.header')}</FormLabel>
                                  <Select onValueChange={field.onChange} value={field.value}>
                                    <FormControl>
                                      <SelectTrigger>
                                        <SelectValue />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      <SelectItem value="none">None</SelectItem>
                                      <SelectItem value="srtp">SRTP</SelectItem>
                                      <SelectItem value="utp">uTP</SelectItem>
                                      <SelectItem value="wechat-video">WeChat Video</SelectItem>
                                      <SelectItem value="dtls">DTLS</SelectItem>
                                      <SelectItem value="wireguard">WireGuard</SelectItem>
                                      <SelectItem value="dns">DNS</SelectItem>
                                    </SelectContent>
                                  </Select>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.mtu"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.mtu')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.tti"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.tti')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.uplink_capacity"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.uplinkCapacity')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.downlink_capacity"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.downlinkCapacity')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.congestion"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.congestion')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.read_buffer_size"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.readBufferSize')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />

                            <FormField
                              control={form.control}
                              name="transport_settings.kcp_settings.write_buffer_size"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.kcp.writeBufferSize')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                        </TabsContent>

                        {/* TCP Settings */}
                        <TabsContent dir={dir} value="tcp" className="space-y-4 p-2">
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <FormField
                              control={form.control}
                              name="transport_settings.tcp_settings.header"
                              render={({ field }) => (
                                <FormItem className="col-span-2">
                                  <FormLabel>{t('hostsDialog.tcp.header')}</FormLabel>
                                  <Select
                                    onValueChange={value => field.onChange(value === '__default' ? '' : value)}
                                    value={field.value === '' || field.value == null ? '__default' : field.value}
                                  >
                                    <FormControl>
                                      <SelectTrigger>
                                        <SelectValue />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      <SelectItem value="__default">{t('hostsDialog.tcp.defaultHeader', { defaultValue: 'Use default' })}</SelectItem>
                                      <SelectItem value="none">None</SelectItem>
                                      <SelectItem value="http">HTTP</SelectItem>
                                    </SelectContent>
                                  </Select>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>

                          {form.watch('transport_settings.tcp_settings.header') === 'http' && (
                            <>
                              <div className="space-y-4 p-2">
                                <h4 className="text-sm font-medium">{t('hostsDialog.tcp.request.title')}</h4>
                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                  <FormField
                                    control={form.control}
                                    name="transport_settings.tcp_settings.request.version"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.tcp.request.version')}</FormLabel>
                                        <Select onValueChange={field.onChange} value={field.value}>
                                          <FormControl>
                                            <SelectTrigger>
                                              <SelectValue />
                                            </SelectTrigger>
                                          </FormControl>
                                          <SelectContent>
                                            <SelectItem value="1.0">HTTP/1.0</SelectItem>
                                            <SelectItem value="1.1">HTTP/1.1</SelectItem>
                                            <SelectItem value="2.0">HTTP/2.0</SelectItem>
                                            <SelectItem value="3.0">HTTP/3.0</SelectItem>
                                          </SelectContent>
                                        </Select>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />

                                  <FormField
                                    control={form.control}
                                    name="transport_settings.tcp_settings.request.method"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.tcp.request.method')}</FormLabel>
                                        <Select onValueChange={field.onChange} value={field.value}>
                                          <FormControl>
                                            <SelectTrigger>
                                              <SelectValue />
                                            </SelectTrigger>
                                          </FormControl>
                                          <SelectContent>
                                            <SelectItem value="GET">GET</SelectItem>
                                            <SelectItem value="POST">POST</SelectItem>
                                            <SelectItem value="PUT">PUT</SelectItem>
                                            <SelectItem value="DELETE">DELETE</SelectItem>
                                            <SelectItem value="HEAD">HEAD</SelectItem>
                                            <SelectItem value="OPTIONS">OPTIONS</SelectItem>
                                            <SelectItem value="PATCH">PATCH</SelectItem>
                                            <SelectItem value="TRACE">TRACE</SelectItem>
                                            <SelectItem value="CONNECT">CONNECT</SelectItem>
                                          </SelectContent>
                                        </Select>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />
                                </div>

                                {/* Request Headers */}
                                <div className="space-y-2">
                                  <div className="flex items-center justify-between">
                                    <h4 className="text-sm font-medium">{t('hostsDialog.tcp.requestHeaders')}</h4>
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="icon"
                                      className="h-6 w-6"
                                      onClick={() => {
                                        const currentHeaders = form.getValues('transport_settings.tcp_settings.request.headers') || {}
                                        const newKey = `header_${Object.keys(currentHeaders).length}`
                                        form.setValue(
                                          'transport_settings.tcp_settings.request.headers',
                                          {
                                            ...currentHeaders,
                                            [newKey]: [''],
                                          },
                                          {
                                            shouldDirty: true,
                                            shouldTouch: true,
                                          },
                                        )
                                      }}
                                    >
                                      <Plus className="h-4 w-4" />
                                    </Button>
                                  </div>

                                  {/* Render request headers */}
                                  {Object.entries(form.watch('transport_settings.tcp_settings.request.headers') || {}).map(([key, values]) => (
                                    <div key={key} className="grid grid-cols-[minmax(120px,1fr),1fr,auto] gap-2">
                                      <Input
                                        placeholder={t('hostsDialog.tcp.headerName')}
                                        defaultValue={key}
                                        onBlur={e => {
                                          if (e.target.value !== key) {
                                            const currentHeaders = { ...form.getValues('transport_settings.tcp_settings.request.headers') }
                                            const oldValues = currentHeaders[key]
                                            delete currentHeaders[key]
                                            currentHeaders[e.target.value] = oldValues
                                            form.setValue('transport_settings.tcp_settings.request.headers', currentHeaders, {
                                              shouldDirty: true,
                                              shouldTouch: true,
                                            })
                                          }
                                        }}
                                      />
                                      <Input
                                        placeholder={t('hostsDialog.tcp.headerValue')}
                                        value={Array.isArray(values) ? values.join(', ') : ''}
                                        onChange={e => {
                                          const tcpHeaderValues = e.target.value.split(',').map(v => v.trim())
                                          const tcpHeaders = { ...form.getValues('transport_settings.tcp_settings.request.headers') }
                                          tcpHeaders[key] = tcpHeaderValues
                                          form.setValue('transport_settings.tcp_settings.request.headers', tcpHeaders, {
                                            shouldDirty: true,
                                            shouldTouch: true,
                                          })
                                        }}
                                      />
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 shrink-0 border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                                        onClick={() => {
                                          const currentHeaders = { ...form.getValues('transport_settings.tcp_settings.request.headers') }
                                          delete currentHeaders[key]
                                          form.setValue('transport_settings.tcp_settings.request.headers', currentHeaders, {
                                            shouldDirty: true,
                                            shouldTouch: true,
                                          })
                                        }}
                                      >
                                        <Trash2 className="h-4 w-4 text-red-500" />
                                      </Button>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              <div className="space-y-4 p-2">
                                <h4 className="text-sm font-medium">{t('hostsDialog.tcp.response.title')}</h4>
                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                  <FormField
                                    control={form.control}
                                    name="transport_settings.tcp_settings.response.version"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.tcp.response.version')}</FormLabel>
                                        <Select onValueChange={field.onChange} value={field.value}>
                                          <FormControl>
                                            <SelectTrigger>
                                              <SelectValue />
                                            </SelectTrigger>
                                          </FormControl>
                                          <SelectContent>
                                            <SelectItem value="1.0">HTTP/1.0</SelectItem>
                                            <SelectItem value="1.1">HTTP/1.1</SelectItem>
                                            <SelectItem value="2.0">HTTP/2.0</SelectItem>
                                            <SelectItem value="3.0">HTTP/3.0</SelectItem>
                                          </SelectContent>
                                        </Select>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />

                                  <FormField
                                    control={form.control}
                                    name="transport_settings.tcp_settings.response.status"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.tcp.response.status')}</FormLabel>
                                        <FormControl>
                                          <Input {...field} placeholder="200" pattern="[1-5]\d{2}" />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />

                                  <FormField
                                    control={form.control}
                                    name="transport_settings.tcp_settings.response.reason"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.tcp.response.reason')}</FormLabel>
                                        <Select onValueChange={field.onChange} value={field.value || ''}>
                                          <FormControl>
                                            <SelectTrigger>
                                              <SelectValue placeholder={t('hostsDialog.selectReason')} />
                                            </SelectTrigger>
                                          </FormControl>
                                          <SelectContent>
                                            {/* 1xx Information responses */}
                                            <SelectGroup>
                                              <SelectLabel>1xx Information</SelectLabel>
                                              <SelectItem value="Continue">{t('hostsDialog.httpReasons.100')}</SelectItem>
                                              <SelectItem value="Switching Protocols">{t('hostsDialog.httpReasons.101')}</SelectItem>
                                            </SelectGroup>

                                            {/* 2xx Success responses */}
                                            <SelectGroup>
                                              <SelectLabel>2xx Success</SelectLabel>
                                              <SelectItem value="OK">{t('hostsDialog.httpReasons.200')}</SelectItem>
                                              <SelectItem value="Created">{t('hostsDialog.httpReasons.201')}</SelectItem>
                                              <SelectItem value="Accepted">{t('hostsDialog.httpReasons.202')}</SelectItem>
                                              <SelectItem value="Non-Authoritative Information">{t('hostsDialog.httpReasons.203')}</SelectItem>
                                              <SelectItem value="No Content">{t('hostsDialog.httpReasons.204')}</SelectItem>
                                              <SelectItem value="Reset Content">{t('hostsDialog.httpReasons.205')}</SelectItem>
                                              <SelectItem value="Partial Content">{t('hostsDialog.httpReasons.206')}</SelectItem>
                                            </SelectGroup>

                                            {/* 3xx Redirection responses */}
                                            <SelectGroup>
                                              <SelectLabel>3xx Redirection</SelectLabel>
                                              <SelectItem value="Multiple Choices">{t('hostsDialog.httpReasons.300')}</SelectItem>
                                              <SelectItem value="Moved Permanently">{t('hostsDialog.httpReasons.301')}</SelectItem>
                                              <SelectItem value="Found">{t('hostsDialog.httpReasons.302')}</SelectItem>
                                              <SelectItem value="See Other">{t('hostsDialog.httpReasons.303')}</SelectItem>
                                              <SelectItem value="Not Modified">{t('hostsDialog.httpReasons.304')}</SelectItem>
                                              <SelectItem value="Use Proxy">{t('hostsDialog.httpReasons.305')}</SelectItem>
                                              <SelectItem value="Temporary Redirect">{t('hostsDialog.httpReasons.307')}</SelectItem>
                                              <SelectItem value="Permanent Redirect">{t('hostsDialog.httpReasons.308')}</SelectItem>
                                            </SelectGroup>

                                            {/* 4xx Client Error responses */}
                                            <SelectGroup>
                                              <SelectLabel>4xx Client Error</SelectLabel>
                                              <SelectItem value="Bad Request">{t('hostsDialog.httpReasons.400')}</SelectItem>
                                              <SelectItem value="Unauthorized">{t('hostsDialog.httpReasons.401')}</SelectItem>
                                              <SelectItem value="Payment Required">{t('hostsDialog.httpReasons.402')}</SelectItem>
                                              <SelectItem value="Forbidden">{t('hostsDialog.httpReasons.403')}</SelectItem>
                                              <SelectItem value="Not Found">{t('hostsDialog.httpReasons.404')}</SelectItem>
                                              <SelectItem value="Method Not Allowed">{t('hostsDialog.httpReasons.405')}</SelectItem>
                                              <SelectItem value="Not Acceptable">{t('hostsDialog.httpReasons.406')}</SelectItem>
                                              <SelectItem value="Proxy Authentication Required">{t('hostsDialog.httpReasons.407')}</SelectItem>
                                              <SelectItem value="Request Timeout">{t('hostsDialog.httpReasons.408')}</SelectItem>
                                              <SelectItem value="Conflict">{t('hostsDialog.httpReasons.409')}</SelectItem>
                                              <SelectItem value="Gone">{t('hostsDialog.httpReasons.410')}</SelectItem>
                                              <SelectItem value="Length Required">{t('hostsDialog.httpReasons.411')}</SelectItem>
                                              <SelectItem value="Precondition Failed">{t('hostsDialog.httpReasons.412')}</SelectItem>
                                              <SelectItem value="Payload Too Large">{t('hostsDialog.httpReasons.413')}</SelectItem>
                                              <SelectItem value="URI Too Long">{t('hostsDialog.httpReasons.414')}</SelectItem>
                                              <SelectItem value="Unsupported Media Type">{t('hostsDialog.httpReasons.415')}</SelectItem>
                                              <SelectItem value="Range Not Satisfiable">{t('hostsDialog.httpReasons.416')}</SelectItem>
                                              <SelectItem value="Expectation Failed">{t('hostsDialog.httpReasons.417')}</SelectItem>
                                              <SelectItem value="I'm a teapot">{t('hostsDialog.httpReasons.418')}</SelectItem>
                                              <SelectItem value="Misdirected Request">{t('hostsDialog.httpReasons.421')}</SelectItem>
                                              <SelectItem value="Unprocessable Entity">{t('hostsDialog.httpReasons.422')}</SelectItem>
                                              <SelectItem value="Locked">{t('hostsDialog.httpReasons.423')}</SelectItem>
                                              <SelectItem value="Failed Dependency">{t('hostsDialog.httpReasons.424')}</SelectItem>
                                              <SelectItem value="Too Early">{t('hostsDialog.httpReasons.425')}</SelectItem>
                                              <SelectItem value="Upgrade Required">{t('hostsDialog.httpReasons.426')}</SelectItem>
                                              <SelectItem value="Precondition Required">{t('hostsDialog.httpReasons.428')}</SelectItem>
                                              <SelectItem value="Too Many Requests">{t('hostsDialog.httpReasons.429')}</SelectItem>
                                              <SelectItem value="Request Header Fields Too Large">{t('hostsDialog.httpReasons.431')}</SelectItem>
                                              <SelectItem value="Unavailable For Legal Reasons">{t('hostsDialog.httpReasons.451')}</SelectItem>
                                            </SelectGroup>

                                            {/* 5xx Server Error responses */}
                                            <SelectGroup>
                                              <SelectLabel>5xx Server Error</SelectLabel>
                                              <SelectItem value="Internal Server Error">{t('hostsDialog.httpReasons.500')}</SelectItem>
                                              <SelectItem value="Not Implemented">{t('hostsDialog.httpReasons.501')}</SelectItem>
                                              <SelectItem value="Bad Gateway">{t('hostsDialog.httpReasons.502')}</SelectItem>
                                              <SelectItem value="Service Unavailable">{t('hostsDialog.httpReasons.503')}</SelectItem>
                                              <SelectItem value="Gateway Timeout">{t('hostsDialog.httpReasons.504')}</SelectItem>
                                              <SelectItem value="HTTP Version Not Supported">{t('hostsDialog.httpReasons.505')}</SelectItem>
                                            </SelectGroup>
                                          </SelectContent>
                                        </Select>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />
                                </div>

                                {/* Response Headers */}
                                <div className="space-y-2">
                                  <div className="flex items-center justify-between">
                                    <h4 className="text-sm font-medium">{t('hostsDialog.tcp.responseHeaders')}</h4>
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="icon"
                                      className="h-6 w-6"
                                      onClick={() => {
                                        const currentHeaders = form.getValues('transport_settings.tcp_settings.response.headers') || {}
                                        const newKey = `header_${Object.keys(currentHeaders).length}`
                                        form.setValue(
                                          'transport_settings.tcp_settings.response.headers',
                                          {
                                            ...currentHeaders,
                                            [newKey]: [''],
                                          },
                                          {
                                            shouldDirty: true,
                                            shouldTouch: true,
                                          },
                                        )
                                      }}
                                    >
                                      <Plus className="h-4 w-4" />
                                    </Button>
                                  </div>

                                  {/* Render response headers */}
                                  {Object.entries(form.watch('transport_settings.tcp_settings.response.headers') || {}).map(([key, values]) => (
                                    <div key={key} className="grid grid-cols-[minmax(120px,1fr),1fr,auto] gap-2">
                                      <Input
                                        placeholder={t('hostsDialog.tcp.headerName')}
                                        defaultValue={key}
                                        onBlur={e => {
                                          if (e.target.value !== key) {
                                            const currentHeaders = { ...form.getValues('transport_settings.tcp_settings.response.headers') }
                                            const oldValues = currentHeaders[key]
                                            delete currentHeaders[key]
                                            currentHeaders[e.target.value] = oldValues
                                            form.setValue('transport_settings.tcp_settings.response.headers', currentHeaders, {
                                              shouldDirty: true,
                                              shouldTouch: true,
                                            })
                                          }
                                        }}
                                      />
                                      <Input
                                        placeholder={t('hostsDialog.tcp.headerValue')}
                                        value={values.join(', ')}
                                        onChange={e => {
                                          const currentHeaders = { ...form.getValues('transport_settings.tcp_settings.response.headers') }
                                          currentHeaders[key] = e.target.value.split(',').map(v => v.trim())
                                          form.setValue('transport_settings.tcp_settings.response.headers', currentHeaders, {
                                            shouldDirty: true,
                                            shouldTouch: true,
                                          })
                                        }}
                                      />
                                      <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 shrink-0 border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                                        onClick={() => {
                                          const currentHeaders = { ...form.getValues('transport_settings.tcp_settings.response.headers') }
                                          delete currentHeaders[key]
                                          form.setValue('transport_settings.tcp_settings.response.headers', currentHeaders, {
                                            shouldDirty: true,
                                            shouldTouch: true,
                                          })
                                        }}
                                      >
                                        <Trash2 className="h-4 w-4 text-red-500" />
                                      </Button>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </>
                          )}
                        </TabsContent>

                        {/* WebSocket Settings */}
                        <TabsContent dir={dir} value="websocket" className="space-y-4">
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <FormField
                              control={form.control}
                              name="transport_settings.websocket_settings.heartbeatPeriod"
                              render={({ field }) => (
                                <FormItem>
                                  <FormLabel>{t('hostsDialog.websocket.heartbeatPeriod')}</FormLabel>
                                  <FormControl>
                                    <Input type="number" {...field} onChange={e => field.onChange(e.target.value ? Number(e.target.value) : 0)} value={field.value} />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                        </TabsContent>
                      </Tabs>
                    </div>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="camouflag">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <ChevronsLeftRightEllipsis className="h-4 w-4" />
                      <span>{t('hostsDialog.camouflagSettings')}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-2">
                    <Tabs defaultValue="xray" className="w-full">
                      <TabsList className="mb-4 grid w-full grid-cols-2">
                        <TabsTrigger value="xray">Xray</TabsTrigger>
                        <TabsTrigger value="singbox">SingBox</TabsTrigger>
                      </TabsList>
                      <TabsContent value="xray">
                        <div className="space-y-6">
                          {/* Fragment Settings */}
                          <div className="space-y-4">
                            <div className="flex items-center justify-between">
                              <h4 className="flex items-center gap-2 text-sm font-medium">
                                {t('hostsDialog.fragment.title')}
                                <Popover>
                                  <PopoverTrigger asChild>
                                    <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                      <Info className="h-4 w-4 text-muted-foreground" />
                                    </Button>
                                  </PopoverTrigger>
                                  <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                                    <div className="space-y-1.5">
                                      <p className="text-[11px] text-muted-foreground">{t('hostsDialog.fragment.info')}</p>
                                      <p className="text-[11px] text-muted-foreground">{t('hostsDialog.fragment.info.attention')}</p>
                                      <p className="text-[11px] text-muted-foreground">{t('hostsDialog.fragment.info.examples')}</p>
                                      <p className="overflow-hidden text-[11px] text-muted-foreground">100-200,10-20,tlshello 100-200,10-20,1-3</p>
                                    </div>
                                  </PopoverContent>
                                </Popover>
                              </h4>
                            </div>
                            <div className="grid grid-cols-3 gap-4">
                              <FormField
                                control={form.control}
                                name="fragment_settings.xray.packets"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.fragment.packets')}</FormLabel>
                                    <FormControl>
                                      <Input placeholder={t('hostsDialog.fragment.packetsPlaceholder')} {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name="fragment_settings.xray.length"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.fragment.length')}</FormLabel>
                                    <FormControl>
                                      <Input placeholder={t('hostsDialog.fragment.lengthPlaceholder')} {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name="fragment_settings.xray.interval"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('hostsDialog.fragment.interval')}</FormLabel>
                                    <FormControl>
                                      <Input placeholder={t('hostsDialog.fragment.intervalPlaceholder')} {...field} value={field.value || ''} />
                                    </FormControl>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>
                          </div>

                          {/* Noise Settings */}
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <h4 className="text-sm font-medium">{t('hostsDialog.noise.title')}</h4>
                                <Popover>
                                  <PopoverTrigger asChild>
                                    <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                                      <Info className="h-4 w-4 text-muted-foreground" />
                                    </Button>
                                  </PopoverTrigger>
                                  <PopoverContent className="w-[320px] p-3" side="right" align="start" sideOffset={5}>
                                    <div className="space-y-1.5">
                                      <p className="text-[11px] text-muted-foreground">{t('hostsDialog.noise.info')}</p>
                                      <p className="text-[11px] text-muted-foreground">{t('hostsDialog.noise.info.attention')}</p>
                                      <p className="text-[11px] text-muted-foreground">{t('hostsDialog.noise.info.examples')}</p>
                                      <p className="overflow-hidden text-[11px] text-muted-foreground">
                                        rand:10-20,10-20 rand:10-20,10-20 &base64:7nQBAAABAAAAAAAABnQtcmluZwZtc2VkZ2UDbmV0AAABAAE=,10-25
                                      </p>
                                    </div>
                                  </PopoverContent>
                                </Popover>
                              </div>
                              <Button type="button" variant="outline" size="icon" className="h-6 w-6" onClick={addNoiseSetting} title={t('hostsDialog.noise.addNoise')}>
                                <Plus className="h-4 w-4" />
                              </Button>
                            </div>
                            <div className="space-y-2">
                              {noiseSettings.map((_, index) => (
                                <NoiseItem key={index} index={index} form={form} onRemove={removeNoiseSetting} onDuplicate={duplicateNoiseSetting} t={t} />
                              ))}
                              {noiseSettings.length === 0 && <div className="py-8 text-center text-sm text-muted-foreground">{t('hostsDialog.noise.noNoiseSettings')}</div>}
                            </div>
                          </div>
                        </div>
                      </TabsContent>
                      <TabsContent value="singbox">
                        <div className="space-y-6">
                          <div className="space-y-4">
                            <div className="flex items-center justify-between">
                              <h4 className="flex items-center gap-2 text-sm font-medium">{t('hostsDialog.fragment.title')}</h4>
                            </div>
                            <div className="grid grid-cols-1 gap-4">
                              <FormField
                                control={form.control}
                                name="fragment_settings.sing_box.fragment"
                                render={({ field }) => (
                                  <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                    <div className="space-y-0.5">
                                      <FormLabel className="text-base">{t('hostsDialog.fragment.fragment')}</FormLabel>
                                    </div>
                                    <FormControl>
                                      <div onClick={e => e.stopPropagation()}>
                                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                                      </div>
                                    </FormControl>
                                  </FormItem>
                                )}
                              />
                              {form.watch('fragment_settings.sing_box.fragment') && (
                                <>
                                  <FormField
                                    control={form.control}
                                    name="fragment_settings.sing_box.fragment_fallback_delay"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.fragment.fallbackDelay')}</FormLabel>
                                        <FormControl>
                                          <Input
                                            placeholder="e.g. 100"
                                            {...field}
                                            value={field.value ? field.value.replace('ms', '') : ''}
                                            onChange={e => {
                                              const value = e.target.value
                                              field.onChange(value)
                                            }}
                                            title="Enter a number (e.g., 100)"
                                          />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />
                                  <FormField
                                    control={form.control}
                                    name="fragment_settings.sing_box.record_fragment"
                                    render={({ field }) => (
                                      <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                        <div className="space-y-0.5">
                                          <FormLabel className="text-base">{t('hostsDialog.fragment.recordFragment')}</FormLabel>
                                        </div>
                                        <FormControl>
                                          <div onClick={e => e.stopPropagation()}>
                                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                                          </div>
                                        </FormControl>
                                      </FormItem>
                                    )}
                                  />
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </TabsContent>
                    </Tabs>
                  </AccordionContent>
                </AccordionItem>
                <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="mux">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Cable className="h-4 w-4" />
                      <span>{t('hostsDialog.muxSettings')}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-2">
                    <div className="space-y-4">
                      <Tabs defaultValue="xray" className="w-full">
                        <TabsList className="mb-4 grid grid-cols-3">
                          <TabsTrigger value="xray">Xray</TabsTrigger>
                          <TabsTrigger value="sing_box">Sing-box</TabsTrigger>
                          <TabsTrigger value="clash">Clash</TabsTrigger>
                        </TabsList>

                        {/* Xray Settings */}
                        <TabsContent dir={dir} value="xray">
                          <div className="space-y-4">
                            <FormField
                              control={form.control}
                              name="mux_settings.xray.enabled"
                              render={({ field }) => (
                                <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                  <div className="space-y-0.5">
                                    <FormLabel className="text-base">{t('hostsDialog.enableMux')}</FormLabel>
                                  </div>
                                  <FormControl>
                                    <div onClick={e => e.stopPropagation()}>
                                      <Switch
                                        checked={field.value || false}
                                        onCheckedChange={checked => {
                                          field.onChange(checked)
                                          if (checked) {
                                            // Disable other mux settings when enabling this one
                                            form.setValue('mux_settings.sing_box.enable', false)
                                            form.setValue('mux_settings.clash.enable', false)
                                          }
                                        }}
                                      />
                                    </div>
                                  </FormControl>
                                </FormItem>
                              )}
                            />
                            {form.watch('mux_settings.xray.enabled') === true ? (
                              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormField
                                  control={form.control}
                                  name="mux_settings.xray.concurrency"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.concurrency')}</FormLabel>
                                      <FormControl>
                                        <Input type="number" {...field} value={field.value ?? ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : null)} />
                                      </FormControl>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />

                                <FormField
                                  control={form.control}
                                  name="mux_settings.xray.xudp_concurrency"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.xudpConcurrency')}</FormLabel>
                                      <FormControl>
                                        <Input type="number" {...field} value={field.value ?? ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : null)} />
                                      </FormControl>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />

                                <FormField
                                  control={form.control}
                                  name="mux_settings.xray.xudp_proxy_443"
                                  render={() => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.xudpProxy443')}</FormLabel>
                                      <Select
                                        value={form.watch('mux_settings.xray.xudp_proxy_443') ?? 'reject'}
                                        onValueChange={value => {
                                          form.setValue('mux_settings.xray.xudp_proxy_443', value)
                                        }}
                                      >
                                        <SelectTrigger>
                                          <SelectValue placeholder={t('host.xudp_proxy_443')} />
                                        </SelectTrigger>
                                        <SelectContent>
                                          <SelectItem value="reject">{t('host.reject')}</SelectItem>
                                          <SelectItem value="allow">{t('host.allow')}</SelectItem>
                                          <SelectItem value="skip">{t('host.skip')}</SelectItem>
                                        </SelectContent>
                                      </Select>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />
                              </div>
                            ) : null}
                          </div>
                        </TabsContent>

                        {/* Sing-box Settings */}
                        <TabsContent dir={dir} value="sing_box">
                          <div className="space-y-4">
                            <FormField
                              control={form.control}
                              name="mux_settings.sing_box.enable"
                              render={({ field }) => (
                                <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                  <div className="space-y-0.5">
                                    <FormLabel className="text-base">{t('hostsDialog.enableMux')}</FormLabel>
                                  </div>
                                  <FormControl>
                                    <div onClick={e => e.stopPropagation()}>
                                      <Switch
                                        checked={field.value || false}
                                        onCheckedChange={checked => {
                                          field.onChange(checked)
                                          if (checked) {
                                            // Disable other mux settings when enabling this one
                                            form.setValue('mux_settings.xray.enabled', false)
                                            form.setValue('mux_settings.clash.enable', false)
                                          }
                                        }}
                                      />
                                    </div>
                                  </FormControl>
                                </FormItem>
                              )}
                            />
                            {form.watch('mux_settings.sing_box.enable') === true ? (
                              <>
                                <FormField
                                  control={form.control}
                                  name="mux_settings.sing_box.protocol"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.protocol')}</FormLabel>
                                      <Select onValueChange={value => field.onChange(value === 'null' ? undefined : value)} value={field.value ?? 'smux'}>
                                        <FormControl>
                                          <SelectTrigger>
                                            <SelectValue placeholder={t('hostsDialog.selectProtocol')} />
                                          </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                          <SelectItem value="smux">smux</SelectItem>
                                          <SelectItem value="yamux">yamux</SelectItem>
                                          <SelectItem value="h2mux">h2mux</SelectItem>
                                        </SelectContent>
                                      </Select>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />

                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                  <FormField
                                    control={form.control}
                                    name="mux_settings.sing_box.max_connections"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.maxConnections')}</FormLabel>
                                        <FormControl>
                                          <Input type="number" {...field} value={field.value || ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : 0)} />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />

                                  <FormField
                                    control={form.control}
                                    name="mux_settings.sing_box.min_streams"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.minStreams')}</FormLabel>
                                        <FormControl>
                                          <Input type="number" {...field} value={field.value || ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : 0)} />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />

                                  <FormField
                                    control={form.control}
                                    name="mux_settings.sing_box.max_streams"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.maxStreams')}</FormLabel>
                                        <FormControl>
                                          <Input type="number" {...field} value={field.value || ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : 0)} />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />
                                </div>

                                <div className="space-y-4">
                                  <h4 className="text-sm font-medium">{t('hostsDialog.brutal.title')}</h4>
                                  <FormField
                                    control={form.control}
                                    name="mux_settings.sing_box.brutal.enable"
                                    render={({ field }) => (
                                      <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                        <div className="space-y-0.5">
                                          <FormLabel className="text-base">{t('hostsDialog.brutal.enable')}</FormLabel>
                                        </div>
                                        <FormControl>
                                          <div onClick={e => e.stopPropagation()}>
                                            <Switch checked={field.value || false} onCheckedChange={field.onChange} />
                                          </div>
                                        </FormControl>
                                      </FormItem>
                                    )}
                                  />
                                  {form.watch('mux_settings.sing_box.brutal.enable') === true ? (
                                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                      <FormField
                                        control={form.control}
                                        name="mux_settings.sing_box.brutal.up_mbps"
                                        render={({ field }) => (
                                          <FormItem>
                                            <FormLabel>{t('hostsDialog.brutal.upMbps')}</FormLabel>
                                            <FormControl>
                                              <Input type="number" {...field} value={field.value || ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : 0)} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />

                                      <FormField
                                        control={form.control}
                                        name="mux_settings.sing_box.brutal.down_mbps"
                                        render={({ field }) => (
                                          <FormItem>
                                            <FormLabel>{t('hostsDialog.brutal.downMbps')}</FormLabel>
                                            <FormControl>
                                              <Input type="number" {...field} value={field.value || ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : 0)} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />
                                    </div>
                                  ) : null}
                                </div>

                                <FormField
                                  control={form.control}
                                  name="mux_settings.sing_box.padding"
                                  render={({ field }) => (
                                    <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                      <div className="space-y-0.5">
                                        <FormLabel className="text-base">{t('hostsDialog.padding')}</FormLabel>
                                      </div>
                                      <FormControl>
                                        <div onClick={e => e.stopPropagation()}>
                                          <Switch checked={field.value || false} onCheckedChange={field.onChange} />
                                        </div>
                                      </FormControl>
                                    </FormItem>
                                  )}
                                />
                              </>
                            ) : null}
                          </div>
                        </TabsContent>

                        {/* Clash Settings */}
                        <TabsContent dir={dir} value="clash">
                          <div className="space-y-4">
                            <FormField
                              control={form.control}
                              name="mux_settings.clash.enable"
                              render={({ field }) => (
                                <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                  <div className="space-y-0.5">
                                    <FormLabel className="text-base">{t('hostsDialog.enableMux')}</FormLabel>
                                  </div>
                                  <FormControl>
                                    <div onClick={e => e.stopPropagation()}>
                                      <Switch
                                        checked={field.value || false}
                                        onCheckedChange={checked => {
                                          field.onChange(checked)
                                          if (checked) {
                                            // Disable other mux settings when enabling this one
                                            form.setValue('mux_settings.xray.enabled', false)
                                            form.setValue('mux_settings.sing_box.enable', false)
                                          }
                                        }}
                                      />
                                    </div>
                                  </FormControl>
                                </FormItem>
                              )}
                            />
                            {form.watch('mux_settings.clash.enable') === true ? (
                              <>
                                <FormField
                                  control={form.control}
                                  name="mux_settings.clash.protocol"
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormLabel>{t('hostsDialog.protocol')}</FormLabel>
                                      <Select onValueChange={value => field.onChange(value === 'null' ? undefined : value)} value={field.value ?? 'smux'}>
                                        <FormControl>
                                          <SelectTrigger>
                                            <SelectValue placeholder={t('hostsDialog.selectProtocol')} />
                                          </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                          <SelectItem value="smux">smux</SelectItem>
                                          <SelectItem value="yamux">yamux</SelectItem>
                                          <SelectItem value="h2mux">h2mux</SelectItem>
                                        </SelectContent>
                                      </Select>
                                      <FormMessage />
                                    </FormItem>
                                  )}
                                />

                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                  <FormField
                                    control={form.control}
                                    name="mux_settings.clash.max_connections"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.maxConnections')}</FormLabel>
                                        <FormControl>
                                          <Input type="number" {...field} value={field.value ?? ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : null)} />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />

                                  <FormField
                                    control={form.control}
                                    name="mux_settings.clash.min_streams"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.minStreams')}</FormLabel>
                                        <FormControl>
                                          <Input type="number" {...field} value={field.value ?? ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : null)} />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />

                                  <FormField
                                    control={form.control}
                                    name="mux_settings.clash.max_streams"
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormLabel>{t('hostsDialog.maxStreams')}</FormLabel>
                                        <FormControl>
                                          <Input type="number" {...field} value={field.value ?? ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : null)} />
                                        </FormControl>
                                        <FormMessage />
                                      </FormItem>
                                    )}
                                  />
                                </div>

                                <div className="space-y-4">
                                  <h4 className="text-sm font-medium">{t('hostsDialog.brutal.title')}</h4>
                                  <FormField
                                    control={form.control}
                                    name="mux_settings.clash.brutal.enable"
                                    render={({ field }) => (
                                      <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                        <div className="space-y-0.5">
                                          <FormLabel className="text-base">{t('hostsDialog.brutal.enable')}</FormLabel>
                                        </div>
                                        <FormControl>
                                          <div onClick={e => e.stopPropagation()}>
                                            <Switch checked={field.value || false} onCheckedChange={field.onChange} />
                                          </div>
                                        </FormControl>
                                      </FormItem>
                                    )}
                                  />
                                  {form.watch('mux_settings.clash.brutal.enable') === true ? (
                                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                      <FormField
                                        control={form.control}
                                        name="mux_settings.clash.brutal.up_mbps"
                                        render={({ field }) => (
                                          <FormItem>
                                            <FormLabel>{t('hostsDialog.brutal.upMbps')}</FormLabel>
                                            <FormControl>
                                              <Input type="number" {...field} value={field.value ?? ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : null)} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />

                                      <FormField
                                        control={form.control}
                                        name="mux_settings.clash.brutal.down_mbps"
                                        render={({ field }) => (
                                          <FormItem>
                                            <FormLabel>{t('hostsDialog.brutal.downMbps')}</FormLabel>
                                            <FormControl>
                                              <Input type="number" {...field} value={field.value ?? ''} onChange={e => field.onChange(e.target.value ? parseInt(e.target.value) : null)} />
                                            </FormControl>
                                            <FormMessage />
                                          </FormItem>
                                        )}
                                      />
                                    </div>
                                  ) : null}
                                </div>

                                <FormField
                                  control={form.control}
                                  name="mux_settings.clash.padding"
                                  render={({ field }) => (
                                    <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                      <div className="space-y-0.5">
                                        <FormLabel className="text-base">{t('hostsDialog.padding')}</FormLabel>
                                      </div>
                                      <FormControl>
                                        <div onClick={e => e.stopPropagation()}>
                                          <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                                        </div>
                                      </FormControl>
                                    </FormItem>
                                  )}
                                />

                                <FormField
                                  control={form.control}
                                  name="mux_settings.clash.statistic"
                                  render={({ field }) => (
                                    <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                      <div className="space-y-0.5">
                                        <FormLabel className="text-base">{t('hostsDialog.statistic')}</FormLabel>
                                      </div>
                                      <FormControl>
                                        <div onClick={e => e.stopPropagation()}>
                                          <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                                        </div>
                                      </FormControl>
                                    </FormItem>
                                  )}
                                />

                                <FormField
                                  control={form.control}
                                  name="mux_settings.clash.only_tcp"
                                  render={({ field }) => (
                                    <FormItem className="flex cursor-pointer flex-row items-center justify-between rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                                      <div className="space-y-0.5">
                                        <FormLabel className="text-base">{t('hostsDialog.onlyTcp')}</FormLabel>
                                      </div>
                                      <FormControl>
                                        <div onClick={e => e.stopPropagation()}>
                                          <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                                        </div>
                                      </FormControl>
                                    </FormItem>
                                  )}
                                />
                              </>
                            ) : null}
                          </div>
                        </TabsContent>
                      </Tabs>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => handleModalOpenChange(false)}>
                {t('cancel')}
              </Button>
              <LoaderButton type="submit" disabled={form.formState.isSubmitting} isLoading={form.formState.isSubmitting} loadingText={editingHost ? t('modifying') : t('creating')}>
                {editingHost ? t('modify') : t('create')}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default HostModal
