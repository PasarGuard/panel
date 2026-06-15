import { z } from 'zod'

export const apiKeyFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(128),
  note: z.string().max(512).optional(),
  role_id: z.number().min(1, 'Role is required'),
  expire_date: z.union([z.date(), z.string(), z.number()]).nullable().optional(),
  status: z.enum(['active', 'disabled']).optional(),
})

export type ApiKeyFormValues = z.infer<typeof apiKeyFormSchema>

export const apiKeyFormDefaultValues: ApiKeyFormValues = {
  name: '',
  note: '',
  role_id: 2, // Default to administrator or something sensible
  expire_date: null,
  status: 'active',
}
