import { DatePicker, type DatePickerAlign, type DatePickerSide } from '@/components/common/date-picker'
import { DecimalInput } from '@/components/common/decimal-input'
import GroupsSelector from '@/components/common/groups-selector'
import { TimeUnitSelect, TIME_UNIT_SECONDS, type TimeUnit } from '@/components/common/time-unit-select'
import UsageModal from '@/features/users/dialogs/usage-modal'
import UserAllIPsModal from '@/features/users/dialogs/user-all-ips-modal'
import { UserHwidsModal } from '@/features/users/dialogs/user-hwids-modal'
import { UserSubscriptionClientsModal } from '@/features/users/dialogs/user-subscription-clients-modal'
import { type UseEditFormValues, type UseFormValues, userCreateObjectSchema, userCreateSchema, userEditObjectSchema, userEditSchema } from '@/features/users/forms/user-form'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { cn } from '@/lib/utils'
import {
  getGeneralSettings,
  getGetGeneralSettingsQueryKey,
  getGetGroupsSimpleQueryKey,
  useCreateUser,
  useCreateUserFromTemplate,
  useGetGroupsSimple,
  useGetUserTemplatesSimple,
  useModifyUserById,
  useModifyUserWithTemplateById,
  useResetUserDataUsageById,
  useRevokeUserSubscriptionById,
  type UserResponse,
} from '@/service/api'
import { dateUtils, useRelativeExpiryDate } from '@/utils/dateFormatter'
import { normalizeDatePickerValueForSubmit, serializeDatePickerValue, toDatePickerDisplayDate } from '@/utils/datePickerUtils'
import { parseDateInput } from '@/utils/dateTimeParsing'
import { bytesToFormGigabytes, formatBytes, gbToBytes } from '@/utils/formatByte'
import { invalidateUserMetricsQueries, upsertUserInUsersCache } from '@/utils/usersCache'
import { generateWireGuardKeyPair, getWireGuardPublicKey } from '@/utils/wireguard'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CalendarPlus, ChevronDown, EllipsisVertical, Fingerprint, Info, Layers, Link2Off, ListStart, Lock, Network, PieChart, RefreshCcw, Group, Users, Pencil, UserRoundPlus } from 'lucide-react'
import React, { useEffect, useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { v4 as uuidv4 } from 'uuid'
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

// Add template validation schema
const templateUserSchema = z.object({
  username: z.string().min(3, 'validation.minLength').max(128, 'validation.maxLength'),
  note: z.string().optional(),
})

// Add template modification schema
const templateModifySchema = z.object({
  note: z.string().optional(),
  user_template_id: z.number(),
})

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
  popoverAlignDesktop,
  popoverSideDesktop,
}: {
  field: any
  displayDate: Date | null
  calendarOpen: boolean
  setCalendarOpen: (open: boolean) => void
  handleFieldChange: (field: string, value: any) => void
  label: string
  useUtcTimestamp?: boolean
  fieldName?: string
  popoverAlignDesktop?: DatePickerAlign
  popoverSideDesktop?: DatePickerSide
}) => {
  const { t } = useTranslation()
  const expireInfo = useRelativeExpiryDate(displayDate ? Math.floor(displayDate.getTime() / 1000) : null)
  const dir = useDirDetection()

  const handleDateChange = React.useCallback(
    (date: Date | undefined) => {
      if (date) {
        const value = serializeDatePickerValue(date, { useUtcTimestamp })
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
      const targetDate = parseDateInput(baseDate).add(days, 'day').toDate()
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
    <FormItem className="min-w-0 flex-1">
      <FormLabel>{label}</FormLabel>
      <div className="flex flex-col gap-2">
        <div dir="ltr" className="flex flex-wrap items-center gap-1 lg:hidden">
          {shortcuts.map(({ label, days }) => (
            <Button
              key={label}
              type="button"
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-foreground h-7 px-2.5 text-xs"
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
            popoverAlignDesktop={popoverAlignDesktop}
            popoverSideDesktop={popoverSideDesktop}
          />
          {displayDate && expireInfo?.time && (
            <p
              className={cn(
                fieldName !== 'on_hold_timeout' && 'lg:w-48',
                'text-muted-foreground absolute top-full right-0 mt-1 text-end text-xs whitespace-nowrap lg:overflow-hidden lg:text-ellipsis',
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
type StatusSelectItemProps = {
  value: string
  children: React.ReactNode
  onSelect?: (value: string) => void
}

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
      <PopoverContent className="w-(--radix-popover-trigger-width) p-1" align="start">
        {React.Children.map(children, child => {
          if (React.isValidElement<StatusSelectItemProps>(child) && typeof child.props.value === 'string') {
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

const StatusSelectItem = ({ value, children, onSelect }: StatusSelectItemProps) => {
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
      className="hover:bg-accent hover:text-accent-foreground relative flex w-full min-w-0 cursor-pointer items-center rounded-sm px-2 py-2 text-sm transition-colors outline-none select-none"
      onClick={() => onSelect?.(value)}
    >
      <span className="min-w-0 flex-1 truncate pr-2">{children}</span>
      <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
        <div className={`h-2 w-2 rounded-full ${getDotColor()}`} />
      </span>
    </div>
  )
}

function UserModal({ isDialogOpen, onOpenChange, form, editingUser, editingUserId, editingUserData, onSuccessCallback }: UserModalProps) {
  const { t, i18n } = useTranslation()
  const { admin } = useAdmin()
  const isSudo = admin?.is_sudo ?? false
  const dir = useDirDetection()
  const handleError = useDynamicErrorHandler()
  const [loading, setLoading] = useState(false)
  const status = form.watch('status')
  const [activeTab, setActiveTab] = useState<'groups' | 'templates'>('groups')
  const tabs = [
    { id: 'groups', label: 'groups', icon: Group },
    { id: 'templates', label: 'templates.title', icon: Layers },
  ]
  const [nextPlanEnabled, setNextPlanEnabled] = useState(false)
  const [nextPlanManuallyDisabled, setNextPlanManuallyDisabled] = useState(false)
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [expireCalendarOpen, setExpireCalendarOpen] = useState(false)
  const [onHoldCalendarOpen, setOnHoldCalendarOpen] = useState(false)
  const [isResetUsageDialogOpen, setResetUsageDialogOpen] = useState(false)
  const [isRevokeSubDialogOpen, setRevokeSubDialogOpen] = useState(false)
  const [isUserAllIPsModalOpen, setUserAllIPsModalOpen] = useState(false)
  const [isUsageModalOpen, setUsageModalOpen] = useState(false)
  const [isHwidsModalOpen, setHwidsModalOpen] = useState(false)
  const [isSubscriptionClientsModalOpen, setSubscriptionClientsModalOpen] = useState(false)
  const [isActionsMenuOpen, setActionsMenuOpen] = useState(false)
  const [onHoldExpireUnit, setOnHoldExpireUnit] = useState<TimeUnit>('days')

  // Watch next plan values directly for reactivity
  const nextPlanUserTemplateId = form.watch('next_plan.user_template_id')
  const nextPlanExpire = form.watch('next_plan.expire')
  const nextPlanDataLimit = form.watch('next_plan.data_limit')
  const nextPlanAddRemainingTraffic = form.watch('next_plan.add_remaining_traffic')

  // Check if template is selected (template_id exists and is not null/undefined)
  const hasTemplateSelected = !!nextPlanUserTemplateId

  const hasNextPlanData = React.useMemo(() => {
    const nextPlan = form.getValues('next_plan')

    if (!nextPlan || nextPlan === null || nextPlan === undefined) {
      return false
    }

    return (
      (nextPlan.user_template_id !== undefined && nextPlan.user_template_id !== null) ||
      (nextPlan.expire !== undefined && nextPlan.expire !== null) ||
      (nextPlan.data_limit !== undefined && nextPlan.data_limit !== null) ||
      (nextPlan.add_remaining_traffic !== undefined && nextPlan.add_remaining_traffic !== null)
    )
  }, [form, nextPlanUserTemplateId, nextPlanExpire, nextPlanDataLimit, nextPlanAddRemainingTraffic])

  useEffect(() => {
    if (!isDialogOpen) {
      // Reset when dialog closes
      setExpireCalendarOpen(false)
      setOnHoldCalendarOpen(false)
      setNextPlanEnabled(false)
      setNextPlanManuallyDisabled(false)
      setActionsMenuOpen(false)
    } else {
      setNextPlanManuallyDisabled(false)
      if (editingUser) {
        // Check both form values and editingUserData prop for next_plan
        // This ensures we catch the data even if form hasn't been populated yet
        const nextPlanFromForm = form.getValues('next_plan')
        const nextPlanFromData = editingUserData?.next_plan
        if (nextPlanFromData === null) {
          // Prevent stale form data from overriding explicit nulls.
          form.setValue('next_plan', undefined, { shouldValidate: false, shouldDirty: false })
        }

        // Use editingUserData if form doesn't have it yet, otherwise use form value
        const nextPlan = nextPlanFromData === null ? null : nextPlanFromForm !== null && nextPlanFromForm !== undefined ? nextPlanFromForm : nextPlanFromData

        const hasData =
          nextPlan !== null &&
          nextPlan !== undefined &&
          typeof nextPlan === 'object' &&
          ((nextPlan.user_template_id !== undefined && nextPlan.user_template_id !== null) ||
            (nextPlan.expire !== undefined && nextPlan.expire !== null) ||
            (nextPlan.data_limit !== undefined && nextPlan.data_limit !== null) ||
            (nextPlan.add_remaining_traffic !== undefined && nextPlan.add_remaining_traffic !== null))
        setNextPlanEnabled(!!hasData)
      } else {
        // For create mode, always start with switch off
        setNextPlanEnabled(false)
      }
    }
  }, [isDialogOpen, editingUser, form, editingUserData])
  const [touchedFields, setTouchedFields] = useState<Record<string, boolean>>({})
  const [isFormValid, setIsFormValid] = useState(false)
  const previousStatusRef = React.useRef(status)

  const handleModalOpenChange = React.useCallback(
    (open: boolean) => {
      if (!open) {
        // Only reset form if not editing (for create mode)
        // When editing, parent component will repopulate the form
        if (!editingUser) {
          form.reset()
          // Ensure next_plan is cleared in create mode
          form.setValue('next_plan', undefined)
        } else {
          // When editing, clear next_plan if switch was manually disabled
          if (!nextPlanEnabled) {
            form.setValue('next_plan', undefined)
          }
        }
        setTouchedFields({})
        setIsFormValid(false)
        setActiveTab('groups')
        setSelectedTemplateId(null)
        setNextPlanEnabled(false)
        setNextPlanManuallyDisabled(false)
        setOnHoldExpireUnit('days')
      }
      onOpenChange(open)
    },
    [form, onOpenChange, editingUser, nextPlanEnabled],
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

  const displayDate = toDatePickerDisplayDate(expireValue)
  const onHoldDisplayDate = toDatePickerDisplayDate(onHoldValue)

  // Query client for data refetching
  const queryClient = useQueryClient()

  // Fetch lightweight templates for selector tabs without caching
  const { data: templatesData, isLoading: templatesLoading } = useGetUserTemplatesSimple(
    { all: true },
    {
      query: {
        staleTime: 0,
        gcTime: 0,
        refetchOnMount: true,
        refetchOnReconnect: false,
        enabled: isDialogOpen,
      },
    },
  )
  const templateOptions = templatesData?.templates || []

  // Prefetch lightweight groups while modal is open so the Groups tab can render immediately.
  useGetGroupsSimple(
    { all: true },
    {
      query: {
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
        refetchOnWindowFocus: true,
        refetchOnMount: true,
        refetchOnReconnect: true,
        enabled: isDialogOpen,
      },
    },
  )

  const { data: generalSettings } = useQuery({
    queryKey: getGetGeneralSettingsQueryKey(),
    queryFn: () => getGeneralSettings(),
    enabled: isDialogOpen,
    refetchOnMount: true,
  })

  const syncUserCacheFromApiResponse = (user: UserResponse, options?: { allowInsert?: boolean; notifySuccessCallback?: boolean }) => {
    upsertUserInUsersCache(queryClient, user, { allowInsert: options?.allowInsert ?? false })
    invalidateUserMetricsQueries(queryClient)
    if (options?.notifySuccessCallback) {
      onSuccessCallback?.(user)
    }
  }

  const createUserMutation = useCreateUser({
    mutation: {
      onSuccess: data => syncUserCacheFromApiResponse(data, { allowInsert: true, notifySuccessCallback: true }),
    },
  })
  const modifyUserMutation = useModifyUserById({
    mutation: {
      onSuccess: data => syncUserCacheFromApiResponse(data, { allowInsert: true, notifySuccessCallback: true }),
    },
  })
  const createUserFromTemplateMutation = useCreateUserFromTemplate({
    mutation: {
      onSuccess: data => syncUserCacheFromApiResponse(data, { allowInsert: true, notifySuccessCallback: true }),
    },
  })

  // Add the mutation hook at the top with other mutations
  const modifyUserWithTemplateMutation = useModifyUserWithTemplateById({
    mutation: {
      onSuccess: data => syncUserCacheFromApiResponse(data, { allowInsert: true, notifySuccessCallback: true }),
    },
  })
  const resetUserDataUsageMutation = useResetUserDataUsageById({
    mutation: {
      onSuccess: updatedUser => {
        if (updatedUser) {
          syncUserCacheFromApiResponse(updatedUser)
        }
      },
    },
  })
  const revokeUserSubscriptionMutation = useRevokeUserSubscriptionById({
    mutation: {
      onSuccess: updatedUser => {
        if (updatedUser) {
          syncUserCacheFromApiResponse(updatedUser)
        }
      },
    },
  })

  useEffect(() => {
    // When the dialog closes, reset errors
    if (!isDialogOpen) {
      form.clearErrors()
    }
  }, [isDialogOpen, form])

  useEffect(() => {
    if (!isDialogOpen) return
    queryClient.invalidateQueries({
      queryKey: getGetGroupsSimpleQueryKey({ all: true }),
    })
  }, [isDialogOpen, queryClient])

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
    const previousStatus = previousStatusRef.current

    if (status === 'on_hold') {
      form.setValue('expire', undefined)
      form.clearErrors('expire')
    } else {
      if (previousStatus === 'on_hold') {
        form.setValue('expire', undefined)
        form.clearErrors('expire')
        setExpireCalendarOpen(false)
      }
      form.setValue('on_hold_expire_duration', undefined)
      form.clearErrors('on_hold_expire_duration')
      form.setValue('on_hold_timeout', undefined)
      form.clearErrors('on_hold_timeout')
    }

    previousStatusRef.current = status
  }, [status, form])

  useEffect(() => {
    if (!nextPlanEnabled) {
      const currentNextPlan = form.getValues('next_plan')
      if (currentNextPlan !== null && currentNextPlan !== undefined) {
        form.setValue('next_plan', undefined, { shouldValidate: false, shouldDirty: false })
        handleFieldChange('next_plan', undefined)
      }
    } else {
      const currentNextPlan = form.getValues('next_plan')
      if (currentNextPlan === null || currentNextPlan === undefined) {
        form.setValue(
          'next_plan',
          {
            expire: 0,
            data_limit: 0,
            add_remaining_traffic: false,
          },
          { shouldValidate: false, shouldDirty: false },
        )
      } else {
        if (!currentNextPlan.user_template_id) {
          const updatedPlan = {
            ...currentNextPlan,
            expire: currentNextPlan.expire ?? 0,
            data_limit: currentNextPlan.data_limit ?? 0,
            add_remaining_traffic: currentNextPlan.add_remaining_traffic ?? false,
          }
          form.setValue('next_plan', updatedPlan, { shouldValidate: false, shouldDirty: false })
        }
      }
      setNextPlanManuallyDisabled(false)
    }
  }, [nextPlanEnabled, form, handleFieldChange])

  useEffect(() => {
    if (!isDialogOpen || !editingUser) return

    // Check both form values and editingUserData prop for next_plan
    const nextPlanFromForm = form.getValues('next_plan')
    const nextPlanFromData = editingUserData?.next_plan

    // Use editingUserData if form doesn't have it yet, otherwise use form value
    const nextPlan = nextPlanFromForm !== null && nextPlanFromForm !== undefined ? nextPlanFromForm : nextPlanFromData

    const hasDataFromForm =
      nextPlan !== null &&
      nextPlan !== undefined &&
      typeof nextPlan === 'object' &&
      ((nextPlan.user_template_id !== undefined && nextPlan.user_template_id !== null) ||
        (nextPlan.expire !== undefined && nextPlan.expire !== null) ||
        (nextPlan.data_limit !== undefined && nextPlan.data_limit !== null) ||
        (nextPlan.add_remaining_traffic !== undefined && nextPlan.add_remaining_traffic !== null))

    const hasData = hasDataFromForm

    if (!hasData && nextPlanEnabled && !nextPlanManuallyDisabled) {
      setNextPlanEnabled(false)
    } else if (hasData && !nextPlanEnabled && !nextPlanManuallyDisabled) {
      setNextPlanEnabled(true)
      setNextPlanManuallyDisabled(false)
    }
  }, [isDialogOpen, editingUser, hasNextPlanData, nextPlanManuallyDisabled, form, nextPlanUserTemplateId, nextPlanExpire, nextPlanDataLimit, nextPlanAddRemainingTraffic, editingUserData])

  // Helper to clear group selection
  const clearGroups = () => form.setValue('group_ids', [])
  // Helper to clear template selection
  const clearTemplate = () => setSelectedTemplateId(null)

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
        schema.parse(fieldsToValidate)
      } else {
        // ZodEffects from .superRefine() has no .partial(); use base object schemas for touched-field validation
        if (selectedTemplateId) {
          ;(editingUser ? templateModifySchema : templateUserSchema).partial().parse(fieldsToValidate)
        } else {
          ;(editingUser ? userEditObjectSchema : userCreateObjectSchema).partial().parse(fieldsToValidate)
        }
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
            } else if (fieldName === 'on_hold_expire_duration') {
              message = t('validation.required', { field: t('templates.expire') })
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
      if (editingUser && !editingUserId) return

      // Validate template mode requirements
      if (!values.username || values.username.length < 3) {
        toast.error(t('validation.required', { field: t('username', { defaultValue: 'Username' }) }))
        return
      }

      setLoading(true)
      try {
        if (editingUser && editingUserId) {
          await modifyUserWithTemplateMutation.mutateAsync({
            userId: editingUserId,
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

            if (values.status === 'on_hold' && (!values.on_hold_expire_duration || !Number.isFinite(Number(values.on_hold_expire_duration)) || Number(values.on_hold_expire_duration) <= 0)) {
              missingFields.push(t('templates.expire'))
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
        // Exclude next_plan from preparedValues - it will be handled separately
        const { next_plan, ...valuesWithoutNextPlan } = values
        const preparedValues = {
          ...valuesWithoutNextPlan,
          data_limit: typeof values.data_limit === 'string' ? parseFloat(values.data_limit) : values.data_limit,
          hwid_limit: typeof values.hwid_limit === 'string' ? parseFloat(values.hwid_limit) : values.hwid_limit,
          on_hold_expire_duration:
            status === 'on_hold' && values.on_hold_expire_duration
              ? typeof values.on_hold_expire_duration === 'string'
                ? parseFloat(values.on_hold_expire_duration)
                : values.on_hold_expire_duration
              : undefined,
          expire: status === 'on_hold' ? undefined : normalizeDatePickerValueForSubmit(values.expire),
          on_hold_timeout: status === 'on_hold' ? normalizeDatePickerValueForSubmit(values.on_hold_timeout) : undefined,
          group_ids: Array.isArray(values.group_ids) ? values.group_ids : [],
          status: values.status,
        }

        setLoading(true)

        // Clean proxy settings to ensure proper enum values
        const cleanedProxySettings = cleanProxySettings(values.proxy_settings)
        const hasProxySettings = !!cleanedProxySettings

        const normalizedDataLimitGb = Number(preparedValues.data_limit ?? 0)
        const hasDataLimit = Number.isFinite(normalizedDataLimitGb) && normalizedDataLimitGb > 0

        // Prepare next plan data
        const sendValues: any = {
          ...preparedValues,
          data_limit: gbToBytes(normalizedDataLimitGb as any),
          hwid_limit: preparedValues.hwid_limit == null ? null : Number.isFinite(Number(preparedValues.hwid_limit)) ? Math.round(Number(preparedValues.hwid_limit)) : null,
          data_limit_reset_strategy: hasDataLimit ? preparedValues.data_limit_reset_strategy : 'no_reset',
          expire: preparedValues.expire,
          ...(hasProxySettings ? { proxy_settings: cleanedProxySettings } : {}),
        }

        // Handle next_plan based on switch state
        if (nextPlanEnabled) {
          // Switch is ON - always send next_plan with defaults or existing data
          const nextPlan = values.next_plan || form.getValues('next_plan') || {}

          if (nextPlan.user_template_id) {
            // Template selected - include numeric fields to avoid backend nulls in next_plan.
            sendValues.next_plan = {
              user_template_id: nextPlan.user_template_id,
              expire: 0,
              data_limit: 0,
              add_remaining_traffic: nextPlan.add_remaining_traffic ?? false,
            }
          } else {
            // No template - send expire and data_limit with defaults (integers; GB→bytes must not send floats)
            sendValues.next_plan = {
              expire: Math.round(Number(nextPlan.expire ?? 0)),
              data_limit: Math.round(Number(nextPlan.data_limit ?? 0)),
              add_remaining_traffic: nextPlan.add_remaining_traffic ?? false,
            }
          }
        } else {
          // Switch is OFF - send null
          sendValues.next_plan = null
        }

        if (!hasProxySettings) {
          delete sendValues.proxy_settings
        }

        // Make API calls to the backend
        if (editingUser && editingUserId) {
          try {
            await modifyUserMutation.mutateAsync({
              userId: editingUserId,
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
        const fields = ['username', 'data_limit', 'hwid_limit', 'expire', 'note', 'data_limit_reset_strategy', 'on_hold_expire_duration', 'on_hold_timeout', 'group_ids']
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
      },
      trojan: {
        password: generatePassword(),
      },
      shadowsocks: {
        password: generatePassword(),
      },
    }
  }

  const generateWireGuardProxySettings = React.useCallback(() => {
    const keyPair = generateWireGuardKeyPair()
    form.setValue('proxy_settings.wireguard.private_key', keyPair.privateKey, { shouldDirty: true, shouldValidate: true })
    form.setValue('proxy_settings.wireguard.public_key', keyPair.publicKey, { shouldDirty: true, shouldValidate: true })
    form.trigger(['proxy_settings.wireguard.private_key', 'proxy_settings.wireguard.public_key'])
    handleFieldChange('proxy_settings.wireguard.private_key', keyPair.privateKey)
    handleFieldChange('proxy_settings.wireguard.public_key', keyPair.publicKey)
    toast.success(t('userDialog.proxySettings.wireguardGenerated', { defaultValue: 'WireGuard keypair generated' }))
  }, [form, handleFieldChange, t])

  const syncWireGuardPublicKey = React.useCallback(
    (privateKey: string) => {
      const publicKey = getWireGuardPublicKey(privateKey)
      form.setValue('proxy_settings.wireguard.public_key', publicKey, { shouldDirty: true, shouldValidate: true })
      handleFieldChange('proxy_settings.wireguard.public_key', publicKey)
    },
    [form, handleFieldChange],
  )

  const parseWireGuardPeerIps = React.useCallback((value: string) => {
    return value.split('\n')
  }, [])

  const hasMeaningfulProxyValue = React.useCallback((value: unknown): boolean => {
    if (Array.isArray(value)) {
      return value.some(item => hasMeaningfulProxyValue(item))
    }
    if (value && typeof value === 'object') {
      return Object.values(value).some(item => hasMeaningfulProxyValue(item))
    }
    return value !== undefined && value !== null && value !== ''
  }, [])

  const cleanProxySettings = React.useCallback(
    (proxySettings: any) => {
      if (!proxySettings) return undefined

      const cleanedSettings = Object.entries(proxySettings).reduce(
        (acc, [protocol, settings]) => {
          if (!settings || typeof settings !== 'object') {
            return acc
          }

          const cleanedProtocolSettings = Object.entries(settings as Record<string, unknown>).reduce(
            (protocolAcc, [key, value]) => {
              if (Array.isArray(value)) {
                const cleanedList = value
                  .flatMap(item => {
                    if (typeof item !== 'string') {
                      return [item]
                    }
                    if (protocol === 'wireguard' && key === 'peer_ips') {
                      return item.split(',')
                    }
                    return [item]
                  })
                  .map(item => (typeof item === 'string' ? item.trim() : item))
                  .filter(item => hasMeaningfulProxyValue(item))

                if (cleanedList.length > 0) {
                  protocolAcc[key] = cleanedList
                }
                return protocolAcc
              }

              if (typeof value === 'string') {
                const trimmedValue = value.trim()
                if (trimmedValue) {
                  protocolAcc[key] = trimmedValue
                }
                return protocolAcc
              }

              if (value !== undefined && value !== null) {
                protocolAcc[key] = value
              }

              return protocolAcc
            },
            {} as Record<string, unknown>,
          )

          if (protocol === 'shadowsocks' && !cleanedProtocolSettings.method) {
            delete cleanedProtocolSettings.method
          }

          if (Object.keys(cleanedProtocolSettings).length > 0) {
            acc[protocol] = cleanedProtocolSettings
          }
          return acc
        },
        {} as Record<string, Record<string, unknown>>,
      )

      return Object.keys(cleanedSettings).length > 0 ? cleanedSettings : undefined
    },
    [hasMeaningfulProxyValue],
  )

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

  const currentUsername = editingUserData?.username || form.getValues('username')
  const currentUserId = editingUserData?.id || editingUserId
  const isPersianLocale = i18n.language?.toLowerCase().startsWith('fa')
  const formatMetaDate = React.useCallback(
    (value?: string | number | null) => {
      if (!value) return ''
      const parsed = parseDateInput(value)
      if (!parsed.isValid()) return ''
      const date = parsed.toDate()
      const locale = isPersianLocale ? 'fa-IR' : 'en-US'
      return (
        date.toLocaleDateString(locale, {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
        }) +
        ' ' +
        date.toLocaleTimeString(locale, {
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })
      )
    },
    [isPersianLocale],
  )

  const createdAtText = React.useMemo(() => {
    return formatMetaDate(editingUserData?.created_at)
  }, [editingUserData?.created_at, formatMetaDate])

  const editedAtText = React.useMemo(() => {
    return formatMetaDate(editingUserData?.edit_at)
  }, [editingUserData?.edit_at, formatMetaDate])

  const confirmResetUsage = async () => {
    if (!currentUserId || !currentUsername) return
    try {
      await resetUserDataUsageMutation.mutateAsync({ userId: currentUserId })
      toast.success(t('usersTable.resetUsageSuccess', { name: currentUsername }))
      setResetUsageDialogOpen(false)
    } catch (error: any) {
      toast.error(t('usersTable.resetUsageFailed', { name: currentUsername, error: error?.message || '' }))
    }
  }

  const confirmRevokeSubscription = async () => {
    if (!currentUserId || !currentUsername) return
    try {
      await revokeUserSubscriptionMutation.mutateAsync({ userId: currentUserId })
      toast.success(t('userDialog.revokeSubSuccess', { name: currentUsername }))
      setRevokeSubDialogOpen(false)
    } catch (error: any) {
      toast.error(t('revokeUserSub.error', { name: currentUsername, error: error?.message || '' }))
    }
  }

  const renderUserMetaPanel = (extraClassName?: string) => {
    if (!editingUser) return null

    return (
      <div className={cn('mt-3 space-y-3', extraClassName)}>
        <Accordion type="multiple" className="w-full">
          <AccordionItem value="meta-details" className="bg-background mt-2 rounded-sm border px-2">
            <AccordionTrigger className="text-muted-foreground py-2 text-xs font-medium tracking-wide uppercase hover:no-underline">
              <span className="flex items-center gap-1.5">
                <Info className="h-3.5 w-3.5" />
                {t('details', { defaultValue: 'Details' })}
              </span>
            </AccordionTrigger>
            <AccordionContent className="pb-2">
              <div className="bg-background space-y-1.5 rounded-md py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground flex items-center gap-1.5">
                    <CalendarPlus className="h-3.5 w-3.5" />
                    {t('createdAt', { defaultValue: 'Created at' })}
                  </span>
                  <span dir="ltr" className="text-right">
                    {createdAtText}
                  </span>
                </div>
                {editedAtText && (
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground flex items-center gap-1.5">
                      <CalendarClock className="h-3.5 w-3.5" />
                      {t('editedAt', { defaultValue: 'Edited at' })}
                    </span>
                    <span dir="ltr" className="text-right">
                      {editedAtText}
                    </span>
                  </div>
                )}
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </div>
    )
  }

  useEffect(() => {
    if (isDialogOpen) {
      if (!editingUser) {
        form.setValue('proxy_settings', undefined)
        form.setValue('data_limit', 0)
        if (generalSettings) {
          const validMethods = ['aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305', 'xchacha20-poly1305'] as const
          const method = validMethods.find(m => m === generalSettings.default_method)
          if (method) {
            form.setValue('proxy_settings.shadowsocks.method', method)
          }
        }
      }
    }
  }, [isDialogOpen, editingUser, generalSettings, form])

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleModalOpenChange}>
      <DialogContent className={`h-auto lg:min-w-[900px]`}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingUser ? <Pencil className="h-5 w-5" /> : <UserRoundPlus className="h-5 w-5" />}
            <span>{editingUser ? t('userDialog.editUser', { defaultValue: 'Edit User' }) : t('createUser', { defaultValue: 'Create User' })}</span>
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
                    <div className="flex w-full flex-col gap-4">
                      {(() => {
                        const dataLimitValue = form.watch('data_limit')
                        const showResetStrategy =
                          !selectedTemplateId && dataLimitValue !== undefined && dataLimitValue !== null && Number(dataLimitValue) > 0
                        return (
                          <div className={cn('flex w-full flex-col gap-4 lg:flex-row lg:items-start')}>
                            {!selectedTemplateId && (
                              <FormField
                                control={form.control}
                                name="data_limit"
                                render={({ field }) => (
                                  <FormItem className={cn('relative h-full min-w-0', showResetStrategy ? 'flex-1' : 'flex-1')}>
                                    <FormLabel>{t('userDialog.dataLimit', { defaultValue: 'Data Limit (GB)' })}</FormLabel>
                                    <FormControl>
                                      <DecimalInput
                                        placeholder={t('userDialog.dataLimit', { defaultValue: 'e.g. 1' })}
                                        value={field.value}
                                        emptyValue={0}
                                        zeroValue={0}
                                        onValueChange={value => {
                                          const nextValue = value ?? 0
                                          field.onChange(nextValue)
                                          handleFieldChange('data_limit', nextValue)
                                        }}
                                      />
                                    </FormControl>
                                    {field.value !== null && field.value !== undefined && field.value > 0 && field.value < 1 && (
                                      <p dir="ltr" className="text-muted-foreground absolute top-full right-0 mt-1 text-end text-xs">
                                        {formatBytes(Math.round(field.value * 1024 * 1024 * 1024))}
                                      </p>
                                    )}
                                    <FormMessage />
                                  </FormItem>
                                )}
                              />
                            )}
                            {showResetStrategy && (
                              <FormField
                                control={form.control}
                                name="data_limit_reset_strategy"
                                render={({ field }) => (
                                  <FormItem className="min-w-0">
                                    <FormLabel className="leading-tight">{t('userDialog.periodicUsageReset', { defaultValue: 'Periodic Usage Reset' })}</FormLabel>
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
                            <div className={cn('flex h-full min-w-0 items-start gap-4', showResetStrategy ? 'flex-1' : 'w-full lg:w-3/8')}>
                              {status === 'on_hold' ? (
                                <FormField
                                  control={form.control}
                                  name="on_hold_expire_duration"
                                  render={({ field }) => {
                                    const unitSeconds = TIME_UNIT_SECONDS[onHoldExpireUnit]

                                    return (
                                      <FormItem className="min-w-0 flex-1">
                                        <FormLabel className="text-left">{t('templates.expire')}</FormLabel>
                                        <FormControl>
                                          <div className="relative" dir="ltr">
                                            <DecimalInput
                                              placeholder={t('templates.expire')}
                                              value={field.value}
                                              emptyValue={0}
                                              zeroValue={0}
                                              toDisplayValue={value => value / unitSeconds}
                                              toValue={displayValue => displayValue * unitSeconds}
                                              onValueChange={value => {
                                                const nextValue = value ?? 0
                                                field.onChange(nextValue)
                                                handleFieldChange('on_hold_expire_duration', nextValue)
                                                void form.trigger('on_hold_expire_duration')
                                              }}
                                              className={cn(dir === 'rtl' ? 'pl-20' : 'pr-20')}
                                            />
                                            <TimeUnitSelect
                                              value={onHoldExpireUnit}
                                              onValueChange={setOnHoldExpireUnit}
                                              triggerClassName={cn(
                                                'absolute top-0 h-full w-20 rounded-none border-y-0 focus:ring-0 focus:ring-offset-0',
                                                dir === 'rtl' ? 'left-0 border-l-0' : 'right-0 border-r-0',
                                              )}
                                            />
                                          </div>
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
                        )
                      })()}
                      {!selectedTemplateId && (
                        <FormField
                          control={form.control}
                          name="hwid_limit"
                          render={({ field }) => (
                            <FormItem className="relative w-full min-w-0">
                              <FormLabel>{t('userDialog.hwidLimit', { defaultValue: 'HWID Limit' })}</FormLabel>
                              <FormControl>
                                <DecimalInput
                                  placeholder={t('userDialog.hwidLimitPlaceholder', { defaultValue: 'Empty for default, 0 for unlimited' })}
                                  value={field.value}
                                  emptyValue={undefined}
                                  zeroValue={0}
                                  keepZeroOnBlur
                                  normalizeDisplayValueOnBlur={Math.floor}
                                  onValueChange={value => {
                                    field.onChange(value)
                                    handleFieldChange('hwid_limit', value)
                                  }}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )}
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
                          label={t('userDialog.timeOutDate', { defaultValue: 'Hold Until' })}
                          fieldName="on_hold_timeout"
                          popoverAlignDesktop="start"
                          popoverSideDesktop={dir === 'rtl' ? 'left' : 'right'}
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
                            <div className="text-muted-foreground text-xs">{t('userDialog.proxySettings.desc')}</div>
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
                                      <Button
                                        size="icon"
                                        type="button"
                                        variant="ghost"
                                        onClick={e => {
                                          e.preventDefault()
                                          e.stopPropagation()
                                          const newVal = uuidv4()
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
                                      <Button
                                        size="icon"
                                        type="button"
                                        variant="ghost"
                                        onClick={e => {
                                          e.preventDefault()
                                          e.stopPropagation()
                                          const newVal = uuidv4()
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
                          {/* Hysteria */}
                          <FormField
                            control={form.control}
                            name="proxy_settings.hysteria.auth"
                            render={({ field }) => {
                              return (
                                <FormItem className="mb-2">
                                  <FormLabel>{t('userDialog.proxySettings.hysteriaAuth')}</FormLabel>
                                  <FormControl>
                                    <div dir="ltr" className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                      <Input
                                        {...field}
                                        placeholder={t('userDialog.proxySettings.hysteriaAuth')}
                                        onChange={e => {
                                          field.onChange(e)
                                          form.trigger('proxy_settings.hysteria.auth')
                                          handleFieldChange('proxy_settings.hysteria.auth', e.target.value)
                                        }}
                                      />
                                      <Button
                                        size="icon"
                                        type="button"
                                        variant="ghost"
                                        onClick={e => {
                                          e.preventDefault()
                                          e.stopPropagation()
                                          const newVal = uuidv4()
                                          field.onChange(newVal)
                                          form.trigger('proxy_settings.hysteria.auth')
                                          handleFieldChange('proxy_settings.hysteria.auth', newVal)
                                        }}
                                        title="Generate auth"
                                      >
                                        <RefreshCcw className="h-3 w-3" />
                                      </Button>
                                    </div>
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )
                            }}
                          />
                          <FormField
                            control={form.control}
                            name="proxy_settings.wireguard.private_key"
                            render={({ field }) => (
                              <FormItem className="mb-2">
                                <FormLabel>{t('userDialog.proxySettings.wireguardPrivateKey', { defaultValue: 'WireGuard Private key' })}</FormLabel>
                                <FormControl>
                                  <div dir="ltr" className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                                    <Input
                                      {...field}
                                      value={field.value ?? ''}
                                      placeholder={t('userDialog.proxySettings.wireguardPrivateKey', { defaultValue: 'WireGuard Private key' })}
                                      onChange={e => {
                                        field.onChange(e)
                                        syncWireGuardPublicKey(e.target.value)
                                        form.trigger('proxy_settings.wireguard.private_key')
                                        handleFieldChange('proxy_settings.wireguard.private_key', e.target.value)
                                      }}
                                    />
                                    <Button
                                      size="icon"
                                      type="button"
                                      variant="ghost"
                                      onClick={generateWireGuardProxySettings}
                                      title={t('userDialog.proxySettings.generateWireGuardKeyPair', { defaultValue: 'Generate WireGuard keypair' })}
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
                            name="proxy_settings.wireguard.public_key"
                            render={({ field }) => (
                              <FormItem className="mb-2">
                                <FormLabel>{t('userDialog.proxySettings.wireguardPublicKey', { defaultValue: 'WireGuard Public key' })}</FormLabel>
                                <FormControl>
                                  <Input
                                    dir="ltr"
                                    {...field}
                                    value={field.value ?? ''}
                                    placeholder={t('userDialog.proxySettings.wireguardPublicKey', { defaultValue: 'WireGuard Public key' })}
                                    disabled
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="proxy_settings.wireguard.peer_ips"
                            render={({ field }) => (
                              <FormItem className="mb-2">
                                <FormLabel>{t('userDialog.proxySettings.wireguardPeerIps', { defaultValue: 'WireGuard Peer IPs' })}</FormLabel>
                                <FormControl>
                                  <Textarea
                                    dir="ltr"
                                    value={Array.isArray(field.value) ? field.value.join('\n') : ''}
                                    placeholder={t('userDialog.proxySettings.peerIpsPlaceholder', { defaultValue: 'One CIDR per line, e.g. 10.0.0.10/32' })}
                                    onChange={e => {
                                      const peerIps = parseWireGuardPeerIps(e.target.value)
                                      field.onChange(peerIps)
                                      form.trigger('proxy_settings.wireguard.peer_ips')
                                      handleFieldChange('proxy_settings.wireguard.peer_ips', peerIps)
                                    }}
                                  />
                                </FormControl>
                                <p className="text-muted-foreground text-xs">
                                  {t('userDialog.proxySettings.peerIpsHint', {
                                    defaultValue: 'Leave empty to auto-assign from the global WireGuard peer pool. For manual entries, enter one CIDR per line, and keep each value within that pool.',
                                  })}
                                </p>
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
                    <div className="border-border rounded-(--radius) border p-4">
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
                                      {templateOptions.map((tpl: any) => (
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
                          {!hasTemplateSelected && (
                            <div className="flex gap-4">
                              <FormField
                                control={form.control}
                                name="next_plan.expire"
                                render={({ field }) => (
                                  <FormItem>
                                    <FormLabel>{t('userDialog.nextPlanExpire', { defaultValue: 'Expire' })}</FormLabel>
                                    <FormControl>
                                      <DecimalInput
                                        value={field.value}
                                        emptyValue={0}
                                        zeroValue={0}
                                        keepZeroOnBlur
                                        toDisplayValue={dateUtils.secondsToDays}
                                        toValue={displayValue => dateUtils.daysToSeconds(displayValue) ?? 0}
                                        onValueChange={value => {
                                          const nextValue = value ?? 0
                                          field.onChange(nextValue)
                                          handleFieldChange('next_plan.expire', nextValue)
                                        }}
                                      />
                                    </FormControl>
                                    <span className="text-muted-foreground text-xs">{t('userDialog.days', { defaultValue: 'Days' })}</span>
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
                                      <DecimalInput
                                        value={field.value}
                                        emptyValue={0}
                                        zeroValue={0}
                                        keepZeroOnBlur
                                        toDisplayValue={bytesToFormGigabytes}
                                        toValue={displayValue => gbToBytes(displayValue) ?? 0}
                                        onValueChange={value => {
                                          const nextValue = value ?? 0
                                          field.onChange(nextValue)
                                          handleFieldChange('next_plan.data_limit', nextValue)
                                        }}
                                      />
                                    </FormControl>
                                    <span className="text-muted-foreground text-xs">GB</span>
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
                  {renderUserMetaPanel('hidden lg:block')}
                </div>
                <div className="h-full w-full min-w-0 flex-1 space-y-6 lg:max-w-[300px] xl:max-w-[340px]">
                  <div className="w-full">
                    <div className="flex items-center border-b">
                      {tabs.map(tab => (
                        <button
                          key={tab.id}
                          onClick={() => setActiveTab(tab.id as typeof activeTab)}
                          className={`relative flex-1 px-3 py-2 text-sm font-medium transition-colors ${
                            activeTab === tab.id ? 'border-primary text-foreground border-b-2' : 'text-muted-foreground hover:text-foreground'
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
                                {templateOptions.map((template: any) => (
                                  <SelectItem key={template.id} value={String(template.id)}>
                                    {template.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            {selectedTemplateId && (
                              <div className="text-muted-foreground text-sm">
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
              {renderUserMetaPanel('mt-4 lg:hidden')}
            </div>
            {/* Cancel/Create buttons - always visible */}
            <div className="-mx-1 mt-2 flex flex-row items-center justify-end gap-3 overflow-x-auto px-1 py-1 sm:mx-0 sm:px-0 sm:pt-2 sm:pb-0">
              {editingUser && (
                <DropdownMenu modal={false} open={isActionsMenuOpen} onOpenChange={setActionsMenuOpen}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      aria-label={t('actions', { defaultValue: 'Actions' })}
                      className="group border-border/70 bg-background/80 hover:border-primary/40 hover:bg-primary/5 focus-visible:ring-primary/30 data-[state=open]:border-primary/50 data-[state=open]:bg-primary/10 h-10 w-10 shadow-sm backdrop-blur transition-all hover:shadow-md focus-visible:ring-2"
                    >
                      <EllipsisVertical className="text-muted-foreground group-hover:text-foreground group-data-[state=open]:text-foreground h-4 w-4 transition-all duration-200 group-data-[state=open]:rotate-90" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="start"
                    onEscapeKeyDown={() => setActionsMenuOpen(false)}
                    onPointerDownOutside={() => setActionsMenuOpen(false)}
                    onInteractOutside={() => setActionsMenuOpen(false)}
                  >
                    {isSudo && (
                      <DropdownMenuItem
                        onSelect={() => {
                          setActionsMenuOpen(false)
                          setUserAllIPsModalOpen(true)
                        }}
                      >
                        <Network className="mr-2 h-4 w-4" />
                        <span>{t('userAllIPs.ipAddresses', { defaultValue: 'IP addresses' })}</span>
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem
                      onSelect={() => {
                        setActionsMenuOpen(false)
                        setUsageModalOpen(true)
                      }}
                    >
                      <PieChart className="mr-2 h-4 w-4" />
                      <span>{t('userDialog.usage', { defaultValue: 'Usage' })}</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        setActionsMenuOpen(false)
                        setSubscriptionClientsModalOpen(true)
                      }}
                    >
                      <Users className="mr-2 h-4 w-4" />
                      <span>{t('subscriptionClients.clients', { defaultValue: 'Clients' })}</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        setActionsMenuOpen(false)
                        setHwidsModalOpen(true)
                      }}
                    >
                      <Fingerprint className="mr-2 h-4 w-4" />
                      <span>{t('hwids.title', { defaultValue: 'Hardware IDs' })}</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        setActionsMenuOpen(false)
                        setRevokeSubDialogOpen(true)
                      }}
                    >
                      <Link2Off className="mr-2 h-4 w-4" />
                      <span>{t('userDialog.revokeSubscription', { defaultValue: 'Revoke subscription' })}</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        setActionsMenuOpen(false)
                        setResetUsageDialogOpen(true)
                      }}
                    >
                      <RefreshCcw className="mr-2 h-4 w-4" />
                      <span>{t('userDialog.resetUsage', { defaultValue: 'Reset usage' })}</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              <div className="flex shrink-0 items-center gap-3">
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

                        if (
                          currentValues.status === 'on_hold' &&
                          (!currentValues.on_hold_expire_duration || !Number.isFinite(Number(currentValues.on_hold_expire_duration)) || Number(currentValues.on_hold_expire_duration) <= 0)
                        ) {
                          missingFields.push(t('templates.expire'))
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
            </div>
          </form>
        </Form>
      </DialogContent>
      <AlertDialog open={isResetUsageDialogOpen} onOpenChange={setResetUsageDialogOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <PieChart className="h-5 w-5" />
              {t('usersTable.resetUsageTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('usersTable.resetUsagePrompt', { name: currentUsername })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('usersTable.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmResetUsage} disabled={resetUserDataUsageMutation.isPending}>
              {t('usersTable.resetUsageSubmit')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={isRevokeSubDialogOpen} onOpenChange={setRevokeSubDialogOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Link2Off className="h-5 w-5" />
              {t('revokeUserSub.title')}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('revokeUserSub.prompt', { username: currentUsername })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('usersTable.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmRevokeSubscription} disabled={revokeUserSubscriptionMutation.isPending}>
              {t('revokeUserSub.title')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {isSudo && currentUsername && <UserAllIPsModal isOpen={isUserAllIPsModalOpen} onOpenChange={setUserAllIPsModalOpen} username={currentUsername} />}
      {currentUserId && <UsageModal open={isUsageModalOpen} onClose={() => setUsageModalOpen(false)} userId={currentUserId} />}
      {currentUserId && <UserHwidsModal isOpen={isHwidsModalOpen} onOpenChange={setHwidsModalOpen} userId={currentUserId} username={currentUsername} />}
      {currentUserId && <UserSubscriptionClientsModal isOpen={isSubscriptionClientsModalOpen} onOpenChange={setSubscriptionClientsModalOpen} userId={currentUserId} username={currentUsername} />}
    </Dialog>
  )
}

export default UserModal
