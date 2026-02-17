import { ProxyHostSecurity, UserStatus } from '@/service/api'
import { z } from 'zod'

export const hostAdvanceSearchFormSchema = z.object({
  status: z.array(z.nativeEnum(UserStatus)).optional(),
  inbound_tags: z.array(z.string()).optional(),
  security: z.nativeEnum(ProxyHostSecurity).optional().nullable(),
  is_disabled: z.boolean().optional().nullable(),
})

export type HostAdvanceSearchFormValues = z.infer<typeof hostAdvanceSearchFormSchema>
