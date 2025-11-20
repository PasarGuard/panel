import GroupsSelector from '@/components/common/groups-selector'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import useDirDetection from '@/hooks/use-dir-detection'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { cn } from '@/lib/utils'
import { DatePicker } from '@/components/common/date-picker'
import { UseEditFormValues, UseFormValues, userCreateSchema, userEditSchema } from '@/pages/_dashboard.users'
import {
  getGeneralSettings,
  getGetGeneralSettingsQueryKey,
  useCreateUser,
  useCreateUserFromTemplate,
  useGetUsers,
  useGetUserTemplates,
  useModifyUser,
  useModifyUserWithTemplate,
  type UserResponse,
  type UsersResponse,
} from '@/service/api'
import { dateUtils, useRelativeExpiryDate } from '@/utils/dateFormatter'
import { formatBytes, gbToBytes } from '@/utils/formatByte'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Layers, ListStart, Lock, RefreshCcw, Users } from 'lucide-react'
import React, { useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { v4 as uuidv4, v5 as uuidv5, v7 as uuidv7 } from 'uuid'
import { z } from 'zod'

interface UserModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<UseFormValues | UseEditFormValues>
  editingUser: boolean
  editingUserId?: number
  editingUserData?: any // The user data object when editing
  onSuccessCallback?: (user: UserResponse) => void
}

const isDate = (v: unknown): v is Date => typeof v === 'object' && v !== null && v instanceof Date

// Add template validation schema
const templateUserSchema = z.object({
  username: z.string().min(3, 'validation.minLength').max(32, 'validation.maxLength'),
  note: z.string().optional(),
})

// Add template modification schema
const templateModifySchema = z.object({
  note: z.string().optional(),
  user_template_id: z.number(),
})

// Helper for UUID namespace (for v5)
const UUID_NAMESPACE = '6ba7b810-9dad-11d1-80b4-00c04fd430c8'

// Helper function to get local ISO time string with timezone offset
// This is kept for backward compatibility with normalizeExpire function
function getLocalISOTime(date: Date): string {
  // Create a properly formatted ISO string with timezone offset
  const tzOffset = -date.getTimezoneOffset()
  const offsetSign = tzOffset >= 0 ? '+' : '-'
  const pad = (num: number) => Math.abs(num).toString().padStart(2, '0')

  const offsetHours = pad(Math.floor(Math.abs(tzOffset) / 60))
  const offsetMinutes = pad(Math.abs(tzOffset) % 60)

  // Get the local date/time components without timezone conversion
  const year = date.getFullYear()
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())
  const seconds = pad(date.getSeconds())

  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}${offsetSign}${offsetHours}:${offsetMinutes}`
}

// Add this new component before the UserModal component
const ExpiryDateField = ({
  field,
  displayDate,
  calendarOpen,
  setCalendarOpen,
  handleFieldChange,
  label,
  useUtcTimestamp = false,
  fieldName = 'expire',
}: {
  field: any
  displayDate: Date | null
  calendarOpen: boolean
  setCalendarOpen: (open: boolean) => void
  handleFieldChange: (field: string, value: any) => void
  label: string
  useUtcTimestamp?: boolean
  fieldName?: string
}) => {
  const { t } = useTranslation()
  const expireInfo = useRelativeExpiryDate(displayDate ? Math.floor(displayDate.getTime() / 1000) : null)
  const dir = useDirDetection()

  const handleDateChange = React.useCallback(
    (date: Date | undefined) => {
      if (date) {
        // Use the same logic as centralized DatePicker
        const value = useUtcTimestamp ? Math.floor(date.getTime() / 1000) : getLocalISOTime(date)
        field.onChange(value)
        handleFieldChange(fieldName, value)
      } else {
        field.onChange('')
        handleFieldChange(fieldName, undefined)
      }
    },
    [field, handleFieldChange, useUtcTimestamp, fieldName],
  )

  const handleShortcut = React.useCallback(
    (days: number) => {
      const baseDate = displayDate || new Date()
      const targetDate = new Date(baseDate)
      targetDate.setDate(baseDate.getDate() + days)
      // Preserve time from base date
      handleDateChange(targetDate)
    },
    [handleDateChange, displayDate],
  )

  // Memoize now to start of today to prevent it from changing every second
  // This ensures minDate only changes once per day, not on every render
  const now = React.useMemo(() => {
    const today = new Date()
    return new Date(today.getFullYear(), today.getMonth(), today.getDate())
  }, [])

  const maxDate = React.useMemo(() => {
    return new Date(now.getFullYear() + 15, 11, 31)
  }, [now])

  const shortcuts = [
    { label: '+7d', days: 7 },
    { label: '+1m', days: 30 },
    { label: '+2m', days: 60 },
    { label: '+3m', days: 90 },
    { label: '+6m', days: 180 },
    { label: '+1y', days: 365 },
  ]

  return (
    <FormItem className="flex flex-1 flex-col">
      <FormLabel className="mb-0.5">{label}</FormLabel>
      <div className="space-y-2 lg:!mt-0">
        <div dir="ltr" className="flex flex-wrap items-center gap-1 lg:hidden">
          {shortcuts.map(({ label, days }) => (
            <Button
              key={label}
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2.5 text-xs text-muted-foreground hover:text-foreground"
              onClick={e => {
                e.preventDefault()
                e.stopPropagation()
                handleShortcut(days)
              }}
            >
              {label}
            </Button>
          ))}
        </div>
        <div className="relative">
          <DatePicker
            mode="single"
            date={displayDate}
            onDateChange={handleDateChange}
            showTime={true}
            useUtcTimestamp={useUtcTimestamp}
            placeholder={t('userDialog.expireDate', { defaultValue: 'Expire date' })}
            minDate={now}
            maxDate={maxDate}
            open={calendarOpen}
            onOpenChange={setCalendarOpen}
            fieldName={fieldName}
            onFieldChange={handleFieldChange}
          />
          {displayDate && expireInfo?.time && (
            <p
              className={cn(
                fieldName !== 'on_hold_timeout' && 'lg:w-48',
                'absolute right-0 top-full mt-1 whitespace-nowrap text-end text-xs text-muted-foreground lg:overflow-hidden lg:text-ellipsis',
                dir === 'rtl' ? 'right-0' : 'left-0',
              )}
            >
              {(() => {
                const now = new Date()
                const isExpired = displayDate < now
                const translationKey = isExpired ? 'expired' : 'expires'
                return t(translationKey, { time: expireInfo.time, defaultValue: isExpired ? 'Expired {{time}}' : 'Expires in {{time}}' })
              })()}
            </p>
          )}
        </div>
      </div>
      <FormMessage />
    </FormItem>
  )
}

export { ExpiryDateField }

// Custom Select component that works reliably on mobile
const StatusSelect = ({
  value,
  onValueChange,
  placeholder,
  children,
  disabled,
}: {
  value?: string
  onValueChange?: (value: string) => void
  placeholder?: string
  children: React.ReactNode
  disabled?: boolean
}) => {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation()

  const handleSelect = (selectedValue: string) => {
    onValueChange?.(selectedValue)
    setOpen(false)
  }

  const getStatusText = (statusValue?: string) => {
    if (!statusValue) return placeholder || t('userDialog.selectStatus', { defaultValue: 'Select status' })

    switch (statusValue) {
      case 'active':
        return t('status.active', { defaultValue: 'Active' })
      case 'disabled':
        return t('status.disabled', { defaultValue: 'Disabled' })
      case 'on_hold':
        return t('status.on_hold', { defaultValue: 'On Hold' })
      default:
        return placeholder || t('userDialog.selectStatus', { defaultValue: 'Select status' })
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} className="h-9 w-full justify-between px-3 py-2 text-sm" disabled={disabled}>
          <span className="truncate">{getStatusText(value)}</span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-1" align="start">
        {React.Children.map(children, child => {
          if (React.isValidElement(child) && child.props.value) {
            return React.cloneElement(child, {
              onSelect: handleSelect,
            })
          }
          return child
        })}
      </PopoverContent>
    </Popover>
  )
}

const StatusSelectItem = ({ value, children, onSelect }: { value: string; children: React.ReactNode; onSelect?: (value: string) => void }) => {
  const getDotColor = () => {
    switch (value) {
      case 'active':
        return 'bg-green-500'
      case 'disabled':
        return 'bg-zinc-500'
      case 'on_hold':
        return 'bg-violet-500'
      default:
        return 'bg-gray-500'
    }
  }

  return (
    <div
      className="relative flex w-full min-w-0 cursor-pointer select-none items-center rounded-sm px-2 py-2 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground"
      onClick={() => onSelect?.(value)}
    >
      <span className="min-w-0 flex-1 truncate pr-2">{children}</span>
      <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
        <div className={`h-2 w-2 rounded-full ${getDotColor()}`} />
      </span>
    </div>
  )
}

export default function UserModal({ isDialogOpen, onOpenChange, form, editingUser, editingUserId, onSuccessCallback }: UserModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const handleError = useDynamicErrorHandler()
  const [loading, setLoading] = useState(false)
  const status = form.watch('status')
  const [activeTab, setActiveTab] = useState<'groups' | 'templates'>('groups')
  const tabs = [
    { id: 'groups', label: 'groups', icon: Users },
    { id: 'templates', label: 'templates.title', icon: Layers },
  ]
  const [nextPlanEnabled, setNextPlanEnabled] = useState(false)
  const [nextPlanManuallyDisabled, setNextPlanManuallyDisabled] = useState(false)
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [expireCalendarOpen, setExpireCalendarOpen] = useState(false)
  const [onHoldCalendarOpen, setOnHoldCalendarOpen] = useState(false)

  const hasNextPlanValues = React.useCallback((nextPlan: any): boolean => {
    if (!nextPlan || typeof nextPlan !== 'object') return false

    const hasAnyValue = !!(
      (nextPlan.user_template_id !== undefined && nextPlan.user_template_id !== null) ||
      (nextPlan.expire !== undefined && nextPlan.expire !== null) ||
      (nextPlan.data_limit !== undefined && nextPlan.data_limit !== null) ||
      nextPlan.add_remaining_traffic !== undefined
    )

    return hasAnyValue
  }, [])

  const nextPlanValue = React.useMemo(
    () => ({
      user_template_id: form.watch('next_plan.user_template_id'),
      expire: form.watch('next_plan.expire'),
      data_limit: form.watch('next_plan.data_limit'),
      add_remaining_traffic: form.watch('next_plan.add_remaining_traffic'),
    }),
    [form.watch('next_plan.user_template_id'), form.watch('next_plan.expire'), form.watch('next_plan.data_limit'), form.watch('next_plan.add_remaining_traffic')],
  )

  useEffect(() => {
    if (!isDialogOpen) {
      setExpireCalendarOpen(false)
      setOnHoldCalendarOpen(false)
      setNextPlanEnabled(false)
      setNextPlanManuallyDisabled(false)
    }
  }, [isDialogOpen])
  const [touchedFields, setTouchedFields] = useState<Record<string, boolean>>({})
  const [isFormValid, setIsFormValid] = useState(false)
  // Ref to store raw input value for data_limit to allow typing decimals
  const dataLimitInputRef = React.useRef<string>('')

  const handleModalOpenChange = React.useCallback(
    (open: boolean) => {
      if (!open) {
        // Only reset form if not editing (for create mode)
        // When editing, parent component will repopulate the form
        if (!editingUser) {
          form.reset()
        }
        setTouchedFields({})
        setIsFormValid(false)
        setActiveTab('groups')
        setSelectedTemplateId(null)
        setNextPlanEnabled(false)
        dataLimitInputRef.current = ''
      }
      onOpenChange(open)
    },
    [form, onOpenChange, editingUser],
  )

  const handleFieldChange = React.useCallback(
    (fieldName: string, value: any) => {
      setTouchedFields(prev => ({ ...prev, [fieldName]: true }))
      const currentValues = {
        ...form.getValues(),
        [fieldName]: value,
      }
      const isValid = validateAllFields(currentValues, { ...touchedFields, [fieldName]: true })
      setIsFormValid(isValid)
    },
    [form, touchedFields],
  )

  // Add handleFieldBlur function
  const handleFieldBlur = React.useCallback(
    (fieldName: string) => {
      if (!touchedFields[fieldName]) {
        setTouchedFields(prev => ({ ...prev, [fieldName]: true }))
        const currentValues = form.getValues()
        const isValid = validateAllFields(currentValues, { ...touchedFields, [fieldName]: true })
        setIsFormValid(isValid)
      }
    },
    [form, touchedFields],
  )

  // Get the expire value from the form
  const expireValue = form.watch('expire')
  const onHoldValue = form.watch('on_hold_timeout')
  const dataLimitValue = form.watch('data_limit')

  let displayDate: Date | null = null
  let onHoldDisplayDate: Date | null = null

  // Handle various formats of expire value using the same logic as OnlineBadge/OnlineStatus
  const parseDateValue = (value: unknown): Date | null => {
    if (isDate(value)) {
      return value
    } else if (typeof value === 'string') {
      if (value === '') {
        return null
      } else {
        // Use the same dateUtils.toDayjs logic as other components
        try {
          const dayjsDate = dateUtils.toDayjs(value.trim())
          if (dayjsDate.isValid()) {
            return dayjsDate.toDate()
          }
        } catch (error) {
          // If dayjs parsing fails, return null
        }
      }
    } else if (typeof value === 'number') {
      try {
        const dayjsDate = dateUtils.toDayjs(value)
        if (dayjsDate.isValid()) {
          return dayjsDate.toDate()
        }
      } catch (error) {
        // If dayjs parsing fails, return null
      }
    }
    return null
  }

  displayDate = parseDateValue(expireValue)
  onHoldDisplayDate = parseDateValue(onHoldValue)

  // Query client for data refetching
  const queryClient = useQueryClient()

  // Get refetch function for users
  const { refetch: refetchUsers } = useGetUsers(
    {},
    {
      query: { enabled: false },
    },
  )

  // Fetch data for tabs without caching
  const { data: templatesData, isLoading: templatesLoading } = useGetUserTemplates(undefined, {
    query: {
      staleTime: 0,
      gcTime: 0,
      refetchOnMount: true,
      refetchOnReconnect: false,
      enabled: isDialogOpen,
    },
  })

  const { data: generalSettings } = useQuery({
    queryKey: getGetGeneralSettingsQueryKey(),
    queryFn: () => getGeneralSettings(),
    enabled: isDialogOpen,
    refetchOnMount: true,
  })

  // Function to refresh all user-related data
  const refreshUserData = (user: UserResponse, isEdit: boolean = false) => {
    if (isEdit) {
      // When editing, update the specific user in the cache without refreshing all users
      // Get all cached queries for users
      queryClient.setQueriesData<UsersResponse>(
        {
          queryKey: ['/api/users'],
          exact: false,
        },
        oldData => {
          if (!oldData) return oldData

          // Find and update the user in the users array
          const updatedUsers = oldData.users.map(u => (u.username === user.username ? user : u))

          return {
            ...oldData,
            users: updatedUsers,
          }
        },
      )

      // Still invalidate usage/stats queries as they may have changed
      queryClient.invalidateQueries({ queryKey: ['getUsersUsage'] })
      queryClient.invalidateQueries({ queryKey: ['getUserStats'] })
      queryClient.invalidateQueries({ queryKey: ['getInboundStats'] })
      queryClient.invalidateQueries({ queryKey: ['getUserOnlineStats'] })
    } else {
      // When creating, invalidate and refetch all users
      queryClient.invalidateQueries({ queryKey: ['/api/users'] })
      queryClient.invalidateQueries({ queryKey: ['getUsersUsage'] })
      queryClient.invalidateQueries({ queryKey: ['getUserStats'] })
      queryClient.invalidateQueries({ queryKey: ['getInboundStats'] })
      queryClient.invalidateQueries({ queryKey: ['getUserOnlineStats'] })

      // Force immediate refetch
      refetchUsers()
    }

    // Call the success callback if provided
    if (onSuccessCallback) {
      onSuccessCallback(user)
    }
  }

  const createUserMutation = useCreateUser({
    mutation: {
      onSuccess: data => refreshUserData(data),
    },
  })
  const modifyUserMutation = useModifyUser({
    mutation: {
      onSuccess: data => refreshUserData(data, true),
    },
  })
  const createUserFromTemplateMutation = useCreateUserFromTemplate({
    mutation: {
      onSuccess: data => refreshUserData(data),
    },
  })

  // Add the mutation hook at the top with other mutations
  const modifyUserWithTemplateMutation = useModifyUserWithTemplate({
    mutation: {
      onSuccess: data => refreshUserData(data, true),
    },
  })

  useEffect(() => {
    // When the dialog closes, reset errors
    if (!isDialogOpen) {
      form.clearErrors()
    }
  }, [isDialogOpen, form])

  useEffect(() => {
    // Set form validation schema
    form.clearErrors()
    if (!editingUser && !selectedTemplateId) {
      form.setError('username', {
        type: 'manual',
        message: t('validation.required', { field: t('username', { defaultValue: 'Username' }) }),
      })
    }
  }, [form, editingUser, t, selectedTemplateId])

  // Add new effect to update form validity when template is selected
  useEffect(() => {
    if (selectedTemplateId) {
      // If template is selected, only username is required
      const username = form.getValues('username')
      if (username && username.length >= 3) {
        // Clear all errors and set form as valid
        form.clearErrors()
        setIsFormValid(true)
        setTouchedFields({ username: true })
      } else {
        // Set username error only
        form.clearErrors()
        form.setError('username', {
          type: 'manual',
          message: t('validation.required', { field: t('username', { defaultValue: 'Username' }) }),
        })
        setIsFormValid(false)
      }
    }
  }, [selectedTemplateId, form, t])

  useEffect(() => {
    if (status === 'on_hold') {
      // Set default on_hold_expire_duration if not set
      const duration = form.getValues('on_hold_expire_duration')
      const touched = touchedFields['on_hold_expire_duration']
      // Only set default if the field hasn't been touched by user and has no value
      if (!touched && (!duration || duration < 1)) {
        const defaultDuration = 30 * 24 * 60 * 60 // 7 days in seconds
        form.setValue('on_hold_expire_duration', defaultDuration)
        handleFieldChange('on_hold_expire_duration', defaultDuration)
      }
      // Clear expire field when switching to on_hold status
      form.setValue('expire', undefined)
      form.clearErrors('expire')
    } else {
      // Clear on_hold fields when switching away from on_hold status
      form.setValue('on_hold_expire_duration', undefined)
      form.clearErrors('on_hold_expire_duration')
      form.setValue('on_hold_timeout', undefined)
      form.clearErrors('on_hold_timeout')
    }
  }, [status, form, t, handleFieldChange, touchedFields])

  useEffect(() => {
    if (!nextPlanEnabled) {
      form.setValue('next_plan', undefined)
      handleFieldChange('next_plan', undefined)
    } else {
      setNextPlanManuallyDisabled(false)
      const isEmpty = !nextPlanValue.user_template_id && !nextPlanValue.expire && !nextPlanValue.data_limit && nextPlanValue.add_remaining_traffic === undefined
      if (isEmpty) {
        form.setValue('next_plan', {})
        handleFieldChange('next_plan', {})
      }
    }
  }, [nextPlanEnabled, nextPlanValue])

  useEffect(() => {
    if (!isDialogOpen || !editingUser || nextPlanManuallyDisabled) return

    const shouldBeEnabled = hasNextPlanValues(nextPlanValue)

    if (shouldBeEnabled && !nextPlanEnabled) {
      setNextPlanEnabled(true)
    }
    // Don't automatically disable - let user control it via the toggle
  }, [nextPlanValue, nextPlanEnabled, isDialogOpen, editingUser, hasNextPlanValues, nextPlanManuallyDisabled])

  // Helper to convert expire field to needed schema using the same logic as other components
  function normalizeExpire(expire: Date | string | number | null | undefined, useUtcTimestamp: boolean = false): string | number | undefined {
    if (expire === '') return 0
    if (expire === undefined || expire === null) return undefined

    // For Date objects, convert to appropriate format
    if (expire instanceof Date) {
      return useUtcTimestamp ? Math.floor(expire.getTime() / 1000) : getLocalISOTime(expire)
    }

    // For strings and numbers, use the same dateUtils logic as other components
    try {
      const dayjsDate = dateUtils.toDayjs(expire)
      if (dayjsDate.isValid()) {
        return useUtcTimestamp ? Math.floor(dayjsDate.toDate().getTime() / 1000) : getLocalISOTime(dayjsDate.toDate())
      }
    } catch (error) {
      // If dayjs parsing fails, return undefined
    }

    return undefined
  }

  // Helper to clear group selection
  const clearGroups = () => form.setValue('group_ids', [])
  // Helper to clear template selection
  const clearTemplate = () => setSelectedTemplateId(null)

  // Helper to check if a template is selected in next plan
  const nextPlanTemplateSelected = !!form.watch('next_plan.user_template_id')

  // Update validateAllFields function
  const validateAllFields = (currentValues: any, touchedFields: any, isSubmit: boolean = false) => {
    try {
      // Special case for template mode
      if (selectedTemplateId) {
        // In template mode, only validate username
        form.clearErrors()
        if (!currentValues.username || currentValues.username.length < 3) {
          form.setError('username', {
            type: 'manual',
            message: t('validation.required', { field: t('username', { defaultValue: 'Username' }) }),
          })
          return false
        }
        return true
      }

      // Check for required fields in non-template mode
      if (isSubmit) {
        // Username validation
        if (!currentValues.username || currentValues.username.length < 3) {
          form.setError('username', {
            type: 'manual',
            message: t('validation.required', { field: t('username', { defaultValue: 'Username' }) }),
          })
          return false
        }

        // Groups validation (required for non-template mode)
        if (!currentValues.group_ids || !Array.isArray(currentValues.group_ids) || currentValues.group_ids.length === 0) {
          form.setError('group_ids', {
            type: 'manual',
            message: t('validation.required', { field: t('groups', { defaultValue: 'Groups' }) }),
          })
          return false
        }

        // Status validation
        if (!currentValues.status) {
          form.setError('status', {
            type: 'manual',
            message: t('validation.required', { field: t('status', { defaultValue: 'Status' }) }),
          })
          return false
        }

        // On hold specific validation
        if (currentValues.status === 'on_hold') {
          if (!currentValues.on_hold_expire_duration || currentValues.on_hold_expire_duration <= 0) {
            form.setError('on_hold_expire_duration', {
              type: 'manual',
              message: t('validation.required', { field: t('userDialog.onHoldExpireDuration', { defaultValue: 'On Hold Expire Duration' }) }),
            })
            return false
          }
        }
      }

      // Special case for Next Plan enabled - if Next Plan is enabled and no other fields are touched,
      // consider the form valid (Next Plan fields are optional)
      if (nextPlanEnabled && editingUser && !isSubmit) {
        const hasTouchedNonNextPlanFields = Object.keys(touchedFields).some(key => key !== 'next_plan' && !key.startsWith('next_plan.') && touchedFields[key])
        if (!hasTouchedNonNextPlanFields) {
          form.clearErrors()
          return true
        }
      }

      // Only validate fields that have been touched
      const fieldsToValidate = isSubmit
        ? currentValues
        : Object.keys(touchedFields).reduce((acc, key) => {
            if (touchedFields[key]) {
              acc[key] = currentValues[key]
            }
            return acc
          }, {} as any)

      // If no fields are touched, clear errors and return true
      if (!isSubmit && Object.keys(fieldsToValidate).length === 0) {
        form.clearErrors()
        return true
      }

      // Clear all previous errors before setting new ones
      form.clearErrors()

      // Select the appropriate schema based on template selection
      const schema = selectedTemplateId ? (editingUser ? templateModifySchema : templateUserSchema) : editingUser ? userEditSchema : userCreateSchema

      // Validate only touched fields using the selected schema
      if (isSubmit) {
        // On submit, validate the full schema
        schema.parse(fieldsToValidate)
      } else {
        // For non-submit validation, validate only touched fields
        schema.partial().parse(fieldsToValidate)
      }

      return true
    } catch (error: any) {
      // Handle validation errors from schema.partial().parse
      if (error?.errors) {
        // Clear all previous errors again just in case
        form.clearErrors()

        // Set new errors only for touched fields
        error.errors.forEach((err: any) => {
          const fieldName = err.path[0]
          if (fieldName && (isSubmit || touchedFields[fieldName])) {
            let message = err.message
            if (fieldName === 'group_ids' && message.includes('Required')) {
              // Check for required message for groups
              message = t('validation.required', { field: t('groups', { defaultValue: 'Groups' }) })
            } else if (fieldName === 'username' && message.includes('too short')) {
              message = t('validation.required', { field: t('username', { defaultValue: 'Username' }) })
            }
            if (fieldName === 'group_ids') {
              message = t('validation.required', { field: t('groups', { defaultValue: 'Groups' }) })
            }
            form.setError(fieldName as any, {
              type: 'manual',
              message,
            })
          }
        })
      }
      return false
    }
  }

  // Update template selection handlers to use number type
  const handleTemplateSelect = React.useCallback(
    (val: string) => {
      const currentValues = form.getValues()
      if (val === 'none' || (selectedTemplateId && String(selectedTemplateId) === val)) {
        setSelectedTemplateId(null)
        clearGroups()
      } else {
        setSelectedTemplateId(Number(val))
        clearGroups()
        // Clear group selection when template is selected
        form.setValue('group_ids', [])
        handleFieldChange('group_ids', [])
      }
      // Trigger validation after template selection changes
      const isValid = validateAllFields(currentValues, touchedFields)
      setIsFormValid(isValid)
    },
    [form, selectedTemplateId, touchedFields, handleFieldChange],
  )

  // Update the template mutation calls
  const handleTemplateMutation = React.useCallback(
    async (values: UseFormValues | UseEditFormValues) => {
      if (!selectedTemplateId) return

      // Validate template mode requirements
      if (!values.username || values.username.length < 3) {
        toast.error(t('validation.required', { field: t('username', { defaultValue: 'Username' }) }))
        return
      }

      setLoading(true)
      try {
        if (editingUser) {
          await modifyUserWithTemplateMutation.mutateAsync({
            username: values.username,
            data: {
              user_template_id: selectedTemplateId,
              note: values.note,
            },
          })
          toast.success(
            t('userDialog.userEdited', {
              username: values.username,
              defaultValue: 'User «{{name}}» has been updated successfully',
            }),
          )
        } else {
          await createUserFromTemplateMutation.mutateAsync({
            data: {
              user_template_id: selectedTemplateId,
              username: values.username,
              note: values.note || undefined,
            },
          })
          toast.success(
            t('userDialog.userCreated', {
              username: values.username,
              defaultValue: 'User «{{name}}» has been created successfully',
            }),
          )
        }

        onOpenChange(false)
        form.reset()
        setSelectedTemplateId(null)
        setActiveTab('groups')
      } catch (error: any) {
        const fields = ['username', 'note']
        handleError({ error, fields, form, contextKey: 'users' })
      } finally {
        setLoading(false)
      }
    },
    [editingUser, selectedTemplateId, form, onOpenChange, t],
  )

  const onSubmit = React.useCallback(
    async (values: UseFormValues | UseEditFormValues) => {
      try {
        form.clearErrors()

        // Handle template-based operations
        if (selectedTemplateId) {
          await handleTemplateMutation(values)
          return
        }

        // Regular create/edit flow
        if (!validateAllFields(values, touchedFields, true)) {
          // Show toast for validation errors
          const errors = form.formState.errors
          const errorFields = Object.keys(errors)

          if (errorFields.length > 0) {
            const firstError = errorFields[0]
            let errorMessage = t('validation.formHasErrors', { defaultValue: 'Please fix the form errors before submitting' })

            // Try to get the specific error message
            if (firstError === 'username' && errors.username?.message) {
              errorMessage = errors.username.message
            } else if (firstError === 'group_ids' && errors.group_ids?.message) {
              errorMessage = errors.group_ids.message
            } else if (firstError === 'status' && errors.status?.message) {
              errorMessage = errors.status.message
            } else if (firstError === 'on_hold_expire_duration' && errors.on_hold_expire_duration?.message) {
              errorMessage = errors.on_hold_expire_duration.message
            }

            toast.error(errorMessage)
          } else {
            // Check what's missing and show specific error
            const missingFields = []

            if (!values.username || values.username.length < 3) {
              missingFields.push(t('username', { defaultValue: 'Username' }))
            }

            if (!values.group_ids || !Array.isArray(values.group_ids) || values.group_ids.length === 0) {
              missingFields.push(t('groups', { defaultValue: 'Groups' }))
            }

            if (!values.status) {
              missingFields.push(t('status', { defaultValue: 'Status' }))
            }

            if (values.status === 'on_hold' && (!values.on_hold_expire_duration || values.on_hold_expire_duration <= 0)) {
              missingFields.push(t('userDialog.onHoldExpireDuration', { defaultValue: 'On Hold Expire Duration' }))
            }

            if (missingFields.length > 0) {
              toast.error(
                t('validation.missingFields', {
                  fields: missingFields.join(', '),
                  defaultValue: 'Please fill in the required fields: {{fields}}',
                }),
              )
            } else {
              toast.error(t('validation.formInvalid', { defaultValue: 'Form is invalid. Please check all required fields.' }))
            }
          }
          return
        }

        // Convert data to the right format before validation
        const preparedValues = {
          ...values,
          data_limit: typeof values.data_limit === 'string' ? parseFloat(values.data_limit) : values.data_limit,
          on_hold_expire_duration: values.on_hold_expire_duration
            ? typeof values.on_hold_expire_duration === 'string'
              ? parseInt(values.on_hold_expire_duration, 10)
              : values.on_hold_expire_duration
            : undefined,
          expire: status === 'on_hold' ? undefined : normalizeExpire(values.expire),
          on_hold_timeout: status === 'on_hold' ? normalizeExpire(values.on_hold_timeout) : undefined,
          group_ids: Array.isArray(values.group_ids) ? values.group_ids : [],
          status: values.status,
        }

        // Check if proxy settings are filled
        const hasProxySettings = values.proxy_settings && Object.values(values.proxy_settings).some(settings => settings && Object.values(settings).some(value => value !== undefined && value !== ''))

        setLoading(true)

        // Clean proxy settings to ensure proper enum values
        const cleanedProxySettings = hasProxySettings
          ? {
              ...values.proxy_settings,
              vless: values.proxy_settings?.vless
                ? {
                    ...values.proxy_settings.vless,
                    flow: values.proxy_settings.vless.flow || undefined,
                  }
                : undefined,
              shadowsocks: values.proxy_settings?.shadowsocks
                ? {
                    ...values.proxy_settings.shadowsocks,
                    method: values.proxy_settings.shadowsocks.method || undefined,
                  }
                : undefined,
            }
          : undefined

        let nextPlanData = undefined
        if (nextPlanEnabled) {
          const nextPlanFromValues = values.next_plan
          const hasValues = nextPlanFromValues && hasNextPlanValues(nextPlanFromValues)

          if (hasValues) {
            nextPlanData = { ...nextPlanFromValues }

            if (nextPlanData.user_template_id) {
              delete nextPlanData.data_limit
              delete nextPlanData.expire
            }
          } else {
            nextPlanData = {
              expire: 0,
              data_limit: 0,
            }
          }
        }

        const sendValues = {
          ...preparedValues,
          data_limit: gbToBytes(preparedValues.data_limit as any),
          expire: preparedValues.expire,
          ...(hasProxySettings ? { proxy_settings: cleanedProxySettings } : {}),
        }

        if (nextPlanEnabled) {
          sendValues.next_plan = nextPlanData
        }

        if (!hasProxySettings) {
          delete sendValues.proxy_settings
        }

        // Make API calls to the backend
        if (editingUser && editingUserId) {
          try {
            await modifyUserMutation.mutateAsync({
              username: sendValues.username,
              data: sendValues,
            })
            toast.success(
              t('userDialog.userEdited', {
                username: values.username,
                defaultValue: 'User «{{name}}» has been updated successfully',
              }),
            )
          } catch (error) {
            console.error('Modify user error:', error)
            throw error
          }
        } else {
          try {
            const createData = {
              ...sendValues,
              status: (sendValues.status === 'active' ? 'active' : sendValues.status) as 'active' | 'on_hold',
            }
            await createUserMutation.mutateAsync({
              data: createData,
            })
            toast.success(
              t('userDialog.userCreated', {
                username: values.username,
                defaultValue: 'User «{{name}}» has been created successfully',
              }),
            )
          } catch (error) {
            console.error('Create user error:', error)
            throw error
          }
        }

        onOpenChange(false)
        form.reset()
        setTouchedFields({})
        setActiveTab('groups')
        setSelectedTemplateId(null)
      } catch (error: any) {
        const fields = ['username', 'data_limit', 'expire', 'note', 'data_limit_reset_strategy', 'on_hold_expire_duration', 'on_hold_timeout', 'group_ids']
        handleError({ error, fields, form, contextKey: 'users' })
      } finally {
        setLoading(false)
      }
    },
    [editingUser, editingUserId, form, handleTemplateMutation, onOpenChange, selectedTemplateId, status, t, touchedFields],
  )

  // Helper for cryptographically secure random integer
  function getRandomInt(max: number): number {
    const array = new Uint32Array(1)
    window.crypto.getRandomValues(array)
    return array[0] % max
  }

  function generateUsername() {
    // Generate random 8-char string with only alphanumeric characters (no special chars)
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    let result = ''
    for (let i = 0; i < 8; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length))
    }
    return result
  }

  // Add this function after the generateUsername function
  function generatePassword(length: number = 24): string {
    const letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    const numbers = '0123456789'
    const special = '_'
    let password = ''

    // Ensure at least one underscore
    password += special

    // Fill the rest with letters and numbers
    for (let i = 1; i < length; i++) {
      const charSet = getRandomInt(10) < 7 ? letters : numbers // 70% letters, 30% numbers
      const randomIndex = getRandomInt(charSet.length)
      password += charSet[randomIndex]
    }

    // Shuffle the password to make it more random
    const arr = password.split('')
    for (let i = arr.length - 1; i > 0; i--) {
      const j = getRandomInt(i + 1)
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
    }
    return arr.join('')
  }

  // Add this function after the generatePassword function
  function generateProxySettings() {
    return {
      vmess: {
        id: uuidv4(),
      },
      vless: {
        id: uuidv4(),
        flow: '' as '' | 'xtls-rprx-vision' | undefined,
      },
      trojan: {
        password: generatePassword(),
      },
      shadowsocks: {
        password: generatePassword(),
      },
    }
  }

  // Add this button component after the username generate button
  const GenerateProxySettingsButton = () => (
    <Button
      size="icon"
      type="button"
      variant="ghost"
      onClick={() => {
        const newSettings = generateProxySettings()
        form.setValue('proxy_settings', newSettings)
        handleFieldChange('proxy_settings', newSettings)
      }}
      title="Generate proxy settings"
    >
      <RefreshCcw className="h-3 w-3" />
    </Button>
  )

  useEffect(() => {
    // Log form state when dialog opens
    if (isDialogOpen) {
      // Initialize on_hold_expire_duration if status is on_hold
      if (status === 'on_hold' && editingUser) {
        const currentDuration = form.getValues('on_hold_expire_duration')
        if (currentDuration === undefined || currentDuration === null || Number(currentDuration) === 0) {
          // Only set default if there's no value at all
          form.setValue('on_hold_expire_duration', 0)
        }
      }
    }
  }, [isDialogOpen, form, editingUser, status])

  // State for UUID version per field
  const [uuidVersions, setUuidVersions] = useState({
    vmess: 'v4',
    vless: 'v4',
    trojan: 'v4',
    shadowsocks: 'v4',
  })

  // Helper to generate UUID by version
  function generateUUID(version: string, value: string = ''): string {
    switch (version) {
      case 'v4':
        return uuidv4()
      case 'v5':
        return uuidv5(value || 'default', UUID_NAMESPACE)
      case 'v7':
        return uuidv7()
      default:
        return uuidv4()
    }
  }

  useEffect(() => {
    if (isDialogOpen && editingUser && dataLimitValue !== null && dataLimitValue !== undefined) {
      if (dataLimitValue > 0) {
        dataLimitInputRef.current = String(dataLimitValue)
      } else {
        dataLimitInputRef.current = ''
      }
    }
  }, [isDialogOpen, editingUser, dataLimitValue])

  useEffect(() => {
    if (isDialogOpen) {
      if (!editingUser) {
        form.setValue('proxy_settings', undefined)
        dataLimitInputRef.current = ''
        form.setValue('data_limit', 0)
        if (generalSettings) {
          form.setValue('proxy_settings.vless.flow', generalSettings.default_flow || '')
          const validMethods = ['aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305', 'xchacha20-poly1305'] as const
          const method = validMethods.find(m => m === generalSettings.default_method)
          if (method) {
            form.setValue('proxy_settings.shadowsocks.method', method)
          }
        }
      } else {
        const currentDataLimit = form.getValues('data_limit')
        if (currentDataLimit !== null && currentDataLimit !== undefined && currentDataLimit > 0) {
          dataLimitInputRef.current = String(currentDataLimit)
        } else {
          dataLimitInputRef.current = ''
        }
      }
    }
  }, [isDialogOpen, editingUser, generalSettings, form])

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleModalOpenChange}>
      <DialogContent className={`lg:min-w-[900px] ${editingUser ? 'h-full sm:h-auto' : 'h-auto'}`}>
        <DialogHeader>
          <DialogTitle className={`${dir === 'rtl' ? 'text-right' : 'text-left'}`}>
            {editingUser ? t('userDialog.editUser', { defaultValue: 'Edit User' }) : t('createUser', { defaultValue: 'Create User' })}
          </DialogTitle>
          <DialogDescription className="sr-only">{editingUser ? t('userDialog.editUser', { defaultValue: 'Edit User' }) : t('createUser', { defaultValue: 'Create User' })}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="flex w-full flex-col items-center justify-between gap-6 lg:flex-row lg:items-start lg:pb-8">
                <div className="w-full flex-[2] space-y-6">
                  <div className="flex w-full items-center justify-center gap-4">
                    {/* Hide these fields if a template is selected */}
                    {!selectedTemplateId && (
                      <div className={'flex w-full gap-4'}>
                        <FormField
                          control={form.control}
                          name="username"
                          render={({ field }) => {
                            const hasError = !!form.formState.errors.username
                            return (
                              <FormItem className="flex-1">
                                <FormLabel>{t('username', { defaultValue: 'Username' })}</FormLabel>
                                <FormControl>
                                  <div className="flex items-center gap-2">
                                    <div className="w-full">
                                      <Input
                                        placeholder={t('admins.enterUsername', { defaultValue: 'Enter username' })}
                                        {...field}
                                        value={field.value ?? ''}
                                        disabled={editingUser}
                                        isError={hasError}
                                        onChange={e => {
                                          field.onChange(e)
                                          handleFieldChange('username', e.target.value)
                                        }}
                                        onBlur={() => handleFieldBlur('username')}
                                      />
                                    </div>
                                    {!editingUser && (
                                      <Button
                                        size="icon"
                                        type="button"
                                        variant="ghost"
                                        onClick={e => {
                                          e.preventDefault()
                                          e.stopPropagation()
                                          const newUsername = generateUsername()
                                          field.onChange(newUsername)
                                          handleFieldChange('username', newUsername)
                                        }}
                                        title="Generate username"
                                      >
                                        <RefreshCcw className="h-3 w-3" />
                                      </Button>
                                    )}
                                  </div>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )
                          }}
                        />
                        {activeTab === 'groups' && (
                          <FormField
                            control={form.control}
                            name="status"
                            render={({ field }) => (
                              <FormItem className="w-1/3">
                                <FormLabel>{t('status', { defaultValue: 'Status' })}</FormLabel>
                                <FormControl>
                                  <StatusSelect
                                    value={field.value || ''}
                                    onValueChange={value => {
                                      field.onChange(value)
                                      handleFieldChange('status', value)
                                    }}
                                    placeholder={t('userDialog.selectStatus', { defaultValue: 'Select status' })}
                                  >
                                    <StatusSelectItem value="active">{t('status.active', { defaultValue: 'Active' })}</StatusSelectItem>
                                    {editingUser && <StatusSelectItem value="disabled">{t('status.disabled', { defaultValue: 'Disabled' })}</StatusSelectItem>}
                                    <StatusSelectItem value="on_hold">{t('status.on_hold', { defaultValue: 'On Hold' })}</StatusSelectItem>
                                  </StatusSelect>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        )}
                      </div>
                    )}
                    {/* If template is selected, only show username field */}
                    {selectedTemplateId && (
                      <FormField
                        control={form.control}
                        name="username"
                        render={({ field }) => {
                          const hasError = !!form.formState.errors.username
                          return (
                            <FormItem className="w-full flex-1">
                              <FormLabel>{t('username', { defaultValue: 'Username' })}</FormLabel>
                              <FormControl>
                                <div className="flex w-full flex-row items-center justify-between gap-4">
                                  <div className="w-full">
                                    <Input
                                      placeholder={t('admins.enterUsername', { defaultValue: 'Enter username' })}
                                      {...field}
                                      value={field.value ?? ''}
                                      disabled={editingUser}
                                      isError={hasError}
                                      onChange={e => {
                                        field.onChange(e)
                                        handleFieldChange('username', e.target.value)
                                      }}
                                      onBlur={() => handleFieldBlur('username')}
                                    />
                                  </div>
                                  {!editingUser && (
                                    <Button
                                      size="icon"
                                      type="button"
                                      variant="ghost"
                                      onClick={e => {
                                        e.preventDefault()
                                        e.stopPropagation()
                                        const newUsername = generateUsername()
                                        field.onChange(newUsername)
                                        handleFieldChange('username', newUsername)
                                      }}
                                      title="Generate username"
                                    >
                                      <RefreshCcw className="h-3 w-3" />
                                    </Button>
                                  )}
                                </div>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )
                        }}
                      />
                    )}
                  </div>
                  {/* Data limit and expire fields - show data_limit only when no template is selected */}
                  {activeTab === 'groups' && (
                    <div className="flex w-full flex-col gap-4 lg:flex-row lg:items-end">
                      {!selectedTemplateId && (
                        <>
                          <FormField
                            control={form.control}
                            name="data_limit"
                            render={({ field }) => {
                              if (dataLimitInputRef.current === '' && field.value !== null && field.value !== undefined && field.value > 0) {
                                dataLimitInputRef.current = String(field.value)
                              } else if ((field.value === null || field.value === undefined) && dataLimitInputRef.current !== '') {
                                dataLimitInputRef.current = ''
                              }

                              const displayValue =
                                dataLimitInputRef.current !== '' ? dataLimitInputRef.current : field.value !== null && field.value !== undefined && field.value > 0 ? String(field.value) : ''

                              return (
                                <FormItem className="relative h-full flex-1">
                                  <FormLabel>{t('userDialog.dataLimit', { defaultValue: 'Data Limit (GB)' })}</FormLabel>
                                  <FormControl>
                                    <Input
                                      type="text"
                                      inputMode="decimal"
                                      placeholder={t('userDialog.dataLimit', { defaultValue: 'e.g. 1' })}
                                      value={displayValue}
                                      onChange={e => {
                                        const rawValue = e.target.value.trim()

                                        dataLimitInputRef.current = rawValue

                                        if (rawValue === '') {
                                          field.onChange(0)
                                          handleFieldChange('data_limit', 0)
                                          return
                                        }

                                        const validNumberPattern = /^-?\d*\.?\d*$/
                                        if (validNumberPattern.test(rawValue)) {
                                          if (rawValue.endsWith('.') && rawValue.length > 1) {
                                            const prevValue = field.value !== null && field.value !== undefined ? field.value : 0
                                            field.onChange(prevValue)
                                            handleFieldChange('data_limit', prevValue)
                                          } else if (rawValue === '.') {
                                            field.onChange(0)
                                            handleFieldChange('data_limit', 0)
                                          } else {
                                            const numValue = parseFloat(rawValue)
                                            if (!isNaN(numValue) && numValue >= 0) {
                                              field.onChange(numValue)
                                              handleFieldChange('data_limit', numValue)
                                            }
                                          }
                                        }
                                      }}
                                      onBlur={() => {
                                        const rawValue = dataLimitInputRef.current.trim()
                                        if (rawValue === '' || rawValue === '.' || rawValue === '0') {
                                          dataLimitInputRef.current = ''
                                          field.onChange(0)
                                          handleFieldChange('data_limit', 0)
                                        } else {
                                          const numValue = parseFloat(rawValue)
                                          if (!isNaN(numValue) && numValue >= 0) {
                                            const finalValue = numValue
                                            dataLimitInputRef.current = finalValue > 0 ? String(finalValue) : ''
                                            field.onChange(finalValue)
                                            handleFieldChange('data_limit', finalValue)
                                          } else {
                                            dataLimitInputRef.current = ''
                                            field.onChange(0)
                                            handleFieldChange('data_limit', 0)
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
                          {form.watch('data_limit') !== undefined && form.watch('data_limit') !== null && Number(form.watch('data_limit')) > 0 && (
                            <FormField
                              control={form.control}
                              name="data_limit_reset_strategy"
                              render={({ field }) => (
                                <FormItem className="flex-1">
                                  <FormLabel>{t('userDialog.periodicUsageReset', { defaultValue: 'Periodic Usage Reset' })}</FormLabel>
                                  <Select
                                    onValueChange={value => {
                                      field.onChange(value)
                                      handleFieldChange('data_limit_reset_strategy', value)
                                    }}
                                    value={field.value || ''}
                                  >
                                    <FormControl>
                                      <SelectTrigger>
                                        <SelectValue placeholder={t('userDialog.resetStrategyNo', { defaultValue: 'No' })} />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      <SelectItem value="no_reset">{t('userDialog.resetStrategyNo', { defaultValue: 'No' })}</SelectItem>
                                      <SelectItem value="day">{t('userDialog.resetStrategyDaily', { defaultValue: 'Daily' })}</SelectItem>
                                      <SelectItem value="week">{t('userDialog.resetStrategyWeekly', { defaultValue: 'Weekly' })}</SelectItem>
                                      <SelectItem value="month">{t('userDialog.resetStrategyMonthly', { defaultValue: 'Monthly' })}</SelectItem>
                                      <SelectItem value="year">{t('userDialog.resetStrategyAnnually', { defaultValue: 'Annually' })}</SelectItem>
                                    </SelectContent>
                                  </Select>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          )}
                        </>
                      )}
                      <div className="flex h-full items-start gap-4 lg:w-52">
                        {status === 'on_hold' ? (
                          <FormField
                            control={form.control}
                            name="on_hold_expire_duration"
                            render={({ field }) => {
                              const hasError = !!form.formState.errors.on_hold_expire_duration
                              const fieldValue = field.value ? Math.round(field.value / (24 * 60 * 60)) : ''
                              const isZeroOrEmpty = fieldValue === 0 || fieldValue === ''
                              const isTouched = touchedFields['on_hold_expire_duration']

                              return (
                                <FormItem className="flex-1">
                                  <FormLabel>{t('userDialog.onHoldExpireDuration', { defaultValue: 'On Hold Expire Duration (days)' })}</FormLabel>
                                  <FormControl>
                                    <Input
                                      type="number"
                                      min="1"
                                      isError={hasError || (isTouched && isZeroOrEmpty)}
                                      placeholder={t('userDialog.onHoldExpireDurationPlaceholder', { defaultValue: 'e.g. 7' })}
                                      {...field}
                                      value={fieldValue ? fieldValue : ''}
                                      onChange={e => {
                                        // Allow empty string for deletion
                                        if (e.target.value === '') {
                                          field.onChange(0)
                                          handleFieldChange('on_hold_expire_duration', 0)
                                          // Mark field as touched to prevent auto-default
                                          setTouchedFields(prev => ({ ...prev, on_hold_expire_duration: true }))
                                        } else {
                                          const value = parseInt(e.target.value, 10)
                                          if (!isNaN(value) && value >= 0) {
                                            field.onChange(value ? value * (24 * 60 * 60) : 0)
                                            handleFieldChange('on_hold_expire_duration', value)
                                            // Mark field as touched
                                            setTouchedFields(prev => ({ ...prev, on_hold_expire_duration: true }))
                                          }
                                        }
                                      }}
                                      onBlur={() => {
                                        handleFieldBlur('on_hold_expire_duration')
                                        // Set validation error if value is 0 or empty
                                        if (fieldValue === 0 || fieldValue === '') {
                                          form.setError('on_hold_expire_duration', {
                                            type: 'manual',
                                            message: t('validation.required', { field: t('userDialog.onHoldExpireDuration', { defaultValue: 'On Hold Expire Duration' }) }),
                                          })
                                        } else {
                                          // Clear error if value is valid
                                          form.clearErrors('on_hold_expire_duration')
                                        }
                                      }}
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )
                            }}
                          />
                        ) : (
                          <FormField
                            control={form.control}
                            name="expire"
                            render={({ field }) => (
                              <ExpiryDateField
                                field={field}
                                displayDate={displayDate}
                                calendarOpen={expireCalendarOpen}
                                setCalendarOpen={setExpireCalendarOpen}
                                handleFieldChange={handleFieldChange}
                                label={t('userDialog.expiryDate', { defaultValue: 'Expire date' })}
                                fieldName="expire"
                              />
                            )}
                          />
                        )}
                      </div>
                    </div>
                  )}
                  {activeTab === 'groups' && status === 'on_hold' && (
                    <FormField
                      control={form.control}
                      name="on_hold_timeout"
                      render={({ field }) => (
                        <ExpiryDateField
                          field={field}
                          displayDate={onHoldDisplayDate}
                          calendarOpen={onHoldCalendarOpen}
                          setCalendarOpen={setOnHoldCalendarOpen}
                          handleFieldChange={handleFieldChange}
                          label={t('userDialog.timeOutDate', { defaultValue: 'Expire date' })}
                          fieldName="on_hold_timeout"
                        />
                      )}
                    />
                  )}
                  <FormField
                    control={form.control}
                    name="note"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('userDialog.note', { defaultValue: 'Note' })}</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder={t('userDialog.note', { defaultValue: 'Optional note' }) + '...'}
                            {...field}
                            rows={3}
                            onChange={e => {
                              field.onChange(e)
                              handleFieldChange('note', e.target.value)
                            }}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {/* Proxy Settings Accordion */}
                  {activeTab === 'groups' && (
                    <Accordion type="single" collapsible className="my-4 w-full">
                      <AccordionItem className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="proxySettings">
                        <AccordionTrigger>
                          <div className="flex items-center gap-2">
                            <Lock className="h-4 w-4" />
                            <span>{t('userDialog.proxySettingsAccordion')}</span>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-2">
                          <div className="mb-2 flex items-center justify-between">
                            <div className="text-xs text-muted-foreground">{t('userDialog.proxySettings.desc')}</div>
                            <GenerateProxySettingsButton />
                          </div>
                          {/* VMess */}
                          <FormField
                            control={form.control}
                            name="proxy_settings.vmess.id"
                            render={({ field, formState }) => {
                              const error = formState.errors.proxy_settings?.vmess?.id
                              return (
                                <FormItem className="mb-2">
                                  <FormLabel>
                                    {t('userDialog.proxySettings.vmess')} {t('userDialog.proxySettings.id')}
                                  </FormLabel>
                                  <FormControl>
                                    <div dir="ltr" className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                      <Input
                                        {...field}
                                        placeholder={t('userDialog.proxySettings.id')}
                                        onChange={e => {
                                          field.onChange(e)
                                          form.trigger('proxy_settings.vmess.id')
                                          handleFieldChange('proxy_settings.vmess.id', e.target.value)
                                        }}
                                      />
                                      <Select value={uuidVersions.vmess} onValueChange={val => setUuidVersions(v => ({ ...v, vmess: val }))}>
                                        <SelectTrigger className="w-[60px]">
                                          <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                          <SelectItem value="v4">v4</SelectItem>
                                          <SelectItem value="v5">v5</SelectItem>
                                          <SelectItem value="v7">v7</SelectItem>
                                        </SelectContent>
                                      </Select>
                                      <Button
                                        size="icon"
                                        type="button"
                                        variant="ghost"
                                        onClick={e => {
                                          e.preventDefault()
                                          e.stopPropagation()
                                          const newVal = generateUUID(uuidVersions.vmess, field.value)
                                          field.onChange(newVal)
                                          form.trigger('proxy_settings.vmess.id')
                                          handleFieldChange('proxy_settings.vmess.id', newVal)
                                        }}
                                        title="Generate UUID"
                                      >
                                        <RefreshCcw className="h-3 w-3" />
                                      </Button>
                                    </div>
                                  </FormControl>
                                  <FormMessage>{error?.message === 'Invalid uuid' && t('validation.invalidUuid', { defaultValue: 'Invalid UUID format' })}</FormMessage>
                                </FormItem>
                              )
                            }}
                          />
                          {/* VLESS */}
                          <FormField
                            control={form.control}
                            name="proxy_settings.vless.id"
                            render={({ field, formState }) => {
                              const error = formState.errors.proxy_settings?.vless?.id
                              return (
                                <FormItem className="mb-2">
                                  <FormLabel>
                                    {t('userDialog.proxySettings.vless')} {t('userDialog.proxySettings.id')}
                                  </FormLabel>
                                  <FormControl>
                                    <div dir="ltr" className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                      <Input
                                        {...field}
                                        placeholder={t('userDialog.proxySettings.id')}
                                        onChange={e => {
                                          field.onChange(e)
                                          form.trigger('proxy_settings.vless.id')
                                          handleFieldChange('proxy_settings.vless.id', e.target.value)
                                        }}
                                      />
                                      <Select value={uuidVersions.vless} onValueChange={val => setUuidVersions(v => ({ ...v, vless: val }))}>
                                        <SelectTrigger className="w-[60px]">
                                          <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                          <SelectItem value="v4">v4</SelectItem>
                                          <SelectItem value="v5">v5</SelectItem>
                                          <SelectItem value="v7">v7</SelectItem>
                                        </SelectContent>
                                      </Select>
                                      <Button
                                        size="icon"
                                        type="button"
                                        variant="ghost"
                                        onClick={e => {
                                          e.preventDefault()
                                          e.stopPropagation()
                                          const newVal = generateUUID(uuidVersions.vless, field.value)
                                          field.onChange(newVal)
                                          form.trigger('proxy_settings.vless.id')
                                          handleFieldChange('proxy_settings.vless.id', newVal)
                                        }}
                                        title="Generate UUID"
                                      >
                                        <RefreshCcw className="h-3 w-3" />
                                      </Button>
                                    </div>
                                  </FormControl>
                                  <FormMessage>{error?.message === 'Invalid uuid' && t('validation.invalidUuid', { defaultValue: 'Invalid UUID format' })}</FormMessage>
                                </FormItem>
                              )
                            }}
                          />
                          <FormField
                            control={form.control}
                            name="proxy_settings.vless.flow"
                            render={({ field }) => (
                              <FormItem className="mb-2">
                                <FormLabel>
                                  {t('userDialog.proxySettings.vless')} {t('userDialog.proxySettings.flow')}
                                </FormLabel>
                                <FormControl>
                                  <Select
                                    value={field.value ?? 'none'}
                                    onValueChange={val => {
                                      const flowValue = val === 'none' ? '' : val
                                      field.onChange(flowValue)
                                      handleFieldChange('proxy_settings.vless.flow', flowValue)
                                    }}
                                  >
                                    <SelectTrigger>
                                      <SelectValue placeholder={t('userDialog.proxySettings.flow')} />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="none">{t('userDialog.proxySettings.flow.none', { defaultValue: 'None' })}</SelectItem>
                                      <SelectItem value="xtls-rprx-vision">xtls-rprx-vision</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          {/* Trojan */}
                          <FormField
                            control={form.control}
                            name="proxy_settings.trojan.password"
                            render={({ field }) => (
                              <FormItem className="mb-2">
                                <FormLabel>
                                  {t('userDialog.proxySettings.trojan')} {t('userDialog.proxySettings.password')}
                                </FormLabel>
                                <FormControl>
                                  <div dir="ltr" className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                    <Input
                                      {...field}
                                      placeholder={t('userDialog.proxySettings.password')}
                                      onChange={e => {
                                        field.onChange(e)
                                        form.trigger('proxy_settings.trojan.password')
                                        handleFieldChange('proxy_settings.trojan.password', e.target.value)
                                      }}
                                    />
                                    <Button
                                      size="icon"
                                      type="button"
                                      variant="ghost"
                                      onClick={e => {
                                        e.preventDefault()
                                        e.stopPropagation()
                                        const newVal = generatePassword()
                                        field.onChange(newVal)
                                        form.trigger('proxy_settings.trojan.password')
                                        handleFieldChange('proxy_settings.trojan.password', newVal)
                                      }}
                                      title="Generate password"
                                    >
                                      <RefreshCcw className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          {/* Shadowsocks */}
                          <FormField
                            control={form.control}
                            name="proxy_settings.shadowsocks.password"
                            render={({ field }) => (
                              <FormItem className="mb-2 w-full">
                                <FormLabel>
                                  {t('userDialog.proxySettings.shadowsocks')} {t('userDialog.proxySettings.password')}
                                </FormLabel>
                                <FormControl>
                                  <div dir="ltr" className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                    <Input
                                      {...field}
                                      placeholder={t('userDialog.proxySettings.password')}
                                      onChange={e => {
                                        field.onChange(e)
                                        form.trigger('proxy_settings.shadowsocks.password')
                                        handleFieldChange('proxy_settings.shadowsocks.password', e.target.value)
                                      }}
                                    />
                                    <Button
                                      size="icon"
                                      type="button"
                                      variant="ghost"
                                      onClick={e => {
                                        e.preventDefault()
                                        e.stopPropagation()
                                        const newVal = generatePassword()
                                        field.onChange(newVal)
                                        form.trigger('proxy_settings.shadowsocks.password')
                                        handleFieldChange('proxy_settings.shadowsocks.password', newVal)
                                      }}
                                      title="Generate password"
                                    >
                                      <RefreshCcw className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="proxy_settings.shadowsocks.method"
                            render={({ field }) => (
                              <FormItem className="mb-2">
                                <FormLabel>
                                  {t('userDialog.proxySettings.shadowsocks')} {t('userDialog.proxySettings.method')}
                                </FormLabel>
                                <FormControl>
                                  <Select
                                    value={field.value ?? ''}
                                    onValueChange={val => {
                                      const methodValue = val || undefined
                                      field.onChange(methodValue)
                                      handleFieldChange('proxy_settings.shadowsocks.method', methodValue)
                                    }}
                                  >
                                    <SelectTrigger>
                                      <SelectValue placeholder={t('userDialog.proxySettings.method')} />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="aes-128-gcm">aes-128-gcm</SelectItem>
                                      <SelectItem value="aes-256-gcm">aes-256-gcm</SelectItem>
                                      <SelectItem value="chacha20-ietf-poly1305">chacha20-ietf-poly1305</SelectItem>
                                      <SelectItem value="xchacha20-poly1305">xchacha20-poly1305</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </AccordionContent>
                      </AccordionItem>
                    </Accordion>
                  )}
                  {/* Next Plan Section (toggleable) */}
                  {activeTab === 'groups' && editingUser && (
                    <div className="rounded-[--radius] border border-border p-4">
                      <div className="flex items-center justify-between">
                        <div
                          className="flex cursor-pointer items-center gap-2"
                          onClick={() => {
                            const newValue = !nextPlanEnabled
                            setNextPlanEnabled(newValue)
                            if (!newValue) {
                              setNextPlanManuallyDisabled(true)
                            } else {
                              setNextPlanManuallyDisabled(false)
                            }
                          }}
                        >
                          <ListStart className="h-4 w-4" />
                          <div>{t('userDialog.nextPlanTitle', { defaultValue: 'Next Plan' })}</div>
                        </div>
                        <Switch
                          checked={nextPlanEnabled}
                          onCheckedChange={value => {
                            setNextPlanEnabled(value)
                            if (!value) {
                              setNextPlanManuallyDisabled(true)
                            } else {
                              setNextPlanManuallyDisabled(false)
                            }
                            const currentValues = form.getValues()
                            const isValid = validateAllFields(currentValues, touchedFields)
                            setIsFormValid(isValid)
                          }}
                        />
                      </div>
                      {nextPlanEnabled && (
                        <div className="flex flex-col gap-4 py-4">
                          <FormField
                            control={form.control}
                            name="next_plan.user_template_id"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>{t('userDialog.nextPlanTemplateId', { defaultValue: 'Template' })}</FormLabel>
                                <FormControl>
                                  <Select
                                    value={field.value ? String(field.value) : 'none'}
                                    onValueChange={val => {
                                      if (val === 'none' || (field.value && String(field.value) === val)) {
                                        field.onChange(undefined)
                                        handleFieldChange('next_plan.user_template_id', undefined)
                                      } else {
                                        field.onChange(Number(val))
                                        handleFieldChange('next_plan.user_template_id', Number(val))
                                      }
                                    }}
                                  >
                                    <SelectTrigger>
                                      <SelectValue placeholder={t('userDialog.selectTemplatePlaceholder', { defaultValue: 'Choose a template' })} />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="none">---</SelectItem>
                                      {(templatesData || []).map((tpl: any) => (
                                        <SelectItem key={tpl.id} value={String(tpl.id)}>
                                          {tpl.name}
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          {/* Only show expire and data_limit if no template is selected */}
                          {!nextPlanTemplateSelected && (
                            <div className="flex gap-4">
                              <FormField
                                control={form.control}
                                name="next_plan.expire"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('userDialog.nextPlanExpire', { defaultValue: 'Expire' })}</FormLabel>
                                    <FormControl>
                                      <Input
                                        type="number"
                                        min="0"
                                        step="any"
                                        {...field}
                                        value={field.value ? dateUtils.secondsToDays(field.value) || '' : ''}
                                        onChange={e => {
                                          const days = e.target.value ? Number(e.target.value) : 0
                                          const seconds = dateUtils.daysToSeconds(days)
                                          field.onChange(seconds)
                                          handleFieldChange('next_plan.expire', seconds)
                                        }}
                                      />
                                    </FormControl>
                                    <span className="text-xs text-muted-foreground">{t('userDialog.days', { defaultValue: 'Days' })}</span>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                              <FormField
                                control={form.control}
                                name="next_plan.data_limit"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('userDialog.nextPlanDataLimit', { defaultValue: 'Data Limit' })}</FormLabel>
                                    <FormControl>
                                      <Input
                                        type="number"
                                        min="0"
                                        step="any"
                                        {...field}
                                        onChange={e => {
                                          const value = e.target.value ? Number(e.target.value) : 0
                                          // Convert GB to bytes (1 GB = 1024 * 1024 * 1024 bytes)
                                          const bytesValue = value ? value * 1024 * 1024 * 1024 : 0
                                          field.onChange(bytesValue)
                                          handleFieldChange('next_plan.data_limit', bytesValue)
                                        }}
                                        value={field.value ? Math.round(field.value / (1024 * 1024 * 1024)) : ''}
                                      />
                                    </FormControl>
                                    <span className="text-xs text-muted-foreground">GB</span>
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            </div>
                          )}
                          <div className="flex gap-8">
                            <FormField
                              control={form.control}
                              name="next_plan.add_remaining_traffic"
                              render={({ field }) => (
                                <FormItem className="flex w-full flex-row items-center justify-between">
                                  <FormLabel>{t('userDialog.nextPlanAddRemainingTraffic', { defaultValue: 'Add Remaining Traffic' })}</FormLabel>
                                  <Switch
                                    checked={!!field.value}
                                    onCheckedChange={value => {
                                      field.onChange(value)
                                      handleFieldChange('next_plan.add_remaining_traffic', value)
                                    }}
                                  />
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div className="h-full w-full flex-1 space-y-6">
                  <div className="w-full">
                    <div className="flex items-center border-b">
                      {tabs.map(tab => (
                        <button
                          key={tab.id}
                          onClick={() => setActiveTab(tab.id as typeof activeTab)}
                          className={`relative flex-1 px-3 py-2 text-sm font-medium transition-colors ${
                            activeTab === tab.id ? 'border-b-2 border-primary text-foreground' : 'text-muted-foreground hover:text-foreground'
                          }`}
                          type="button"
                        >
                          <div className="flex items-center justify-center gap-1.5">
                            <tab.icon className="h-4 w-4" />
                            <span>{t(tab.label)}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                    <div className="py-2">
                      {activeTab === 'templates' &&
                        (templatesLoading ? (
                          <div>{t('Loading...', { defaultValue: 'Loading...' })}</div>
                        ) : (
                          <div className="space-y-4 pt-4">
                            <FormLabel>{t('userDialog.selectTemplate', { defaultValue: 'Select Template' })}</FormLabel>
                            <Select value={selectedTemplateId ? String(selectedTemplateId) : 'none'} onValueChange={handleTemplateSelect}>
                              <SelectTrigger>
                                <SelectValue placeholder={t('userDialog.selectTemplatePlaceholder', { defaultValue: 'Choose a template' })} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="none">---</SelectItem>
                                {(templatesData || []).map((template: any) => (
                                  <SelectItem key={template.id} value={String(template.id)}>
                                    {template.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            {selectedTemplateId && (
                              <div className="text-sm text-muted-foreground">
                                {t('userDialog.selectedTemplates', {
                                  count: 1,
                                  defaultValue: '1 template selected',
                                })}
                              </div>
                            )}
                          </div>
                        ))}
                      {activeTab === 'groups' && (
                        <FormField
                          control={form.control}
                          name="group_ids"
                          render={({ field }) => (
                            <GroupsSelector
                              control={form.control}
                              name="group_ids"
                              onGroupsChange={groups => {
                                field.onChange(groups)
                                handleFieldChange('group_ids', groups)

                                // Clear template selection when groups are selected
                                if (groups.length > 0 && selectedTemplateId) {
                                  setSelectedTemplateId(null)
                                  clearTemplate()
                                }

                                // Trigger validation after group selection changes
                                const isValid = validateAllFields({ ...form.getValues(), group_ids: groups }, touchedFields)
                                setIsFormValid(isValid)
                              }}
                            />
                          )}
                        />
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
            {/* Cancel/Create buttons - always visible */}
            <div className="mt-4 flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={e => {
                  e.preventDefault()
                  e.stopPropagation()
                  onOpenChange(false)
                }}
              >
                {t('cancel', { defaultValue: 'Cancel' })}
              </Button>
              <LoaderButton
                type="submit"
                isLoading={loading}
                disabled={!isFormValid}
                loadingText={editingUser ? t('modifying') : t('creating')}
                onClick={e => {
                  if (!isFormValid) {
                    e.preventDefault()
                    e.stopPropagation()

                    // Check what's missing and show appropriate toast
                    const currentValues = form.getValues()

                    if (selectedTemplateId) {
                      // Template mode - only username required
                      if (!currentValues.username || currentValues.username.length < 3) {
                        toast.error(t('validation.required', { field: t('username', { defaultValue: 'Username' }) }))
                      }
                    } else {
                      // Regular mode - check required fields
                      const missingFields = []

                      if (!currentValues.username || currentValues.username.length < 3) {
                        missingFields.push(t('username', { defaultValue: 'Username' }))
                      }

                      if (!currentValues.group_ids || !Array.isArray(currentValues.group_ids) || currentValues.group_ids.length === 0) {
                        missingFields.push(t('groups', { defaultValue: 'Groups' }))
                      }

                      if (!currentValues.status) {
                        missingFields.push(t('status', { defaultValue: 'Status' }))
                      }

                      if (currentValues.status === 'on_hold' && (!currentValues.on_hold_expire_duration || currentValues.on_hold_expire_duration <= 0)) {
                        missingFields.push(t('userDialog.onHoldExpireDuration', { defaultValue: 'On Hold Expire Duration' }))
                      }

                      if (missingFields.length > 0) {
                        toast.error(
                          t('validation.missingFields', {
                            fields: missingFields.join(', '),
                            defaultValue: 'Please fill in the required fields: {{fields}}',
                          }),
                        )
                      } else {
                        toast.error(t('validation.formInvalid', { defaultValue: 'Form is invalid. Please check all fields.' }))
                      }
                    }
                  }
                }}
              >
                {editingUser ? t('modify', { defaultValue: 'Modify' }) : t('create', { defaultValue: 'Create' })}
              </LoaderButton>
            </div>
          </form>
        </Form>
      </DialogContent>
      {/* Subscription Clients Modal */}
    </Dialog>
  )
}
