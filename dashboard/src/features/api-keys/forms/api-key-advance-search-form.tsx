import { z } from 'zod'
import { APIKeyStatus } from '@/service/api'

export const apiKeyAdvanceSearchFormSchema = z.object({
  status: z.array(z.nativeEnum(APIKeyStatus)).optional(),
  key_id: z.number().optional(),
})

export type ApiKeyAdvanceSearchFormValue = z.infer<typeof apiKeyAdvanceSearchFormSchema>
