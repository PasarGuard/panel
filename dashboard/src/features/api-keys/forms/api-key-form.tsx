import { z } from 'zod'

import { sanitizeRolePermissions } from '@/features/admin-roles/forms/admin-role-form'

const scopeSchema = z.object({ scope: z.union([z.literal(0), z.literal(1), z.literal(2)]) })
const permissionValueSchema = z.union([z.boolean(), scopeSchema])
const resourcePermissionsSchema = z.record(z.string(), permissionValueSchema)

export const permissionsSchema = z.preprocess(value => sanitizeRolePermissions(value as object | null | undefined), z.record(z.string(), resourcePermissionsSchema))

export const apiKeyFormSchema = z.object({
  admin_id: z.number().nullable().optional(),
  name: z.string().min(1, 'Name is required').max(128),
  note: z.string().max(512).optional(),
  permissions: permissionsSchema,
  inherit_permissions: z.boolean().default(true),
  expire_date: z.union([z.date(), z.string(), z.number()]).nullable().optional(),
  status: z.enum(['active', 'disabled']).optional(),
})

export type ApiKeyFormValuesInput = z.input<typeof apiKeyFormSchema>
export type ApiKeyFormValues = z.infer<typeof apiKeyFormSchema>

export const apiKeyFormDefaultValues: ApiKeyFormValuesInput = {
  admin_id: null,
  name: '',
  note: '',
  permissions: {},
  inherit_permissions: true,
  expire_date: null,
  status: 'active',
}
