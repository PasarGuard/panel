'use client'

import { useState, useRef, useEffect } from 'react'
import {
  useGetAllGroups,
  useGetUsers,
  useGetAdmins,
  useBulkModifyUsersProxySettings,
  useBulkModifyUsersDatalimit,
  useBulkModifyUsersExpire,
  useBulkAddGroupsToUsers,
  useBulkRemoveUsersFromGroups,
  XTLSFlows,
  ShadowsocksMethods,
} from '@/service/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from '@/components/ui/command'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Settings, Users2, User, Shield, CheckCircle, AlertTriangle, Plus, Minus, X, HardDrive, Calendar, Network, CheckCircle2, ChevronLeft, ChevronRight } from 'lucide-react'
import { SelectorPanel } from '@/components/bulk/selector-panel'
import { formatBytes, gbToBytes } from '@/utils/formatByte'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'

const PAGE_SIZE = 50

type BulkOperationType = 'proxy' | 'data' | 'expire' | 'groups'
type ExpiryUnit = 'seconds' | 'minutes' | 'hours' | 'days' | 'months'

interface BulkFlowProps {
  operationType: BulkOperationType
}

export default function BulkFlow({ operationType }: BulkFlowProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'

  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1)

  const [selectedFlow, setSelectedFlow] = useState<XTLSFlows | 'none' | undefined>(undefined)
  const [selectedMethod, setSelectedMethod] = useState<ShadowsocksMethods | undefined>(undefined)

  const [dataLimit, setDataLimit] = useState<number | undefined>(undefined)
  const [dataOperation, setDataOperation] = useState<'add' | 'subtract'>('add')
  const dataLimitInputRef = useRef<string>('')

  const [expireSeconds, setExpireSeconds] = useState<number | undefined>(undefined)
  const [expireUnit, setExpireUnit] = useState<ExpiryUnit>('days')
  const [expireAmount, setExpireAmount] = useState<number | undefined>(undefined)
  const [expireOperation, setExpireOperation] = useState<'add' | 'subtract'>('add')

  const [groupsOperation, setGroupsOperation] = useState<'add' | 'remove'>('add')

  const [selectedGroups, setSelectedGroups] = useState<number[]>([])
  const [selectedUsers, setSelectedUsers] = useState<number[]>([])
  const [selectedAdmins, setSelectedAdmins] = useState<number[]>([])
  const [selectedHasGroups, setSelectedHasGroups] = useState<number[]>([])

  const [groupCommandSearch, setGroupCommandSearch] = useState('')

  const { search: userSearch, debouncedSearch: debouncedUserSearch, setSearch: setUserSearch } = useDebouncedSearch('', 300)
  const { search: adminSearch, debouncedSearch: debouncedAdminSearch, setSearch: setAdminSearch } = useDebouncedSearch('', 300)
  const { search: hasGroupSearch, debouncedSearch: debouncedHasGroupSearch, setSearch: setHasGroupSearch } = useDebouncedSearch('', 300)
  const { search: groupSearch, debouncedSearch: debouncedGroupSearch, setSearch: setGroupSearch } = useDebouncedSearch('', 300)

  useEffect(() => {
    if (expireAmount === undefined) {
      setExpireSeconds(undefined)
      return
    }
    const num = Number(expireAmount)
    if (num <= 0) {
      setExpireSeconds(undefined)
      return
    }
    let seconds = num
    switch (expireUnit) {
      case 'minutes':
        seconds = num * 60
        break
      case 'hours':
        seconds = num * 3600
        break
      case 'days':
        seconds = num * 86400
        break
      case 'months':
        seconds = num * 2592000
        break
    }
    setExpireSeconds(seconds)
  }, [expireAmount, expireUnit])

  const { data: groupsData, isLoading: groupsLoading } = useGetAllGroups({ limit: PAGE_SIZE, offset: 0 })
  const { data: usersData, isLoading: usersLoading } = useGetUsers({ limit: PAGE_SIZE, offset: 0, search: debouncedUserSearch || undefined })
  const { data: adminsData, isLoading: adminsLoading } = useGetAdmins({ limit: PAGE_SIZE, offset: 0, username: debouncedAdminSearch || undefined })

  const filteredGroups =
    groupsData?.groups?.filter(group => {
      if (!debouncedGroupSearch) return true
      return group.name.toLowerCase().includes(debouncedGroupSearch.toLowerCase())
    }) || []

  const filteredHasGroups =
    groupsData?.groups?.filter(group => {
      if (operationType === 'groups' && selectedGroups.includes(group.id)) return false
      if (!debouncedHasGroupSearch) return true
      return group.name.toLowerCase().includes(debouncedHasGroupSearch.toLowerCase())
    }) || []

  const proxyMutation = useBulkModifyUsersProxySettings()
  const dataMutation = useBulkModifyUsersDatalimit()
  const expireMutation = useBulkModifyUsersExpire()
  const addGroupsMutation = useBulkAddGroupsToUsers()
  const removeGroupsMutation = useBulkRemoveUsersFromGroups()

  const nextStep = () => {
    if (currentStep < 3) setCurrentStep((currentStep + 1) as 1 | 2 | 3)
  }

  const prevStep = () => {
    if (currentStep > 1) setCurrentStep((currentStep - 1) as 1 | 2 | 3)
  }

  const canProceedToNext = () => {
    switch (currentStep) {
      case 1:
        if (operationType === 'proxy') {
          return selectedFlow || selectedMethod
        }
        if (operationType === 'groups') {
          return selectedGroups.length > 0
        }
        if (operationType === 'data') {
          return dataLimit !== undefined && dataLimit > 0
        }
        if (operationType === 'expire') {
          return expireAmount !== undefined && expireAmount > 0
        }
        return true
      case 2:
        switch (operationType) {
          case 'proxy':
            return selectedFlow || selectedMethod
          case 'data':
            return dataLimit !== undefined
          case 'expire':
            return expireSeconds !== undefined
          case 'groups':
            if (groupsOperation === 'remove') {
              return selectedHasGroups.length > 0 || selectedUsers.length > 0 || selectedAdmins.length > 0
            }
            return selectedUsers.length > 0 || selectedAdmins.length > 0 || selectedHasGroups.length > 0
          default:
            return false
        }
      case 3:
        return true
      default:
        return false
    }
  }

  const handleApply = () => {
    const totalTargets = selectedUsers.length + selectedAdmins.length + selectedGroups.length + selectedHasGroups.length
    if (operationType === 'groups' && groupsOperation === 'remove' && totalTargets === 0) {
      toast.error(t('error'), { description: t('bulk.noTargetsSelected') })
      return
    }
    setShowConfirmDialog(true)
  }

  const [showConfirmDialog, setShowConfirmDialog] = useState(false)

  const confirmApply = () => {
    const basePayload = {
      group_ids: selectedGroups.length ? selectedGroups : [],
      users: selectedUsers.length ? selectedUsers : [],
      admins: selectedAdmins.length ? selectedAdmins : [],
    }

    const payload = (() => {
      switch (operationType) {
        case 'proxy':
          return {
            ...basePayload,
            flow: selectedFlow === 'none' ? ('' as XTLSFlows) : selectedFlow,
            method: selectedMethod,
          }
        case 'data':
          const dataLimitBytes = gbToBytes(dataLimit!)
          return {
            ...basePayload,
            amount: dataOperation === 'subtract' ? -dataLimitBytes! : dataLimitBytes,
          }
        case 'expire':
          return {
            ...basePayload,
            amount: expireOperation === 'subtract' ? -expireSeconds! : expireSeconds,
          }
        case 'groups':
          return {
            group_ids: selectedGroups,
            has_group_ids: selectedHasGroups.length > 0 ? selectedHasGroups : [],
            users: selectedUsers.length ? selectedUsers : [],
            admins: selectedAdmins.length ? selectedAdmins : [],
          }
        default:
          return basePayload
      }
    })()

    const mutation = (() => {
      switch (operationType) {
        case 'proxy':
          return proxyMutation
        case 'data':
          return dataMutation
        case 'expire':
          return expireMutation
        case 'groups':
          return groupsOperation === 'add' ? addGroupsMutation : removeGroupsMutation
        default:
          return proxyMutation
      }
    })()

    mutation.mutate(
      { data: payload as any },
      {
        onSuccess: response => {
          const detail = typeof response === 'object' && response && 'detail' in response ? response.detail : undefined
          let description = ''
          if (detail) {
            description = typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2)
          } else if (typeof response === 'string') {
            description = response
          } else if (response && Object.keys(response).length > 0) {
            description = JSON.stringify(response, null, 2)
          } else {
            description = 'Operation completed successfully'
          }
          toast.success(t('operationSuccess', { defaultValue: 'Operation successful!' }), { description })

          setCurrentStep(1)
          setSelectedFlow(undefined)
          setSelectedMethod(undefined)
          setDataLimit(undefined)
          dataLimitInputRef.current = ''
          setExpireSeconds(undefined)
          setExpireAmount(undefined)
          setSelectedGroups([])
          setSelectedUsers([])
          setSelectedAdmins([])
          setSelectedHasGroups([])
          setShowConfirmDialog(false)
        },
        onError: error => {
          toast.error(t('operationFailed', { defaultValue: 'Operation failed!' }), {
            description: error?.message || JSON.stringify(error, null, 2),
          })
          setShowConfirmDialog(false)
        },
      },
    )
  }

  const totalTargets = selectedUsers.length + selectedAdmins.length + selectedGroups.length + (operationType === 'groups' ? selectedHasGroups.length : 0)
  const isApplyToAll = totalTargets === 0

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`
    if (seconds < 86400) return `${Math.round(seconds / 3600)}h`
    if (seconds < 2592000) return `${Math.round(seconds / 86400)}d`
    return `${Math.round(seconds / 2592000)}mo`
  }

  const steps = [
    { id: 1, title: t('bulk.configureSettings', { defaultValue: 'Configure Settings' }), icon: Settings },
    { id: 2, title: t('bulk.selectTargets', { defaultValue: 'Select Targets' }), icon: User },
    { id: 3, title: t('bulk.reviewAndApply', { defaultValue: 'Review & Apply' }), icon: CheckCircle },
  ]

  return (
    <div className="w-full space-y-3 sm:space-y-4">
      <div className="flex items-center justify-center px-2 sm:px-4">
        <div className="flex w-full max-w-3xl items-center">
          {steps.map((step, index) => {
            const Icon = step.icon
            const isActive = step.id === currentStep
            const isCompleted = step.id < currentStep
            const isUpcoming = step.id > currentStep
            return (
              <div key={step.id} className="flex flex-1 items-center">
                <div className="flex flex-1 items-center gap-2 sm:gap-3">
                  <div className="flex flex-shrink-0 flex-col items-center gap-1.5 sm:gap-2">
                    <div
                      className={cn(
                        'relative flex h-8 w-8 items-center justify-center rounded-full border-2 transition-all duration-200 sm:h-9 sm:w-9',
                        isCompleted && 'border-primary bg-primary text-primary-foreground shadow-sm',
                        isActive && 'scale-105 border-primary bg-background text-primary shadow-md',
                        isUpcoming && 'border-muted-foreground/30 bg-background text-muted-foreground',
                      )}
                    >
                      {isCompleted ? <CheckCircle className="h-4 w-4 sm:h-5 sm:w-5" /> : <Icon className={cn('h-4 w-4 sm:h-5 sm:w-5', isActive && 'text-primary')} />}
                      {isActive && <div className="absolute inset-0 animate-pulse rounded-full border-2 border-primary/20" />}
                    </div>
                    <span
                      className={cn(
                        'hidden max-w-[60px] text-center text-[10px] font-medium leading-tight sm:block sm:max-w-[80px] sm:text-xs',
                        isActive && 'font-semibold text-primary',
                        isCompleted && 'text-primary',
                        isUpcoming && 'text-muted-foreground',
                      )}
                    >
                      {step.title}
                    </span>
                  </div>
                  {index < steps.length - 1 && (
                    <div className="relative mx-1 h-0.5 flex-1 sm:mx-2">
                      <div className={cn('absolute inset-0 rounded-full transition-all duration-300', isCompleted ? 'bg-primary' : 'bg-muted')} />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <Card className="overflow-hidden">
        <CardContent className="p-3 sm:p-4 md:p-6">
          {currentStep === 1 && (
            <div className="space-y-3 sm:space-y-4">
              {operationType === 'proxy' && (
                <div className="space-y-3 sm:space-y-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="flow" className="flex items-center gap-1.5 text-sm font-medium">
                        <Network className="h-3.5 w-3.5 text-muted-foreground" />
                        {t('bulk.flowLabel', { defaultValue: 'Flow' })}
                      </Label>
                      <Select value={selectedFlow || ''} onValueChange={value => setSelectedFlow(value as XTLSFlows | 'none')}>
                        <SelectTrigger>
                          <SelectValue placeholder={t('bulk.selectFlowPlaceholder', { defaultValue: 'Select flow' })} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t('none', { defaultValue: 'None' })}</SelectItem>
                          {Object.values(XTLSFlows)
                            .filter(flow => flow !== '')
                            .map(flow => (
                              <SelectItem key={flow} value={flow}>
                                {flow}
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="method" className="flex items-center gap-1.5 text-sm font-medium">
                        <Settings className="h-3.5 w-3.5 text-muted-foreground" />
                        {t('bulk.methodLabel', { defaultValue: 'Method' })}
                      </Label>
                      <Select value={selectedMethod || ''} onValueChange={value => setSelectedMethod(value as ShadowsocksMethods)}>
                        <SelectTrigger>
                          <SelectValue placeholder={t('bulk.selectMethodPlaceholder', { defaultValue: 'Select method' })} />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.values(ShadowsocksMethods).map(method => (
                            <SelectItem key={method} value={method}>
                              {method}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )}

              {operationType === 'data' && (
                <div className="space-y-3 sm:space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="data-limit" className="flex items-center gap-1.5 text-sm font-medium">
                      <HardDrive className="h-3.5 w-3.5 text-muted-foreground" />
                      {t('bulk.dataLimitLabel', { defaultValue: 'Data Limit (GB)' })}
                    </Label>
                    <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
                      <ToggleGroup
                        type="single"
                        value={dataOperation}
                        onValueChange={value => value && setDataOperation(value as 'add' | 'subtract')}
                        className="w-full rounded-md border p-1 sm:w-auto"
                        defaultValue="add"
                      >
                        <ToggleGroupItem value="add" aria-label="Add" className="flex-1 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-initial">
                          <Plus className="h-4 w-4" />
                        </ToggleGroupItem>
                        <ToggleGroupItem value="subtract" aria-label="Subtract" className="flex-1 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-initial">
                          <Minus className="h-4 w-4" />
                        </ToggleGroupItem>
                      </ToggleGroup>
                      <div className="relative flex-1 sm:max-w-xs">
                        <Input
                          id="data-limit"
                          type="text"
                          inputMode="decimal"
                          placeholder={t('bulk.dataLimitPlaceholder', { defaultValue: 'Enter amount' })}
                          value={dataLimitInputRef.current !== '' ? dataLimitInputRef.current : dataLimit !== undefined && dataLimit > 0 ? String(dataLimit) : ''}
                          onChange={e => {
                            const rawValue = e.target.value.trim()

                            if (rawValue === '') {
                              dataLimitInputRef.current = ''
                              setDataLimit(undefined)
                              return
                            }

                            const validNumberPattern = /^-?(\d*\.?\d*|\.\d*)$/
                            if (validNumberPattern.test(rawValue)) {
                              dataLimitInputRef.current = rawValue

                              if (rawValue === '.' || rawValue === '-.' || rawValue === '-') {
                                setDataLimit(undefined)
                              } else if (rawValue.endsWith('.') && rawValue.length > 1) {
                                const prevValue = dataLimit !== undefined ? dataLimit : 0
                                setDataLimit(prevValue)
                              } else {
                                const numValue = parseFloat(rawValue)
                                if (!isNaN(numValue) && numValue >= 0) {
                                  setDataLimit(numValue)
                                } else {
                                  setDataLimit(undefined)
                                }
                              }
                            }
                          }}
                          onBlur={() => {
                            const rawValue = dataLimitInputRef.current.trim()
                            if (rawValue === '' || rawValue === '.' || rawValue === '0') {
                              dataLimitInputRef.current = ''
                              setDataLimit(undefined)
                            } else {
                              const numValue = parseFloat(rawValue)
                              if (!isNaN(numValue) && numValue >= 0) {
                                const finalValue = numValue
                                dataLimitInputRef.current = finalValue > 0 ? String(finalValue) : ''
                                setDataLimit(finalValue > 0 ? finalValue : undefined)
                              } else {
                                dataLimitInputRef.current = ''
                                setDataLimit(undefined)
                              }
                            }
                          }}
                          className="pr-12"
                        />
                        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">GB</span>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {dataOperation === 'add' ? t('bulk.addDataLimit', { defaultValue: 'Add Data Limit' }) : t('bulk.subtractDataLimit', { defaultValue: 'Subtract Data Limit' })}
                    </p>
                  </div>
                </div>
              )}

              {operationType === 'expire' && (
                <div className="space-y-3 sm:space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="expire-amount" className="flex items-center gap-1.5 text-sm font-medium">
                      <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                      {t('bulk.expireDate', { defaultValue: 'Expire Date' })}
                    </Label>
                    <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
                      <ToggleGroup
                        type="single"
                        value={expireOperation}
                        onValueChange={value => value && setExpireOperation(value as 'add' | 'subtract')}
                        className="w-full rounded-md border p-1 sm:w-auto"
                        defaultValue="add"
                      >
                        <ToggleGroupItem value="add" aria-label="Add" className="flex-1 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-initial">
                          <Plus className="h-4 w-4" />
                        </ToggleGroupItem>
                        <ToggleGroupItem value="subtract" aria-label="Subtract" className="flex-1 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-initial">
                          <Minus className="h-4 w-4" />
                        </ToggleGroupItem>
                      </ToggleGroup>
                      <div className="relative flex-1 sm:max-w-xs">
                        <Input
                          id="expire-amount"
                          type="number"
                          placeholder={t('bulk.expire.placeholder', { defaultValue: 'Enter amount' })}
                          value={expireAmount === undefined ? '' : expireAmount}
                          onChange={e => {
                            const value = Number.parseFloat(e.target.value)
                            if (!isNaN(value) && value > 0) setExpireAmount(value)
                            else if (e.target.value === '') setExpireAmount(undefined)
                          }}
                          step="1"
                          min="1"
                          className="pr-20"
                        />
                        <Select value={expireUnit} onValueChange={v => setExpireUnit(v as ExpiryUnit)}>
                          <SelectTrigger className="pointer-events-auto absolute right-0 top-0 h-full w-20 rounded-l-none border-l-0">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="seconds">{t('time.seconds', { defaultValue: 'Seconds' })}</SelectItem>
                            <SelectItem value="minutes">{t('time.mins', { defaultValue: 'Minutes' })}</SelectItem>
                            <SelectItem value="hours">{t('time.hours', { defaultValue: 'Hours' })}</SelectItem>
                            <SelectItem value="days">{t('time.days', { defaultValue: 'Days' })}</SelectItem>
                            <SelectItem value="months">{t('time.months', { defaultValue: 'Months' })}</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {expireOperation === 'add' ? t('bulk.addExpiry', { defaultValue: 'Add to Expiry' }) : t('bulk.subtractExpiry', { defaultValue: 'Subtract from Expiry' })}
                    </p>
                  </div>
                </div>
              )}

              {operationType === 'groups' && (
                <div className="space-y-4 sm:space-y-5">
                  <div className="space-y-2.5 sm:space-y-3">
                    <Label className="flex items-center gap-1.5 text-sm font-medium">
                      <Users2 className="h-3.5 w-3.5 text-muted-foreground" />
                      {t('bulk.groups', { defaultValue: 'Groups' })}
                    </Label>
                    <div>
                      <ToggleGroup
                        type="single"
                        value={groupsOperation}
                        onValueChange={value => value && setGroupsOperation(value as 'add' | 'remove')}
                        className="inline-flex w-full rounded-md border p-1 sm:w-auto"
                        defaultValue="add"
                      >
                        <ToggleGroupItem value="add" aria-label="Add" className="flex-1 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-initial sm:px-4">
                          <Plus className="h-4 w-4" />
                          <span className="ml-1.5 text-xs sm:ml-2 sm:text-sm">{t('bulk.addGroups', { defaultValue: 'Add Groups' })}</span>
                        </ToggleGroupItem>
                        <ToggleGroupItem value="remove" aria-label="Remove" className="flex-1 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-initial sm:px-4">
                          <Minus className="h-4 w-4" />
                          <span className="ml-1.5 text-xs sm:ml-2 sm:text-sm">{t('bulk.removeGroups', { defaultValue: 'Remove Groups' })}</span>
                        </ToggleGroupItem>
                      </ToggleGroup>
                    </div>
                  </div>

                  <div className="space-y-3 sm:space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <Label className="flex items-center gap-1.5 text-sm font-medium">
                        <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground" />
                        {groupsOperation === 'add' ? t('bulk.groupsToAdd', { defaultValue: 'Groups to Add' }) : t('bulk.groupsToRemove', { defaultValue: 'Groups to Remove' })}
                      </Label>
                      {filteredGroups.length > 0 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            const allSelected = filteredGroups.every(group => selectedGroups.includes(group.id))
                            if (allSelected) {
                              setSelectedGroups([])
                            } else {
                              setSelectedGroups(filteredGroups.map(group => group.id))
                            }
                          }}
                          className="h-8 flex-shrink-0 text-xs sm:text-sm"
                        >
                          {filteredGroups.every(group => selectedGroups.includes(group.id)) ? t('deselectAll') : t('selectAll')}
                        </Button>
                      )}
                    </div>
                    <Command className="rounded-md border">
                      <CommandInput placeholder={t('bulk.searchGroups', { defaultValue: 'Search groups...' })} value={groupCommandSearch} onValueChange={setGroupCommandSearch} />
                      <CommandEmpty>{t('noResults', { defaultValue: 'No results found.' })}</CommandEmpty>
                      <CommandGroup dir="ltr" className="max-h-40 overflow-auto">
                        {filteredGroups
                          .filter(group => !groupCommandSearch || group.name.toLowerCase().includes(groupCommandSearch.toLowerCase()))
                          .map(group => (
                            <CommandItem
                              key={group.id}
                              onSelect={() => {
                                if (selectedGroups.includes(group.id)) {
                                  setSelectedGroups(selectedGroups.filter(id => id !== group.id))
                                } else {
                                  setSelectedGroups([...selectedGroups, group.id])
                                }
                              }}
                            >
                              <div className={cn('mr-2 flex h-4 w-4 items-center justify-center rounded-sm border', selectedGroups.includes(group.id) ? 'border-primary bg-primary' : 'border-muted')}>
                                {selectedGroups.includes(group.id) && <CheckCircle className="h-3 w-3 text-primary-foreground" />}
                              </div>
                              {group.name}
                            </CommandItem>
                          ))}
                      </CommandGroup>
                    </Command>
                    {selectedGroups.length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-1 sm:gap-2.5">
                        {filteredGroups
                          .filter(group => selectedGroups.includes(group.id))
                          .map(group => (
                            <Badge key={group.id} variant="secondary" className="flex items-center gap-1.5 px-2.5 py-1">
                              {group.name}
                              <X
                                className="h-3 w-3 cursor-pointer transition-colors hover:text-destructive"
                                onClick={() => {
                                  setSelectedGroups(selectedGroups.filter(id => id !== group.id))
                                }}
                              />
                            </Badge>
                          ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {currentStep === 2 && (
            <div className="space-y-3 sm:space-y-4">
              <div className="space-y-2">
                {isApplyToAll && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-2.5 dark:border-blue-800 dark:bg-blue-950/20 sm:p-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-blue-600 dark:text-blue-400 sm:h-4 sm:w-4" />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium leading-relaxed text-blue-800 dark:text-blue-200 sm:text-sm">
                          {t('bulk.noSelectionInfo', { defaultValue: 'No targets selected. This operation will apply to ALL users, admins, and groups in the system.' })}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
                {operationType === 'groups' ? (
                  <SelectorPanel
                    icon={Users2}
                    title={t('bulk.selectHasGroups', { defaultValue: 'Select Has Groups' })}
                    items={filteredHasGroups}
                    selected={selectedHasGroups}
                    setSelected={setSelectedHasGroups}
                    search={hasGroupSearch}
                    setSearch={setHasGroupSearch}
                    searchPlaceholder={t('bulk.searchHasGroups', { defaultValue: 'Search has groups...' })}
                    selectAllLabel={t('selectAll', { defaultValue: 'Select All' })}
                    deselectAllLabel={t('deselectAll', { defaultValue: 'Deselect All' })}
                    itemLabelKey="name"
                    itemValueKey="id"
                    searchKey="name"
                    t={t}
                    isLoading={groupsLoading}
                    description={
                      groupsOperation === 'remove'
                        ? t('bulk.hasGroupsDescription', { defaultValue: 'Users must have these groups to be affected' })
                        : t('bulk.hasGroupsDescriptionAdd', { defaultValue: 'Filter users who have these groups' })
                    }
                    isRequired={groupsOperation === 'remove'}
                    hasError={groupsOperation === 'remove' && selectedHasGroups.length === 0}
                  />
                ) : (
                  <SelectorPanel
                    icon={Users2}
                    title={t('bulk.selectGroups', { defaultValue: 'Select Groups' })}
                    items={filteredGroups}
                    selected={selectedGroups}
                    setSelected={setSelectedGroups}
                    search={groupSearch}
                    setSearch={setGroupSearch}
                    searchPlaceholder={t('bulk.searchGroups', { defaultValue: 'Search groups...' })}
                    selectAllLabel={t('selectAll', { defaultValue: 'Select All' })}
                    deselectAllLabel={t('deselectAll', { defaultValue: 'Deselect All' })}
                    itemLabelKey="name"
                    itemValueKey="id"
                    searchKey="name"
                    t={t}
                    isLoading={groupsLoading}
                  />
                )}

                <SelectorPanel
                  icon={User}
                  title={t('bulk.selectUsers', { defaultValue: 'Select Users' })}
                  items={usersData?.users || []}
                  selected={selectedUsers}
                  setSelected={setSelectedUsers}
                  search={userSearch}
                  setSearch={setUserSearch}
                  searchPlaceholder={t('bulk.searchUsers', { defaultValue: 'Search users...' })}
                  selectAllLabel={t('selectAll', { defaultValue: 'Select All' })}
                  deselectAllLabel={t('deselectAll', { defaultValue: 'Deselect All' })}
                  itemLabelKey="username"
                  itemValueKey="id"
                  searchKey="username"
                  t={t}
                  isLoading={usersLoading}
                />

                <SelectorPanel
                  icon={Shield}
                  title={t('bulk.selectAdmins', { defaultValue: 'Select Admins' })}
                  items={(adminsData?.admins || []).filter(a => typeof a.id === 'number' && typeof a.username === 'string').map(a => ({ id: a.id as number, username: a.username as string }))}
                  selected={selectedAdmins}
                  setSelected={setSelectedAdmins}
                  search={adminSearch}
                  setSearch={setAdminSearch}
                  searchPlaceholder={t('bulk.searchAdmins', { defaultValue: 'Search admins...' })}
                  selectAllLabel={t('selectAll', { defaultValue: 'Select All' })}
                  deselectAllLabel={t('deselectAll', { defaultValue: 'Deselect All' })}
                  itemLabelKey="username"
                  itemValueKey="id"
                  searchKey="username"
                  t={t}
                  isLoading={adminsLoading}
                />
              </div>
            </div>
          )}

          {currentStep === 3 && (
            <div className="space-y-3 sm:space-y-4">
              <div className="space-y-2 rounded-lg bg-muted/50 p-3 sm:space-y-3 sm:p-4">
                <h3 className="text-sm font-medium">{t('bulk.operationSummary', { defaultValue: 'Operation Summary' })}</h3>

                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">{t('bulk.operationType', { defaultValue: 'Operation Type' })}:</span>
                    <Badge variant="secondary">
                      {operationType === 'proxy' && t('bulk.proxySettings')}
                      {operationType === 'data' && t('bulk.dataLimit')}
                      {operationType === 'expire' && t('bulk.expireDate')}
                      {operationType === 'groups' && t('bulk.groups')}
                    </Badge>
                  </div>

                  {operationType === 'proxy' && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('bulk.settings', { defaultValue: 'Settings' })}:</span>
                      <span>{t('bulk.flowMethod', { flow: selectedFlow === 'none' || !selectedFlow ? t('none') : selectedFlow, method: selectedMethod || t('none') })}</span>
                    </div>
                  )}

                  {operationType === 'data' && dataLimit && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('bulk.settings', { defaultValue: 'Settings' })}:</span>
                      <span dir="ltr">
                        {dataOperation === 'add' ? '+' : '-'}
                        {formatBytes(gbToBytes(dataLimit)!)}
                      </span>
                    </div>
                  )}

                  {operationType === 'expire' && expireSeconds && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">{t('bulk.settings', { defaultValue: 'Settings' })}:</span>
                      <span>
                        {expireOperation === 'add' ? '+' : '-'}
                        {formatTime(expireSeconds)}
                      </span>
                    </div>
                  )}

                  {operationType === 'groups' && (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">{t('bulk.settings', { defaultValue: 'Settings' })}:</span>
                        <Badge variant={groupsOperation === 'remove' ? 'destructive' : 'default'}>{groupsOperation === 'add' ? t('bulk.addGroups') : t('bulk.removeGroups')}</Badge>
                      </div>
                      {selectedHasGroups.length > 0 && (
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">{t('bulk.hasGroups', { defaultValue: 'Has Groups' })}:</span>
                          <span className="text-sm">
                            {selectedHasGroups.length} {t('bulk.selected', { defaultValue: 'selected' })}
                          </span>
                        </div>
                      )}
                      {selectedGroups.length > 0 && (
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">{t('bulk.groups', { defaultValue: 'Groups' })}:</span>
                          <span className="text-sm">
                            {selectedGroups.length} {t('bulk.selected', { defaultValue: 'selected' })}
                          </span>
                        </div>
                      )}
                    </>
                  )}

                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">{t('bulk.targets', { defaultValue: 'Targets' })}:</span>
                    <span>{isApplyToAll ? t('bulk.allTargets', { defaultValue: 'All users, admins, and groups' }) : t('bulk.targetsCount', { count: totalTargets })}</span>
                  </div>
                </div>
              </div>

              {isApplyToAll && (
                <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-2.5 dark:border-yellow-800 dark:bg-yellow-950/20 sm:p-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-yellow-600 dark:text-yellow-400 sm:h-4 sm:w-4" />
                    <div className="min-w-0 flex-1">
                      <h4 className="text-xs font-medium text-yellow-800 dark:text-yellow-200 sm:text-sm">{t('bulk.warning', { defaultValue: 'Warning' })}</h4>
                      <p className="mt-1 text-xs leading-relaxed text-yellow-700 dark:text-yellow-300 sm:text-sm">
                        {t('bulk.applyToAllWarning', { defaultValue: 'This operation will apply to ALL users, admins, and groups in the system.' })}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <div className={cn('flex flex-col-reverse gap-2 px-2 sm:flex-row sm:px-0', currentStep === 1 ? 'justify-end' : 'justify-between')}>
        {currentStep > 1 && (
          <Button variant="outline" onClick={prevStep} size="sm" className="w-full sm:w-auto">
            <ChevronLeft className={cn('h-4 w-4', isRTL ? 'ml-1.5 rotate-180' : 'mr-1.5')} />
            <span>{t('previous', { defaultValue: 'Previous' })}</span>
          </Button>
        )}

        {currentStep < 3 ? (
          <Button onClick={nextStep} disabled={!canProceedToNext()} size="sm" className="w-full sm:w-auto">
            <span>{t('next', { defaultValue: 'Next' })}</span>
            <ChevronRight className={cn('h-4 w-4', isRTL ? 'mr-1.5 rotate-180' : 'ml-1.5')} />
          </Button>
        ) : (
          <Button onClick={handleApply} disabled={!canProceedToNext()} size="sm" className="w-full sm:w-auto">
            <CheckCircle className={cn('h-4 w-4', isRTL ? 'ml-1.5' : 'mr-1.5')} />
            <span>{t('bulk.applyOperation', { defaultValue: 'Apply Operation' })}</span>
          </Button>
        )}
      </div>

      <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('bulk.confirmOperation', { defaultValue: 'Confirm Operation' })}</AlertDialogTitle>
            <AlertDialogDescription>
              {isApplyToAll
                ? t('bulk.confirmApplyAll', { defaultValue: 'Are you sure you want to apply this operation to ALL users, admins, and groups?' })
                : t('bulk.confirmApplyTargets', { count: totalTargets, defaultValue: 'Are you sure you want to apply this operation to {{count}} target(s)?' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel', { defaultValue: 'Cancel' })}</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmApply}
              disabled={proxyMutation.isPending || dataMutation.isPending || expireMutation.isPending || addGroupsMutation.isPending || removeGroupsMutation.isPending}
            >
              {proxyMutation.isPending || dataMutation.isPending || expireMutation.isPending || addGroupsMutation.isPending || removeGroupsMutation.isPending
                ? t('applying', { defaultValue: 'Applying...' })
                : t('confirm', { defaultValue: 'Confirm' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
