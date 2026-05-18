import { z } from 'zod'
import type { AdminRoleResponse, RoleAccess, RoleFeatures, RoleLimits, RolePermissions } from '@/service/api'

export type RoleScope = 0 | 1 | 2

export type PermissionAction = {
  resource: string
  action: string
  scoped?: boolean
}

export type PermissionGroup = {
  labelKey: string
  actions: PermissionAction[]
}

export const PERMISSION_GROUPS: PermissionGroup[] = [
  {
    labelKey: 'users',
    actions: [
      { resource: 'users', action: 'read', scoped: true },
      { resource: 'users', action: 'create' },
      { resource: 'users', action: 'update', scoped: true },
      { resource: 'users', action: 'delete', scoped: true },
    ],
  },
  {
    labelKey: 'admins',
    actions: [
      { resource: 'admins', action: 'read' },
      { resource: 'admins', action: 'create' },
      { resource: 'admins', action: 'update' },
      { resource: 'admins', action: 'delete' },
    ],
  },
  {
    labelKey: 'roles',
    actions: [
      { resource: 'admin_roles', action: 'read' },
      { resource: 'admin_roles', action: 'create' },
      { resource: 'admin_roles', action: 'update' },
      { resource: 'admin_roles', action: 'delete' },
    ],
  },
  {
    labelKey: 'nodes',
    actions: [
      { resource: 'nodes', action: 'read' },
      { resource: 'nodes', action: 'create' },
      { resource: 'nodes', action: 'update' },
      { resource: 'nodes', action: 'delete' },
      { resource: 'nodes', action: 'stats' },
      { resource: 'nodes', action: 'logs' },
    ],
  },
  {
    labelKey: 'coreHosts',
    actions: [
      { resource: 'cores', action: 'read' },
      { resource: 'cores', action: 'create' },
      { resource: 'cores', action: 'update' },
      { resource: 'cores', action: 'delete' },
      { resource: 'hosts', action: 'read' },
      { resource: 'hosts', action: 'create' },
      { resource: 'hosts', action: 'update' },
      { resource: 'hosts', action: 'delete' },
    ],
  },
  {
    labelKey: 'groupsTemplates',
    actions: [
      { resource: 'groups', action: 'read' },
      { resource: 'groups', action: 'create' },
      { resource: 'groups', action: 'update' },
      { resource: 'groups', action: 'delete' },
      { resource: 'templates', action: 'read' },
      { resource: 'templates', action: 'create' },
      { resource: 'templates', action: 'update' },
      { resource: 'templates', action: 'delete' },
      { resource: 'client_templates', action: 'read' },
      { resource: 'client_templates', action: 'create' },
      { resource: 'client_templates', action: 'update' },
      { resource: 'client_templates', action: 'delete' },
    ],
  },
  {
    labelKey: 'settings',
    actions: [
      { resource: 'settings', action: 'read' },
      { resource: 'settings', action: 'read_general' },
      { resource: 'settings', action: 'update' },
      { resource: 'system', action: 'read' },
      { resource: 'system', action: 'update' },
      { resource: 'hwids', action: 'read' },
      { resource: 'hwids', action: 'update' },
    ],
  },
]

export const LIMIT_KEYS: Array<keyof RoleLimits> = [
  'max_users',
  'data_limit_min',
  'data_limit_max',
  'expire_days_min',
  'expire_days_max',
  'min_hwid_per_user',
  'max_hwid_per_user',
]

export const FEATURE_KEYS: Array<keyof RoleFeatures> = ['can_use_reset_strategy', 'can_use_next_plan']

const scopeSchema = z.object({ scope: z.union([z.literal(0), z.literal(1), z.literal(2)]) })
const permissionValueSchema = z.union([z.boolean(), scopeSchema])
const resourcePermissionsSchema = z.record(z.string(), permissionValueSchema)
const permissionsSchema = z.record(z.string(), resourcePermissionsSchema)

const optionalNullableNumber = z.union([z.coerce.number(), z.null(), z.literal('').transform(() => null)]).optional()

const limitsSchema = z.object({
  max_users: optionalNullableNumber,
  data_limit_min: optionalNullableNumber,
  data_limit_max: optionalNullableNumber,
  expire_days_min: optionalNullableNumber,
  expire_days_max: optionalNullableNumber,
  min_hwid_per_user: optionalNullableNumber,
  max_hwid_per_user: optionalNullableNumber,
})

const featuresSchema = z.object({
  can_use_reset_strategy: z.boolean(),
  can_use_next_plan: z.boolean(),
})

const accessSchema = z.object({
  require_template: z.boolean(),
  allowed_template_ids: z.array(z.number().int().positive()).nullable(),
  allowed_group_ids: z.array(z.number().int().positive()).nullable(),
})

export const adminRoleFormSchema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(64),
  permissions: permissionsSchema,
  limits: limitsSchema,
  features: featuresSchema,
  access: accessSchema,
})

export type AdminRoleFormValuesInput = z.input<typeof adminRoleFormSchema>
export type AdminRoleFormValues = z.infer<typeof adminRoleFormSchema>

export const defaultAdminRoleFeatures = (): RoleFeatures => ({
  can_use_reset_strategy: true,
  can_use_next_plan: true,
})

export const defaultAdminRoleAccess = (): AdminRoleFormValues['access'] => ({
  require_template: false,
  allowed_template_ids: null,
  allowed_group_ids: null,
})

export const adminRoleFormDefaultValues: AdminRoleFormValuesInput = {
  name: '',
  permissions: {},
  limits: {
    max_users: null,
    data_limit_min: null,
    data_limit_max: null,
    expire_days_min: null,
    expire_days_max: null,
    min_hwid_per_user: null,
    max_hwid_per_user: null,
  },
  features: defaultAdminRoleFeatures(),
  access: defaultAdminRoleAccess(),
}

export const adminRoleFormFromResponse = (role: AdminRoleResponse): AdminRoleFormValuesInput => ({
  name: role.name,
  permissions: (role.permissions || {}) as AdminRoleFormValues['permissions'],
  limits: {
    max_users: role.limits?.max_users ?? null,
    data_limit_min: role.limits?.data_limit_min ?? null,
    data_limit_max: role.limits?.data_limit_max ?? null,
    expire_days_min: role.limits?.expire_days_min ?? null,
    expire_days_max: role.limits?.expire_days_max ?? null,
    min_hwid_per_user: role.limits?.min_hwid_per_user ?? null,
    max_hwid_per_user: role.limits?.max_hwid_per_user ?? null,
  },
  features: {
    can_use_reset_strategy: role.features?.can_use_reset_strategy ?? true,
    can_use_next_plan: role.features?.can_use_next_plan ?? true,
  },
  access: {
    require_template: role.access?.require_template ?? false,
    allowed_template_ids: role.access?.allowed_template_ids ?? null,
    allowed_group_ids: role.access?.allowed_group_ids ?? null,
  },
})

export const adminRoleFormToPayload = (values: AdminRoleFormValues) => ({
  name: values.name.trim(),
  permissions: values.permissions as RolePermissions,
  limits: Object.fromEntries(Object.entries(values.limits).filter(([, v]) => v !== null && v !== undefined)) as RoleLimits,
  features: values.features as RoleFeatures,
  access: {
    require_template: values.access.require_template,
    allowed_template_ids: values.access.allowed_template_ids?.length ? values.access.allowed_template_ids : null,
    allowed_group_ids: values.access.allowed_group_ids?.length ? values.access.allowed_group_ids : null,
  } as RoleAccess,
})

export const BUILT_IN_ROLE_IDS = new Set([1, 2, 3])

export const isProtectedRole = (role: AdminRoleResponse) => role.is_owner || BUILT_IN_ROLE_IDS.has(role.id)
