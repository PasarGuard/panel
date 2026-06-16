import { useEffect, useMemo, useState } from 'react'
import { FieldErrors, UseFormReturn, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'
import { Check, ChevronsUpDown, Cpu, Eye, FolderTree, KeyRound, Minus, Pencil, Search, Shield, Sliders, Sparkles, X } from 'lucide-react'

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { LoaderButton } from '@/components/ui/loader-button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

import { DecimalInput } from '@/components/common/decimal-input'

import useDirDetection from '@/hooks/use-dir-detection'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors.ts'
import { cn } from '@/lib/utils'
import { bytesToFormGigabytes, formatBytes, gbToBytes } from '@/utils/formatByte'
import { getGetRolesQueryKey, getGetRolesSimpleQueryKey, useCreateRole, useGetAllGroups, useGetUserTemplatesSimple, useModifyRole } from '@/service/api'

import {
  AdminRoleFormValues,
  AdminRoleFormValuesInput,
  FEATURE_KEYS,
  PERMISSION_GROUPS,
  PermissionAction,
  RoleScope,
  adminRoleFormDefaultValues,
  adminRoleFormToPayload,
} from '@/features/admin-roles/forms/admin-role-form'

type RolePermissionFormMap = Record<string, Record<string, boolean | { scope: RoleScope }>>

const ONE_GB_IN_BYTES = 1024 * 1024 * 1024

interface AdminRoleModalProps {
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  form: UseFormReturn<AdminRoleFormValuesInput, unknown, AdminRoleFormValues>
  editingRole: boolean
  editingRoleId?: number | null
  readOnly?: boolean
}

const SECTION_PERMISSIONS = 'permissions'
const SECTION_LIMITS = 'limits'
const SECTION_HWID = 'hwid'
const SECTION_FEATURES = 'features'
const SECTION_ACCESS = 'access'

export default function AdminRoleModal({ isDialogOpen, onOpenChange, form, editingRole, editingRoleId, readOnly = false }: AdminRoleModalProps) {
  const { t } = useTranslation()
  const handleError = useDynamicErrorHandler()
  const queryClient = useQueryClient()
  const createRole = useCreateRole()
  const modifyRole = useModifyRole()
  const [openSection, setOpenSection] = useState<string | undefined>(SECTION_PERMISSIONS)

  const groupsQuery = useGetAllGroups({}, { query: { enabled: isDialogOpen } })
  const templatesQuery = useGetUserTemplatesSimple(undefined, { query: { enabled: isDialogOpen } })

  const groupsOptions = useMemo(() => (groupsQuery.data?.groups || []).map(group => ({ id: group.id, name: group.name || `#${group.id}` })), [groupsQuery.data?.groups])
  const templatesOptions = useMemo(() => (templatesQuery.data?.templates || []).map(tpl => ({ id: tpl.id, name: tpl.name || `#${tpl.id}` })), [templatesQuery.data?.templates])

  useEffect(() => {
    if (!isDialogOpen) {
      form.clearErrors()
      setOpenSection(SECTION_PERMISSIONS)
    }
  }, [isDialogOpen, form])

  const isSaving = createRole.isPending || modifyRole.isPending

  const onSubmit = async (values: AdminRoleFormValues) => {
    try {
      const payload = adminRoleFormToPayload(values)
      if (editingRole && editingRoleId != null) {
        await modifyRole.mutateAsync({ roleId: editingRoleId, data: payload })
        toast.success(t('adminRoles.editSuccess', { name: payload.name, defaultValue: 'Role «{{name}}» has been updated successfully' }))
      } else {
        await createRole.mutateAsync({ data: payload })
        toast.success(t('adminRoles.createSuccess', { name: payload.name, defaultValue: 'Role «{{name}}» has been created successfully' }))
      }
      await Promise.all([queryClient.invalidateQueries({ queryKey: getGetRolesQueryKey() }), queryClient.invalidateQueries({ queryKey: getGetRolesSimpleQueryKey() })])
      onOpenChange(false)
      form.reset(adminRoleFormDefaultValues)
    } catch (error: any) {
      handleError({ error, fields: ['name'], form, contextKey: 'adminRoles' })
    }
  }

  const onInvalidSubmit = (errors: FieldErrors<AdminRoleFormValuesInput>) => {
    const firstPath = firstErrorPath(errors)
    if (firstPath?.startsWith('limits.')) setOpenSection(SECTION_LIMITS)
    else if (firstPath?.startsWith('hwid.')) setOpenSection(SECTION_HWID)
    else if (firstPath?.startsWith('features.')) setOpenSection(SECTION_FEATURES)
    else if (firstPath?.startsWith('access.')) setOpenSection(SECTION_ACCESS)
    else if (firstPath?.startsWith('permissions.')) setOpenSection(SECTION_PERMISSIONS)

    toast.error(
      firstPath
        ? t('validation.invalidField', { field: firstPath, defaultValue: `Invalid value for ${firstPath}` })
        : t('validation.formInvalid', { defaultValue: 'Form is invalid. Please check all fields.' }),
    )
  }

  const handleAccordionChange = (value: string) => {
    setOpenSection(prev => (prev === value ? undefined : value))
  }

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent className="h-auto w-full max-w-2xl" onOpenAutoFocus={e => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {readOnly ? <Eye className="h-5 w-5" /> : editingRole ? <Pencil className="h-5 w-5" /> : <Shield className="h-5 w-5" />}
            <span>
              {readOnly
                ? t('adminRoles.viewRole', { defaultValue: 'View role' })
                : editingRole
                  ? t('adminRoles.editRole', { defaultValue: 'Edit role' })
                  : t('adminRoles.createRole', { defaultValue: 'Create role' })}
            </span>
          </DialogTitle>
          <DialogDescription className="sr-only">{t('adminRoles.modalDescription', { defaultValue: 'Configure permissions, limits, features and access for this role.' })}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit, onInvalidSubmit)} className="space-y-4">
            {readOnly && (
              <div className="bg-muted/40 text-muted-foreground rounded-md border border-dashed px-3 py-2 text-xs">
                {t('adminRoles.readOnlyHint', { defaultValue: 'This is a built-in role. You can review its configuration but cannot modify it.' })}
              </div>
            )}
            <div className="-mr-4 max-h-[80dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <fieldset disabled={readOnly} className="disabled:opacity-100">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('name', { defaultValue: 'Name' })}</FormLabel>
                      <FormControl>
                        <Input placeholder="operator-custom" autoComplete="off" isError={!!form.formState.errors.name} {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </fieldset>

              <Accordion type="single" collapsible value={openSection} onValueChange={handleAccordionChange} className="mt-0! mb-2 flex w-full flex-col gap-y-4">
                <AccordionItem className="rounded-sm border px-4 **:data-[state=closed]:no-underline **:data-[state=open]:no-underline" value={SECTION_PERMISSIONS}>
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <KeyRound className="h-4 w-4" />
                      <span>{t('adminRoles.permissions', { defaultValue: 'Permissions' })}</span>
                      <PermissionsBadge form={form} />
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <fieldset disabled={readOnly} className={cn('disabled:opacity-100', readOnly && 'pointer-events-none')}>
                      <PermissionsSection form={form} />
                    </fieldset>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 **:data-[state=closed]:no-underline **:data-[state=open]:no-underline" value={SECTION_LIMITS}>
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Sliders className="h-4 w-4" />
                      <span>{t('adminRoles.limits', { defaultValue: 'Limits' })}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <fieldset disabled={readOnly} className={cn('disabled:opacity-100', readOnly && 'pointer-events-none')}>
                      <LimitsSection form={form} />
                    </fieldset>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 **:data-[state=closed]:no-underline **:data-[state=open]:no-underline" value={SECTION_HWID}>
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Cpu className="h-4 w-4" />
                      <span>{t('adminRoles.hwidPolicy', { defaultValue: 'HWID policy' })}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <fieldset disabled={readOnly} className={cn('disabled:opacity-100', readOnly && 'pointer-events-none')}>
                      <HwidPolicySection form={form} />
                    </fieldset>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 **:data-[state=closed]:no-underline **:data-[state=open]:no-underline" value={SECTION_FEATURES}>
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4" />
                      <span>{t('adminRoles.features', { defaultValue: 'Features' })}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <fieldset disabled={readOnly} className={cn('disabled:opacity-100', readOnly && 'pointer-events-none')}>
                      <FeaturesSection form={form} />
                    </fieldset>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem className="rounded-sm border px-4 **:data-[state=closed]:no-underline **:data-[state=open]:no-underline" value={SECTION_ACCESS}>
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <FolderTree className="h-4 w-4" />
                      <span>{t('adminRoles.access', { defaultValue: 'Access' })}</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-1 pt-1">
                    <fieldset disabled={readOnly} className={cn('disabled:opacity-100', readOnly && 'pointer-events-none')}>
                      <AccessSection form={form} groupsOptions={groupsOptions} templatesOptions={templatesOptions} isLoading={groupsQuery.isLoading || templatesQuery.isLoading} />
                    </fieldset>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {readOnly ? t('close', { defaultValue: 'Close' }) : t('cancel')}
              </Button>
              {!readOnly && (
                <LoaderButton type="submit" isLoading={isSaving} loadingText={editingRole ? t('modifying') : t('creating')}>
                  {editingRole ? t('modify', { defaultValue: 'Modify' }) : t('create', { defaultValue: 'Create' })}
                </LoaderButton>
              )}
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

type AdminRoleForm = UseFormReturn<AdminRoleFormValuesInput, unknown, AdminRoleFormValues>

function firstErrorPath(errors: FieldErrors<AdminRoleFormValuesInput>, prefix = ''): string | null {
  for (const [key, value] of Object.entries(errors)) {
    if (!value) continue
    const path = prefix ? `${prefix}.${key}` : key
    if ('message' in value || 'type' in value) return path
    if (typeof value === 'object') {
      const nestedPath = firstErrorPath(value as FieldErrors<AdminRoleFormValuesInput>, path)
      if (nestedPath) return nestedPath
    }
  }
  return null
}

function PermissionsBadge({ form }: { form: AdminRoleForm }) {
  const { t } = useTranslation()
  const permissions = useWatch({ control: form.control, name: 'permissions' })
  const total = useMemo(() => {
    let count = 0
    for (const value of Object.values(permissions || {})) {
      if (!value || typeof value !== 'object') continue
      for (const inner of Object.values(value as Record<string, unknown>)) {
        if (inner === true) count += 1
        else if (inner && typeof inner === 'object' && Number((inner as any).scope) > 0) count += 1
      }
    }
    return count
  }, [permissions])

  if (!total) return null
  return (
    <Badge variant="secondary" className="ms-2 shrink-0 text-[10px]">
      {t('adminRoles.permissionCount', { count: total, defaultValue: '{{count}} permissions' })}
    </Badge>
  )
}

function PermissionsSection({ form }: { form: AdminRoleForm }) {
  const { t } = useTranslation()
  const permissions = useWatch({ control: form.control, name: 'permissions' }) as RolePermissionFormMap | undefined

  const setPermission = (resource: string, action: string, value: boolean | { scope: RoleScope }) => {
    const next: RolePermissionFormMap = { ...(permissions || {}) }
    next[resource] = { ...(next[resource] || {}), [action]: value }
    form.setValue('permissions', next, { shouldDirty: true })
  }

  const setGroupAll = (group: { actions: PermissionAction[] }, mode: 'all' | 'none') => {
    const next: RolePermissionFormMap = { ...(permissions || {}) }
    for (const item of group.actions) {
      const inner = { ...(next[item.resource] || {}) }
      if (item.scoped) inner[item.action] = { scope: mode === 'all' ? 2 : 0 }
      else inner[item.action] = mode === 'all'
      next[item.resource] = inner
    }
    form.setValue('permissions', next, { shouldDirty: true })
  }

  const formatActionLabel = (item: PermissionAction) => {
    const resourceLabel = t(`adminRoles.resources.${item.resource}`, { defaultValue: humanizeKey(item.resource) })
    const actionLabel = t(`adminRoles.actions.${item.resource}.${item.action}`, {
      defaultValue: t(`adminRoles.actions.common.${item.action}`, { defaultValue: humanizeKey(item.action) }),
    })
    return { resourceLabel, actionLabel }
  }

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">{t('adminRoles.roleFormHint', { defaultValue: 'Scoped user actions use none, own, or all. Other actions are boolean toggles.' })}</p>
      {PERMISSION_GROUPS.map(group => {
        const enabledInGroup = group.actions.reduce((acc, item) => {
          const value = permissions?.[item.resource]?.[item.action]
          if (value === true) return acc + 1
          if (value && typeof value === 'object' && Number((value as any).scope) > 0) return acc + 1
          return acc
        }, 0)

        const groupLabel = t(`adminRoles.groups.${group.labelKey}`)
        const showResourcePrefix = group.actions.some((a, _, all) => all.some(b => b !== a && b.action === a.action && b.resource !== a.resource))

        return (
          <div key={group.labelKey} className="bg-background rounded-md border">
            <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-sm font-medium">{groupLabel}</span>
                <span className="text-muted-foreground text-[10px]">
                  {enabledInGroup}/{group.actions.length}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setGroupAll(group, 'all')}>
                  {t('selectAll', { defaultValue: 'Select all' })}
                </Button>
                <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setGroupAll(group, 'none')}>
                  {t('deselectAll', { defaultValue: 'Clear' })}
                </Button>
              </div>
            </div>
            <div className="grid gap-2 p-2 sm:grid-cols-2">
              {group.actions.map(item => {
                const current = permissions?.[item.resource]?.[item.action]
                const isScope = current && typeof current === 'object'
                const scopeValue: RoleScope = isScope ? (Number((current as any).scope) as RoleScope) : current === true ? 2 : 0
                const boolValue = current === true
                const { resourceLabel, actionLabel } = formatActionLabel(item)

                return (
                  <div key={`${item.resource}.${item.action}`} className="bg-muted/40 flex min-h-10 items-center justify-between gap-3 rounded-md px-3 py-2">
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <span className="truncate text-xs font-medium">{showResourcePrefix ? `${resourceLabel} · ${actionLabel}` : actionLabel}</span>
                      {item.scoped && <span className="text-muted-foreground text-[10px]">{t('adminRoles.scopedBadge', { defaultValue: 'Scoped' })}</span>}
                    </div>
                    {item.scoped ? (
                      <Select value={String(scopeValue)} onValueChange={next => setPermission(item.resource, item.action, { scope: Number(next) as RoleScope })}>
                        <SelectTrigger className="h-8 w-28">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="0">{t('adminRoles.scopes.none', { defaultValue: 'None' })}</SelectItem>
                          <SelectItem value="1">{t('adminRoles.scopes.own', { defaultValue: 'Own' })}</SelectItem>
                          <SelectItem value="2">{t('adminRoles.scopes.all', { defaultValue: 'All' })}</SelectItem>
                        </SelectContent>
                      </Select>
                    ) : (
                      <Switch checked={boolValue} onCheckedChange={checked => setPermission(item.resource, item.action, checked)} />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function humanizeKey(key: string) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function LimitsSection({ form }: { form: AdminRoleForm }) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">{t('adminRoles.limitsHint', { defaultValue: 'Leave empty to inherit defaults. Set to 0 to disable.' })}</p>

      <FormField
        control={form.control}
        name="limits.max_users"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('adminRoles.limitFields.max_users', { defaultValue: 'Max users' })}</FormLabel>
            <FormControl>
              <DecimalInput
                placeholder={t('adminRoles.unlimited', { defaultValue: 'Unlimited' })}
                value={typeof field.value === 'number' ? field.value : null}
                emptyValue={null as any}
                zeroValue={0}
                onValueChange={value => field.onChange(value ?? null)}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <BytesLimitField form={form} name="limits.data_limit_min" labelKey="adminRoles.limitFields.data_limit_min" />
        <BytesLimitField form={form} name="limits.data_limit_max" labelKey="adminRoles.limitFields.data_limit_max" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <NumberLimitField form={form} name="limits.expire_days_min" labelKey="adminRoles.limitFields.expire_days_min" />
        <NumberLimitField form={form} name="limits.expire_days_max" labelKey="adminRoles.limitFields.expire_days_max" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <NumberLimitField form={form} name="limits.min_hwid_per_user" labelKey="adminRoles.limitFields.min_hwid_per_user" />
        <NumberLimitField form={form} name="limits.max_hwid_per_user" labelKey="adminRoles.limitFields.max_hwid_per_user" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <NumberLimitField form={form} name="limits.on_hold_timeout_days_min" labelKey="adminRoles.limitFields.on_hold_timeout_days_min" />
        <NumberLimitField form={form} name="limits.on_hold_timeout_days_max" labelKey="adminRoles.limitFields.on_hold_timeout_days_max" />
      </div>
    </div>
  )
}

function HwidPolicySection({ form }: { form: AdminRoleForm }) {
  const { t } = useTranslation()
  const mode = useWatch({ control: form.control, name: 'hwid.mode' })
  const isOverride = mode === 'override'

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">
        {t('adminRoles.hwidPolicyHint', { defaultValue: 'Choose how HWID policy is applied. Use "Override" to customize limits for this role.' })}
      </p>

      <FormField
        control={form.control}
        name="hwid.mode"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="text-sm font-medium">{t('adminRoles.hwidMode', { defaultValue: 'HWID Mode' })}</FormLabel>
            <FormControl>
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="disabled">{t('adminRoles.hwidModeDisabled', { defaultValue: 'Disabled' })}</SelectItem>
                  <SelectItem value="use_global">{t('adminRoles.hwidModeUseGlobal', { defaultValue: 'Use Global Settings' })}</SelectItem>
                  <SelectItem value="override">{t('adminRoles.hwidModeOverride', { defaultValue: 'Override Settings' })}</SelectItem>
                </SelectContent>
              </Select>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      {isOverride && (
        <>
          <FormField
            control={form.control}
            name="hwid.forced"
            render={({ field }) => (
              <FormItem className="flex cursor-pointer flex-row items-center justify-between space-y-0 rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
                <div className="space-y-0.5">
                  <FormLabel className="text-base">{t('settings.hwid.forced.title', { defaultValue: 'Require HWID header' })}</FormLabel>
                  <p className="text-muted-foreground text-xs">{t('settings.hwid.forced.description', { defaultValue: 'Reject subscription requests that do not send X-HWID.' })}</p>
                </div>
                <FormControl>
                  <div onClick={e => e.stopPropagation()}>
                    <Switch checked={!!field.value} onCheckedChange={field.onChange} />
                  </div>
                </FormControl>
              </FormItem>
            )}
          />

          <div className="grid gap-3 sm:grid-cols-3">
            <NumberLimitField form={form} name="hwid.fallback_limit" labelKey="settings.hwid.fallbackLimit.title" />
            <NumberLimitField form={form} name="hwid.min_limit" labelKey="settings.hwid.minLimit.title" />
            <NumberLimitField form={form} name="hwid.max_limit" labelKey="settings.hwid.maxLimit.title" />
          </div>
        </>
      )}
    </div>
  )
}

function NumberLimitField({ form, name, labelKey, disabled = false }: { form: AdminRoleForm; name: any; labelKey: string; disabled?: boolean }) {
  const { t } = useTranslation()
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel className="text-xs">{t(labelKey)}</FormLabel>
          <FormControl>
            <DecimalInput
              placeholder={t('adminRoles.inherit', { defaultValue: 'Inherit' })}
              value={typeof field.value === 'number' ? field.value : null}
              emptyValue={null as any}
              zeroValue={0}
              onValueChange={value => field.onChange(value ?? null)}
              disabled={disabled}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  )
}

function BytesLimitField({ form, name, labelKey }: { form: AdminRoleForm; name: any; labelKey: string }) {
  const { t } = useTranslation()
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => {
        const numericValue = typeof field.value === 'number' ? field.value : null
        return (
          <FormItem className="relative">
            <FormLabel className="text-xs">{t(labelKey)}</FormLabel>
            <FormControl>
              <div className="relative">
                <DecimalInput
                  placeholder={t('adminRoles.unlimited', { defaultValue: 'Unlimited' })}
                  value={numericValue == null ? null : bytesToFormGigabytes(numericValue)}
                  onValueChange={value => {
                    if (value == null) {
                      field.onChange(null)
                      return
                    }
                    field.onChange(gbToBytes(value))
                  }}
                  emptyValue={undefined}
                  className="pr-10"
                />
                <span className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs font-medium">{t('userDialog.gb', { defaultValue: 'GB' })}</span>
              </div>
            </FormControl>
            {numericValue != null && numericValue > 0 && numericValue < ONE_GB_IN_BYTES && (
              <p dir="ltr" className="text-muted-foreground mt-1 w-full text-end text-[11px]">
                {formatBytes(numericValue)}
              </p>
            )}
            <FormMessage />
          </FormItem>
        )
      }}
    />
  )
}

function FeaturesSection({ form }: { form: AdminRoleForm }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-3">
      <FormField
        control={form.control}
        name="disabled_when_limited"
        render={({ field }) => (
          <FormItem className="flex cursor-pointer flex-row items-center justify-between space-y-0 rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
            <div className="space-y-0.5">
              <FormLabel className="text-base">{t('adminRoles.limitedBehavior.disabledWhenLimited.title', { defaultValue: 'Block limited admins' })}</FormLabel>
              <p className="text-muted-foreground text-xs">
                {t('adminRoles.limitedBehavior.disabledWhenLimited.description', { defaultValue: 'Deny all dashboard and API access after an admin reaches their data limit.' })}
              </p>
            </div>
            <FormControl>
              <div onClick={e => e.stopPropagation()}>
                <Switch checked={!!field.value} onCheckedChange={field.onChange} />
              </div>
            </FormControl>
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="disconnect_users_when_limited"
        render={({ field }) => (
          <FormItem className="flex cursor-pointer flex-row items-center justify-between space-y-0 rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
            <div className="space-y-0.5">
              <FormLabel className="text-base">{t('adminRoles.limitedBehavior.disconnectUsersWhenLimited.title', { defaultValue: 'Disconnect users when limited' })}</FormLabel>
              <p className="text-muted-foreground text-xs">
                {t('adminRoles.limitedBehavior.disconnectUsersWhenLimited.description', { defaultValue: "Remove this admin's users from nodes while the admin is usage-limited." })}
              </p>
            </div>
            <FormControl>
              <div onClick={e => e.stopPropagation()}>
                <Switch checked={!!field.value} onCheckedChange={field.onChange} />
              </div>
            </FormControl>
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="disconnect_users_when_disabled"
        render={({ field }) => (
          <FormItem className="flex cursor-pointer flex-row items-center justify-between space-y-0 rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
            <div className="space-y-0.5">
              <FormLabel className="text-base">{t('adminRoles.limitedBehavior.disconnectUsersWhenDisabled.title', { defaultValue: 'Disconnect users when disabled' })}</FormLabel>
              <p className="text-muted-foreground text-xs">
                {t('adminRoles.limitedBehavior.disconnectUsersWhenDisabled.description', { defaultValue: "Remove this admin's users from nodes while the admin is disabled." })}
              </p>
            </div>
            <FormControl>
              <div onClick={e => e.stopPropagation()}>
                <Switch checked={!!field.value} onCheckedChange={field.onChange} />
              </div>
            </FormControl>
          </FormItem>
        )}
      />

      {FEATURE_KEYS.map(key => (
        <FormField
          key={key}
          control={form.control}
          name={`features.${key}` as const}
          render={({ field }) => (
            <FormItem className="flex cursor-pointer flex-row items-center justify-between space-y-0 rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
              <div className="space-y-0.5">
                <FormLabel className="text-base">{t(`adminRoles.featureFields.${key}.title`, { defaultValue: key })}</FormLabel>
                <p className="text-muted-foreground text-xs">{t(`adminRoles.featureFields.${key}.description`, { defaultValue: '' })}</p>
              </div>
              <FormControl>
                <div onClick={e => e.stopPropagation()}>
                  <Switch checked={!!field.value} onCheckedChange={field.onChange} />
                </div>
              </FormControl>
            </FormItem>
          )}
        />
      ))}
    </div>
  )
}

function AccessSection({
  form,
  groupsOptions,
  templatesOptions,
  isLoading,
}: {
  form: AdminRoleForm
  groupsOptions: Array<{ id: number; name: string }>
  templatesOptions: Array<{ id: number; name: string }>
  isLoading: boolean
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-4">
      <FormField
        control={form.control}
        name="access.require_template"
        render={({ field }) => (
          <FormItem className="flex cursor-pointer flex-row items-center justify-between space-y-0 rounded-lg border p-4" onClick={() => field.onChange(!field.value)}>
            <div className="space-y-0.5">
              <FormLabel className="text-base">{t('adminRoles.requireTemplateTitle', { defaultValue: 'Require template' })}</FormLabel>
              <p className="text-muted-foreground text-xs">
                {t('adminRoles.requireTemplateDescription', { defaultValue: 'Force admins with this role to create or modify users only from a template.' })}
              </p>
            </div>
            <FormControl>
              <div onClick={e => e.stopPropagation()}>
                <Switch checked={!!field.value} onCheckedChange={field.onChange} />
              </div>
            </FormControl>
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="access.allowed_template_ids"
        render={({ field }) => (
          <IdMultiSelect
            label={t('adminRoles.allowedTemplates', { defaultValue: 'Allowed templates' })}
            description={t('adminRoles.allowedTemplatesDescription', { defaultValue: 'Restrict templates this role can use. Leave empty to allow all.' })}
            emptyText={t('adminRoles.noTemplates', { defaultValue: 'No templates available' })}
            options={templatesOptions}
            value={field.value || []}
            onChange={ids => field.onChange(ids.length ? ids : null)}
            isLoading={isLoading}
          />
        )}
      />

      <FormField
        control={form.control}
        name="access.allowed_group_ids"
        render={({ field }) => (
          <IdMultiSelect
            label={t('adminRoles.allowedGroups', { defaultValue: 'Allowed groups' })}
            description={t('adminRoles.allowedGroupsDescription', { defaultValue: 'Restrict user groups this role can manage. Leave empty to allow all.' })}
            emptyText={t('adminRoles.noGroups', { defaultValue: 'No groups available' })}
            options={groupsOptions}
            value={field.value || []}
            onChange={ids => field.onChange(ids.length ? ids : null)}
            isLoading={isLoading}
          />
        )}
      />
    </div>
  )
}

interface IdMultiSelectProps {
  label: string
  description?: string
  emptyText: string
  options: Array<{ id: number; name: string }>
  value: number[]
  onChange: (ids: number[]) => void
  isLoading?: boolean
}

function IdMultiSelect({ label, description, emptyText, options, value, onChange, isLoading }: IdMultiSelectProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const selected = useMemo(() => new Set(value), [value])
  const optionMap = useMemo(() => new Map(options.map(option => [option.id, option] as const)), [options])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return options
    return options.filter(option => option.name.toLowerCase().includes(query))
  }, [options, search])

  const toggle = (id: number) => {
    if (selected.has(id)) onChange(value.filter(item => item !== id))
    else onChange([...value, id])
  }

  const allFilteredSelected = filtered.length > 0 && filtered.every(option => selected.has(option.id))
  const anyFilteredSelected = filtered.some(option => selected.has(option.id))

  const handleToggleAll = () => {
    if (allFilteredSelected) {
      const filteredIds = new Set(filtered.map(option => option.id))
      onChange(value.filter(id => !filteredIds.has(id)))
      return
    }
    const next = [...value]
    for (const option of filtered) {
      if (!selected.has(option.id)) next.push(option.id)
    }
    onChange(next)
  }

  return (
    <FormItem>
      <FormLabel>{label}</FormLabel>
      {description && <p className="text-muted-foreground text-xs">{description}</p>}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" role="combobox" className="h-auto min-h-[40px] w-full justify-between p-2" disabled={isLoading}>
            <div className="flex flex-1 flex-wrap gap-1.5">
              {value.length === 0 ? (
                <span className="text-muted-foreground text-sm">{isLoading ? t('loading', { defaultValue: 'Loading...' }) : t('adminRoles.allowAll', { defaultValue: 'Allow all' })}</span>
              ) : (
                value.map(id => {
                  const option = optionMap.get(id)
                  return (
                    <Badge key={id} variant="secondary" className="flex items-center gap-1">
                      <span className="max-w-40 truncate">{option?.name || `#${id}`}</span>
                      <X
                        className="hover:text-destructive h-3 w-3 cursor-pointer"
                        onClick={event => {
                          event.stopPropagation()
                          onChange(value.filter(item => item !== id))
                        }}
                      />
                    </Badge>
                  )
                })
              )}
            </div>
            <ChevronsUpDown className="ms-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-[min(90vw,28rem)] p-2"
          align={dir === 'rtl' ? 'end' : 'start'}
          onWheelCapture={event => event.stopPropagation()}
          onTouchMoveCapture={event => event.stopPropagation()}
        >
          <div className="space-y-2">
            <div className="relative">
              <Search className="text-muted-foreground absolute top-2.5 left-2 h-4 w-4" />
              <Input value={search} onChange={event => setSearch(event.target.value)} placeholder={t('search', { defaultValue: 'Search' })} className="pl-8" />
            </div>
            {options.length > 0 && (
              <Button type="button" variant="ghost" size="sm" onClick={handleToggleAll} className="w-full justify-start text-xs">
                <SelectionCheckbox checked={allFilteredSelected ? true : anyFilteredSelected ? 'indeterminate' : false} className="me-2 h-3.5 w-3.5" />
                {allFilteredSelected ? t('deselectAll', { defaultValue: 'Deselect all' }) : t('selectAll', { defaultValue: 'Select all' })}
              </Button>
            )}
            <ScrollArea className="bg-muted/20 h-[min(45dvh,14rem)] overscroll-contain rounded-md border">
              <div className="space-y-1 p-1">
                {isLoading ? (
                  <div className="text-muted-foreground px-2 py-3 text-xs">{t('loading', { defaultValue: 'Loading...' })}</div>
                ) : filtered.length === 0 ? (
                  <div className="text-muted-foreground px-2 py-3 text-xs">{options.length === 0 ? emptyText : t('noResults', { defaultValue: 'No results' })}</div>
                ) : (
                  filtered.map(option => {
                    const isSelected = selected.has(option.id)
                    return (
                      <button
                        type="button"
                        key={option.id}
                        onClick={() => toggle(option.id)}
                        className={cn('hover:bg-accent flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm', isSelected && 'bg-accent/60')}
                      >
                        <SelectionCheckbox checked={isSelected} className="h-3.5 w-3.5" />
                        <span className="min-w-0 truncate">{option.name}</span>
                      </button>
                    )
                  })
                )}
              </div>
            </ScrollArea>
          </div>
        </PopoverContent>
      </Popover>
      <FormMessage />
    </FormItem>
  )
}

function SelectionCheckbox({ checked, className }: { checked: boolean | 'indeterminate'; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('border-primary text-primary-foreground pointer-events-none inline-flex shrink-0 items-center justify-center rounded-sm border', checked && 'bg-primary', className)}
    >
      {checked === 'indeterminate' ? <Minus className="h-3 w-3 stroke-current" /> : checked ? <Check className="h-3 w-3 stroke-current" /> : null}
    </span>
  )
}
