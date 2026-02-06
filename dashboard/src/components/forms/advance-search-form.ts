import { z } from 'zod'

export const advanceSearchFormSchema = z.object({
  is_username: z.boolean().default(true),
  is_protocol: z.boolean().default(false),
  admin: z.array(z.string()).optional(),
  group: z.array(z.number()).optional(),
  status: z.enum(['0', 'active', 'on_hold', 'disabled', 'expired', 'limited']).default('0').optional(),
})

export type AdvanceSearchFormValue = z.infer<typeof advanceSearchFormSchema>
