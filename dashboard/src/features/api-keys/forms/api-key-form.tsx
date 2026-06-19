import { z } from 'zod'

// Mirrors RolePermissions from the backend — all fields optional
const roleActionValue = z.union([
  z.boolean(),
  z.object({ scope: z.number() }),
]).nullable().optional()

const resourcePermissionsSchema = z.object({
  create: roleActionValue,
  read: roleActionValue,
  read_simple: roleActionValue,
  update: roleActionValue,
  delete: roleActionValue,
  reset_usage: roleActionValue,
  revoke_sub: roleActionValue,
  set_owner: roleActionValue,
  activate_next_plan: roleActionValue,
  reconnect: roleActionValue,
  update_core: roleActionValue,
  logs: roleActionValue,
  stats: roleActionValue,
  read_general: roleActionValue,
}).partial()

export const permissionsSchema = z.object({
  users: resourcePermissionsSchema.optional(),
  admins: resourcePermissionsSchema.optional(),
  nodes: resourcePermissionsSchema.optional(),
  groups: resourcePermissionsSchema.optional(),
  hosts: resourcePermissionsSchema.optional(),
  templates: resourcePermissionsSchema.optional(),
  client_templates: resourcePermissionsSchema.optional(),
  cores: resourcePermissionsSchema.optional(),
  settings: resourcePermissionsSchema.optional(),
  system: resourcePermissionsSchema.optional(),
  hwids: resourcePermissionsSchema.optional(),
  admin_roles: resourcePermissionsSchema.optional(),
  api_keys: resourcePermissionsSchema.optional(),
}).optional().default({})

export const apiKeyFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(128),
  note: z.string().max(512).optional(),
  permissions: permissionsSchema,
  expire_date: z.union([z.date(), z.string(), z.number()]).nullable().optional(),
  status: z.enum(['active', 'disabled']).optional(),
})

export type ApiKeyFormValues = z.infer<typeof apiKeyFormSchema>

export const apiKeyFormDefaultValues: ApiKeyFormValues = {
  name: '',
  note: '',
  permissions: {},
  expire_date: null,
  status: 'active',
}
